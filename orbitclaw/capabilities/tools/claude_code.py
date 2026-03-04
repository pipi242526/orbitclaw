"""Claude Code tmux session control tool."""

from __future__ import annotations

import asyncio
import json
import os
import re
import shlex
import shutil
import time
from pathlib import Path
from typing import Any

from orbitclaw.capabilities.tools.base import Tool
from orbitclaw.platform.config.schema import ClaudeCodeToolConfig

_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
_CTRL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


class ClaudeCodeTool(Tool):
    """Manage Claude Code CLI in persistent tmux sessions."""

    def __init__(
        self,
        *,
        workspace: Path,
        config: ClaudeCodeToolConfig,
        restrict_to_workspace: bool = False,
    ):
        self.workspace = workspace.resolve()
        self.config = config
        self.restrict_to_workspace = restrict_to_workspace

    @property
    def name(self) -> str:
        return "claude_code"

    @property
    def description(self) -> str:
        return (
            "Control Claude Code through tmux sessions: start/send/tail/status/list/stop. "
            "Use for long-running coding sessions on the server."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["start", "send", "tail", "status", "list", "stop"],
                    "description": "Operation to perform on Claude Code tmux sessions",
                },
                "session": {
                    "type": "string",
                    "description": (
                        "Session name (without prefix is okay; tool will normalize it). "
                        "Optional for start (auto-generated). For send/tail/status/stop, "
                        "if omitted and exactly one Claude Code session exists, it will be used."
                    ),
                },
                "prompt": {
                    "type": "string",
                    "description": "Prompt/content to send to an existing Claude Code session",
                },
                "working_dir": {
                    "type": "string",
                    "description": "Working directory for start action (defaults to tool config/workspace)",
                },
                "lines": {
                    "type": "integer",
                    "minimum": 10,
                    "maximum": 2000,
                    "description": "Lines to capture for tail/status preview",
                },
                "submit": {
                    "type": "boolean",
                    "description": "Whether to press Enter after sending prompt (default true)",
                },
                "include_output": {
                    "type": "boolean",
                    "description": "For status: include captured pane output preview",
                },
            },
            "required": ["action"],
        }

    async def execute(
        self,
        action: str,
        session: str | None = None,
        prompt: str | None = None,
        working_dir: str | None = None,
        lines: int | None = None,
        submit: bool = True,
        include_output: bool = True,
        **kwargs: Any,
    ) -> str:
        action = (action or "").strip().lower()
        if action not in {"start", "send", "tail", "status", "list", "stop"}:
            return self._dump({"error": f"unsupported_action: {action}"})

        tmux_path = shutil.which(self.config.tmux_command)
        if not tmux_path:
            return self._dump(
                {
                    "error": "tmux_not_found",
                    "hint": f"Install tmux and ensure `{self.config.tmux_command}` is on PATH.",
                }
            )

        if action == "list":
            return self._dump(await self._list_sessions(tmux_path))

        if action == "start":
            target = self._normalize_session_name(session)
            if not target:
                target = await self._generate_session_name(tmux_path)
            return self._dump(await self._start_session(tmux_path, target, prompt=prompt, working_dir=working_dir, submit=submit))
        target = self._normalize_session_name(session)
        if not target:
            target, err = await self._resolve_implicit_session(tmux_path)
            if err:
                return self._dump(err)
        if action == "send":
            return self._dump(await self._send_to_session(tmux_path, target, prompt=prompt, submit=submit))
        if action == "tail":
            return self._dump(await self._tail_session(tmux_path, target, lines=lines))
        if action == "status":
            return self._dump(await self._status_session(tmux_path, target, lines=lines, include_output=include_output))
        if action == "stop":
            return self._dump(await self._stop_session(tmux_path, target))

        return self._dump({"error": "unreachable"})

    @staticmethod
    def _dump(payload: dict[str, Any]) -> str:
        return json.dumps(payload, ensure_ascii=False)

    def _normalize_session_name(self, raw: str | None) -> str | None:
        if raw is None:
            return None
        name = str(raw).strip()
        if not name:
            return None
        name = re.sub(r"[^A-Za-z0-9_.:-]+", "_", name)
        prefix = self.config.session_prefix or "cc_"
        if not name.startswith(prefix):
            name = f"{prefix}{name}"
        # tmux names can be long but keep them readable/safe
        return name[:64]

    async def _generate_session_name(self, tmux_path: str) -> str:
        base = self._normalize_session_name(f"auto_{time.strftime('%Y%m%d_%H%M%S')}")
        if not base:
            base = (self.config.session_prefix or "cc_") + "auto"
        candidate = base
        for idx in range(1, 100):
            if not await self._session_exists(tmux_path, candidate):
                return candidate
            suffix = f"_{idx}"
            candidate = f"{base[: max(1, 64 - len(suffix))]}{suffix}"
        return f"{(self.config.session_prefix or 'cc_')}auto_{int(time.time())}"[:64]

    async def _resolve_implicit_session(self, tmux_path: str) -> tuple[str | None, dict[str, Any] | None]:
        listed = await self._list_sessions(tmux_path)
        if "error" in listed:
            return None, {
                "error": "session_required",
                "hint": "Provide `session`, or run `list` to inspect available Claude Code sessions.",
                "detail": listed.get("detail"),
            }
        sessions = [s.get("name") for s in listed.get("sessions", []) if isinstance(s.get("name"), str)]
        if len(sessions) == 1:
            return sessions[0], None
        if not sessions:
            return None, {
                "error": "session_required",
                "hint": "No Claude Code sessions found. Start one first with action=start.",
            }
        return None, {
            "error": "session_ambiguous",
            "hint": "Multiple Claude Code sessions exist. Provide `session` explicitly or call action=list.",
            "sessions": sessions[:20],
        }

    def _resolve_working_dir(self, working_dir: str | None) -> tuple[Path | None, str | None]:
        base = (working_dir or self.config.default_working_dir or str(self.workspace)).strip()
        try:
            path = Path(base).expanduser().resolve()
        except Exception as e:
            return None, f"invalid working_dir: {e}"
        if not path.exists():
            return None, f"working_dir does not exist: {path}"
        if not path.is_dir():
            return None, f"working_dir is not a directory: {path}"
        if self.restrict_to_workspace and self.workspace not in path.parents and path != self.workspace:
            return None, f"working_dir outside workspace is not allowed: {path}"
        return path, None

    def _claude_command_exists(self) -> bool:
        cmd = (self.config.command or "claude").strip()
        if not cmd:
            return False
        if "/" in cmd or cmd.startswith("."):
            return Path(cmd).expanduser().exists()
        return shutil.which(cmd) is not None

    async def _run(
        self,
        exe: str,
        *args: str,
        timeout: int | None = None,
    ) -> tuple[int, str, str]:
        proc = await asyncio.create_subprocess_exec(
            exe,
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout or self.config.timeout,
            )
        except asyncio.TimeoutError:
            proc.kill()
            try:
                await asyncio.wait_for(proc.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                pass
            return 124, "", f"timed out after {timeout or self.config.timeout}s"
        out = stdout.decode("utf-8", errors="replace") if stdout else ""
        err = stderr.decode("utf-8", errors="replace") if stderr else ""
        return proc.returncode or 0, out, err

    async def _tmux(self, tmux_path: str, *args: str) -> tuple[int, str, str]:
        return await self._run(tmux_path, *args, timeout=self.config.timeout)

    def _clean_capture(self, text: str) -> str:
        text = _ANSI_RE.sub("", text or "")
        text = _CTRL_RE.sub("", text)
        text = text.replace("\r", "")
        text = re.sub(r"\n{4,}", "\n\n\n", text).strip()
        if len(text) > self.config.max_output_chars:
            omitted = len(text) - self.config.max_output_chars
            text = (
                text[: self.config.max_output_chars]
                + f"\n\n[truncated by claude_code tool: {omitted} chars omitted]"
            )
        return text

    async def _session_exists(self, tmux_path: str, session: str) -> bool:
        rc, _, _ = await self._tmux(tmux_path, "has-session", "-t", session)
        return rc == 0

    async def _list_sessions(self, tmux_path: str) -> dict[str, Any]:
        prefix = self.config.session_prefix or "cc_"
        rc, out, err = await self._tmux(
            tmux_path,
            "list-sessions",
            "-F",
            "#{session_name}\t#{session_attached}\t#{session_windows}",
        )
        if rc != 0:
            if "no server running" in err.lower():
                return {"action": "list", "sessions": []}
            return {"error": "tmux_list_failed", "detail": err.strip() or out.strip()}
        sessions = []
        for line in out.splitlines():
            parts = line.split("\t")
            if not parts or not parts[0].startswith(prefix):
                continue
            sessions.append(
                {
                    "name": parts[0],
                    "attached": (parts[1] == "1") if len(parts) > 1 else False,
                    "windows": int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None,
                }
            )
        sessions.sort(key=lambda s: s.get("name") or "")
        return {"action": "list", "sessions": sessions}

    async def _start_session(
        self,
        tmux_path: str,
        session: str,
        *,
        prompt: str | None,
        working_dir: str | None,
        submit: bool,
    ) -> dict[str, Any]:
        cwd, err = self._resolve_working_dir(working_dir)
        if err:
            return {"error": "invalid_working_dir", "detail": err}
        if await self._session_exists(tmux_path, session):
            return {"error": "session_exists", "session": session, "hint": "Use send/status/tail, or choose another session name."}
        if not self._claude_command_exists():
            return {
                "error": "claude_command_not_found",
                "command": self.config.command,
                "hint": "Install Claude Code CLI and/or set tools.claudeCode.command to the executable path.",
            }

        cmdline = shlex.join([self.config.command, *self.config.args])
        shell = os.environ.get("SHELL") or "sh"
        rc, out, stderr = await self._tmux(
            tmux_path,
            "new-session",
            "-d",
            "-s",
            session,
            "-c",
            str(cwd),
            shell,
            "-lc",
            cmdline,
        )
        if rc != 0:
            return {"error": "start_failed", "session": session, "detail": (stderr or out).strip()}

        if self.config.startup_wait_ms > 0:
            await asyncio.sleep(max(0, self.config.startup_wait_ms) / 1000.0)

        sent = None
        if prompt:
            sent = await self._send_to_session(tmux_path, session, prompt=prompt, submit=submit)

        tail = await self._tail_session(tmux_path, session, lines=self.config.capture_lines)
        return {
            "action": "start",
            "ok": True,
            "session": session,
            "workingDir": str(cwd),
            "command": cmdline,
            "sent": sent if prompt else None,
            "tail": tail.get("output", ""),
        }

    async def _send_to_session(
        self,
        tmux_path: str,
        session: str,
        *,
        prompt: str | None,
        submit: bool,
    ) -> dict[str, Any]:
        if not prompt:
            return {"error": "prompt_required", "session": session}
        if not await self._session_exists(tmux_path, session):
            return {"error": "session_not_found", "session": session}

        # Preserve embedded newlines by sending line-by-line.
        lines = prompt.splitlines() or [prompt]
        for idx, line in enumerate(lines):
            rc, out, err = await self._tmux(tmux_path, "send-keys", "-t", session, "-l", line)
            if rc != 0:
                return {"error": "send_failed", "session": session, "detail": (err or out).strip()}
            if idx < len(lines) - 1:
                rc, out, err = await self._tmux(tmux_path, "send-keys", "-t", session, "Enter")
                if rc != 0:
                    return {"error": "send_failed", "session": session, "detail": (err or out).strip()}
        if submit:
            rc, out, err = await self._tmux(tmux_path, "send-keys", "-t", session, "Enter")
            if rc != 0:
                return {"error": "send_failed", "session": session, "detail": (err or out).strip()}

        return {
            "action": "send",
            "ok": True,
            "session": session,
            "submitted": bool(submit),
            "chars": len(prompt),
            "timestamp": int(time.time()),
        }

    async def _tail_session(self, tmux_path: str, session: str, *, lines: int | None) -> dict[str, Any]:
        if not await self._session_exists(tmux_path, session):
            return {"error": "session_not_found", "session": session}
        line_count = min(max(lines or self.config.capture_lines, 10), 2000)
        rc, out, err = await self._tmux(tmux_path, "capture-pane", "-p", "-t", session, "-S", f"-{line_count}")
        if rc != 0:
            return {"error": "tail_failed", "session": session, "detail": (err or out).strip()}
        return {
            "action": "tail",
            "ok": True,
            "session": session,
            "lines": line_count,
            "output": self._clean_capture(out),
        }

    async def _status_session(
        self,
        tmux_path: str,
        session: str,
        *,
        lines: int | None,
        include_output: bool,
    ) -> dict[str, Any]:
        if not await self._session_exists(tmux_path, session):
            return {"action": "status", "ok": False, "session": session, "exists": False}

        rc, out, err = await self._tmux(
            tmux_path,
            "display-message",
            "-p",
            "-t",
            session,
            "#{session_name}\t#{session_attached}\t#{session_windows}\t#{pane_current_command}\t#{pane_current_path}",
        )
        if rc != 0:
            return {"error": "status_failed", "session": session, "detail": (err or out).strip()}
        parts = out.strip().split("\t")
        data = {
            "action": "status",
            "ok": True,
            "exists": True,
            "session": parts[0] if len(parts) > 0 else session,
            "attached": (parts[1] == "1") if len(parts) > 1 else False,
            "windows": int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None,
            "currentCommand": parts[3] if len(parts) > 3 else None,
            "currentPath": parts[4] if len(parts) > 4 else None,
        }
        if include_output:
            tail = await self._tail_session(tmux_path, session, lines=lines)
            if tail.get("ok"):
                data["tail"] = tail.get("output", "")
        return data

    async def _stop_session(self, tmux_path: str, session: str) -> dict[str, Any]:
        if not await self._session_exists(tmux_path, session):
            return {"action": "stop", "ok": False, "session": session, "exists": False}
        rc, out, err = await self._tmux(tmux_path, "kill-session", "-t", session)
        if rc != 0:
            return {"error": "stop_failed", "session": session, "detail": (err or out).strip()}
        return {"action": "stop", "ok": True, "session": session}
