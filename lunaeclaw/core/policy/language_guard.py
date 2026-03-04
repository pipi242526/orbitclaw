"""Language guard for final user-facing reply."""

from __future__ import annotations

import re
from typing import Callable

from loguru import logger

from lunaeclaw.platform.providers.base import LLMProvider

SUPPORTED_REPLY_LANGUAGES = {"zh-CN", "ja", "ko", "en"}


def detect_text_language(text: str | None) -> str:
    body = (text or "").strip()
    if not body:
        return "unknown"
    kana = len(re.findall(r"[\u3040-\u30ff]", body))
    hangul = len(re.findall(r"[\uac00-\ud7af]", body))
    cjk = len(re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff]", body))
    latin = len(re.findall(r"[A-Za-z]", body))
    if kana >= 2:
        return "ja"
    if hangul >= 2:
        return "ko"
    if cjk >= 4 and kana == 0 and hangul == 0 and cjk >= max(2, latin // 2):
        return "zh-CN"
    if latin >= 12 and cjk + kana + hangul <= 2:
        return "en"
    if cjk + kana + hangul > 0 and latin > 0:
        return "mixed"
    return "unknown"


def looks_code_heavy(text: str | None) -> bool:
    body = text or ""
    if body.count("```") >= 2:
        return True
    lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
    if not lines:
        return False
    prefixes = (
        "def ",
        "class ",
        "import ",
        "from ",
        "if ",
        "for ",
        "while ",
        "return ",
        "const ",
        "let ",
        "var ",
        "function ",
        "#include ",
        "SELECT ",
        "INSERT ",
        "UPDATE ",
        "DELETE ",
        "CREATE ",
        "ALTER ",
        "DROP ",
    )
    code_like = 0
    symbol_heavy = 0
    for line in lines:
        if line.startswith(prefixes) or line.endswith(("{", "}", ";")):
            code_like += 1
        ratio = sum(1 for ch in line if ch in "{}[]();<>:=`") / max(1, len(line))
        if ratio >= 0.18:
            symbol_heavy += 1
    return code_like >= max(3, len(lines) // 2) or symbol_heavy >= max(4, (2 * len(lines)) // 3)


def should_rewrite_reply_language(content: str, target_language: str | None) -> bool:
    target = (target_language or "").strip()
    if target not in SUPPORTED_REPLY_LANGUAGES:
        return False
    if len((content or "").strip()) < 24:
        return False
    if looks_code_heavy(content):
        return False
    detected = detect_text_language(content)
    if detected in {target, "mixed", "unknown"}:
        return False
    if target == "zh-CN" and detected == "en":
        return True
    if target == "ja" and detected in {"en", "zh-CN"}:
        return True
    if target == "ko" and detected in {"en", "zh-CN"}:
        return True
    if target == "en" and detected in {"zh-CN", "ja", "ko"}:
        return True
    return False


async def rewrite_reply_language(
    *,
    provider: LLMProvider,
    user_message: str,
    content: str,
    target_language: str,
    model: str,
    max_tokens: int,
    strip_think: Callable[[str | None], str | None],
) -> str:
    lang_map = {
        "zh-CN": "Simplified Chinese",
        "ja": "Japanese",
        "ko": "Korean",
        "en": "English",
    }
    label = lang_map.get(target_language, target_language)
    rewrite_prompt = (
        "Rewrite the assistant draft into the target language.\n"
        "Rules:\n"
        "1) Keep facts, numbers, dates, links, file paths, and commands unchanged.\n"
        "2) Keep Markdown structure unchanged.\n"
        "3) Do not translate fenced code blocks.\n"
        "4) Do not add new facts.\n"
        "5) Output only the rewritten final answer.\n\n"
        f"Target language: {label} ({target_language})\n\n"
        f"User message:\n{user_message}\n\n"
        f"Assistant draft:\n{content}"
    )
    try:
        rewrite = await provider.chat(
            messages=[
                {"role": "system", "content": "You are a strict reply rewriter."},
                {"role": "user", "content": rewrite_prompt},
            ],
            tools=None,
            model=model,
            max_tokens=max(256, min(max_tokens, 2048)),
            temperature=0.1,
        )
        rewritten = strip_think(rewrite.content)
        return rewritten or content
    except Exception as e:
        logger.debug("Language rewrite skipped due to provider error: {}", e)
        return content


async def enforce_reply_language(
    *,
    provider: LLMProvider,
    user_message: str,
    draft_reply: str,
    target_language: str | None,
    model: str,
    max_tokens: int,
    strip_think: Callable[[str | None], str | None],
) -> str:
    if not target_language:
        return draft_reply
    if not should_rewrite_reply_language(draft_reply, target_language):
        return draft_reply
    rewritten = await rewrite_reply_language(
        provider=provider,
        user_message=user_message,
        content=draft_reply,
        target_language=target_language,
        model=model,
        max_tokens=max_tokens,
        strip_think=strip_think,
    )
    if rewritten != draft_reply:
        logger.info("Final reply language adjusted to {}", target_language)
    return rewritten
