"""Turn execution helpers for AgentLoop."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Awaitable, Callable

from loguru import logger


async def run_agent_iterations(
    *,
    provider: Any,
    context: Any,
    tools: Any,
    initial_messages: list[dict[str, Any]],
    max_iterations: int,
    model: str,
    temperature: float,
    max_tokens: int,
    on_progress: Callable[[str], Awaitable[None]] | None,
    emit_tool_hints: bool,
    user_message: str,
    strip_think: Callable[[str], str],
    tool_hint: Callable[[list[Any]], str],
    processing_notice_text: Callable[[str], str],
    truncate_tool_result: Callable[[str, str], str],
) -> tuple[str | None, list[str]]:
    """Run iterative model/tool loop and return (final_content, tools_used)."""
    messages: list[dict[str, Any]] | Any = initial_messages
    iteration = 0
    final_content = None
    tools_used: list[str] = []
    tool_definitions = tools.get_definitions()

    while iteration < max_iterations:
        iteration += 1

        response = await provider.chat(
            messages=messages,
            tools=tool_definitions,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        if response.has_tool_calls:
            if on_progress:
                clean = strip_think(response.content)
                if clean:
                    await on_progress(clean)
                else:
                    if emit_tool_hints:
                        await on_progress(tool_hint(response.tool_calls))
                    else:
                        await on_progress(processing_notice_text(user_message))

            tool_call_dicts = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                    },
                }
                for tc in response.tool_calls
            ]
            messages = context.add_assistant_message(
                messages,
                response.content,
                tool_call_dicts,
                reasoning_content=response.reasoning_content,
            )

            for tool_call in response.tool_calls:
                tools_used.append(tool_call.name)
                args_str = json.dumps(tool_call.arguments, ensure_ascii=False)
                logger.info("Tool call: {}({})", tool_call.name, args_str[:200])
                result = await tools.execute(tool_call.name, tool_call.arguments)
                result = truncate_tool_result(result, tool_call.name)
                messages = context.add_tool_result(messages, tool_call.id, tool_call.name, result)
        else:
            final_content = strip_think(response.content)
            break

    return final_content, tools_used


def create_delayed_notice_task(
    *,
    delay_seconds: float,
    send_notice: Callable[[], Awaitable[None]],
) -> asyncio.Task:
    """Create a cancellable delayed progress-notice task."""

    async def _runner() -> None:
        try:
            await asyncio.sleep(delay_seconds)
            await send_notice()
        except asyncio.CancelledError:
            return

    return asyncio.create_task(_runner())


async def cancel_task_safely(task: asyncio.Task | None) -> None:
    """Cancel task and swallow cancellation error."""
    if task is None or task.done():
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
