"""Mochat channel implementation using Socket.IO with HTTP polling fallback."""

from __future__ import annotations

import asyncio
from collections import deque
from typing import Any

import httpx
from loguru import logger

from lunaeclaw.capabilities.channels.base import BaseChannel
from lunaeclaw.capabilities.channels.common.retry import seconds_from_ms
from lunaeclaw.capabilities.channels.mochat_adapter import mochat_api_send, mochat_post_json
from lunaeclaw.capabilities.channels.mochat_dedup import remember_message_id
from lunaeclaw.capabilities.channels.mochat_fallback import (
    ensure_fallback_tasks,
    stop_fallback_tasks,
)
from lunaeclaw.capabilities.channels.mochat_helpers import str_field
from lunaeclaw.capabilities.channels.mochat_mapper import (
    build_buffered_body,
    normalize_mochat_id_list,
    read_mochat_group_id,
    resolve_mochat_target,
)
from lunaeclaw.capabilities.channels.mochat_notify import (
    build_panel_notify_event,
    build_session_notify_event,
)
from lunaeclaw.capabilities.channels.mochat_protocol import (
    parse_mochat_inbound_event,
    parse_panel_poll_events,
)
from lunaeclaw.capabilities.channels.mochat_refresh import (
    parse_mochat_panels,
    parse_mochat_sessions,
)
from lunaeclaw.capabilities.channels.mochat_state import (
    load_mochat_session_cursors,
    save_mochat_session_cursors,
)
from lunaeclaw.capabilities.channels.mochat_subscribe import parse_subscribe_sessions_ack
from lunaeclaw.capabilities.channels.mochat_types import DelayState, MochatBufferedEntry
from lunaeclaw.capabilities.channels.mochat_watch import (
    iter_mochat_message_add_events,
    parse_mochat_watch_payload,
)
from lunaeclaw.core.bus.events import OutboundMessage
from lunaeclaw.core.bus.queue import MessageBus
from lunaeclaw.platform.config.schema import MochatConfig
from lunaeclaw.platform.utils.helpers import get_data_path

try:
    import socketio
    SOCKETIO_AVAILABLE = True
except ImportError:
    socketio = None
    SOCKETIO_AVAILABLE = False

try:
    import msgpack  # noqa: F401
    MSGPACK_AVAILABLE = True
except ImportError:
    MSGPACK_AVAILABLE = False

MAX_SEEN_MESSAGE_IDS = 2000
CURSOR_SAVE_DEBOUNCE_S = 0.5


# ---------------------------------------------------------------------------
# Channel
# ---------------------------------------------------------------------------

class MochatChannel(BaseChannel):
    """Mochat channel using socket.io with fallback polling workers."""

    name = "mochat"

    def __init__(self, config: MochatConfig, bus: MessageBus):
        super().__init__(config, bus)
        self.config: MochatConfig = config
        self._http: httpx.AsyncClient | None = None
        self._socket: Any = None
        self._ws_connected = self._ws_ready = False

        self._state_dir = get_data_path() / "mochat"
        self._cursor_path = self._state_dir / "session_cursors.json"
        self._session_cursor: dict[str, int] = {}
        self._cursor_save_task: asyncio.Task | None = None

        self._session_set: set[str] = set()
        self._panel_set: set[str] = set()
        self._auto_discover_sessions = self._auto_discover_panels = False

        self._cold_sessions: set[str] = set()
        self._session_by_converse: dict[str, str] = {}

        self._seen_set: dict[str, set[str]] = {}
        self._seen_queue: dict[str, deque[str]] = {}
        self._delay_states: dict[str, DelayState] = {}

        self._fallback_mode = False
        self._session_fallback_tasks: dict[str, asyncio.Task] = {}
        self._panel_fallback_tasks: dict[str, asyncio.Task] = {}
        self._refresh_task: asyncio.Task | None = None
        self._target_locks: dict[str, asyncio.Lock] = {}

    # ---- lifecycle ---------------------------------------------------------

    async def start(self) -> None:
        """Start Mochat channel workers and websocket connection."""
        claw_token = self._prepare_credential("claw_token", self.config.claw_token, required=True)
        if not claw_token:
            return
        self.config.claw_token = claw_token
        base_url = self._prepare_credential("base_url", self.config.base_url, required=True)
        if not base_url:
            return
        self.config.base_url = base_url
        self.config.socket_url = self._prepare_credential("socket_url", self.config.socket_url, required=False) or ""
        self.config.socket_path = (
            self._prepare_credential("socket_path", self.config.socket_path, required=False) or "/socket.io"
        )
        self.config.agent_user_id = self._prepare_credential(
            "agent_user_id", self.config.agent_user_id, required=False
        ) or ""

        self._running = True
        self._http = httpx.AsyncClient(timeout=30.0)
        self._state_dir.mkdir(parents=True, exist_ok=True)
        await self._load_session_cursors()
        self._seed_targets_from_config()
        await self._refresh_targets(subscribe_new=False)

        if not await self._start_socket_client():
            await self._ensure_fallback_workers()

        self._refresh_task = asyncio.create_task(self._refresh_loop())
        while self._running:
            await asyncio.sleep(1)

    async def stop(self) -> None:
        """Stop all workers and clean up resources."""
        self._running = False
        if self._refresh_task:
            self._refresh_task.cancel()
            self._refresh_task = None

        await self._stop_fallback_workers()
        await self._cancel_delay_timers()

        if self._socket:
            try:
                await self._socket.disconnect()
            except Exception:
                pass
            self._socket = None

        if self._cursor_save_task:
            self._cursor_save_task.cancel()
            self._cursor_save_task = None
        await self._save_session_cursors()

        if self._http:
            await self._http.aclose()
            self._http = None
        self._ws_connected = self._ws_ready = False

    async def send(self, msg: OutboundMessage) -> None:
        """Send outbound message to session or panel."""
        if not self.config.claw_token:
            logger.warning("Mochat claw_token missing, skip send")
            return

        parts = ([msg.content.strip()] if msg.content and msg.content.strip() else [])
        if msg.media:
            parts.extend(m for m in msg.media if isinstance(m, str) and m.strip())
        content = "\n".join(parts).strip()
        if not content:
            return

        target = resolve_mochat_target(msg.chat_id)
        if not target.id:
            logger.warning("Mochat outbound target is empty")
            return

        is_panel = (target.is_panel or target.id in self._panel_set) and not target.id.startswith("session_")
        try:
            if is_panel:
                await self._api_send("/api/claw/groups/panels/send", "panelId", target.id,
                                     content, msg.reply_to, read_mochat_group_id(msg.metadata))
            else:
                await self._api_send("/api/claw/sessions/send", "sessionId", target.id,
                                     content, msg.reply_to)
        except Exception as e:
            logger.error("Failed to send Mochat message: {}", e)

    # ---- config / init helpers ---------------------------------------------

    def _seed_targets_from_config(self) -> None:
        sessions, self._auto_discover_sessions = normalize_mochat_id_list(self.config.sessions)
        panels, self._auto_discover_panels = normalize_mochat_id_list(self.config.panels)
        self._session_set.update(sessions)
        self._panel_set.update(panels)
        for sid in sessions:
            if sid not in self._session_cursor:
                self._cold_sessions.add(sid)

    # ---- websocket ---------------------------------------------------------

    async def _start_socket_client(self) -> bool:
        if not SOCKETIO_AVAILABLE:
            logger.warning("python-socketio not installed, Mochat using polling fallback")
            return False

        serializer = "default"
        if not self.config.socket_disable_msgpack:
            if MSGPACK_AVAILABLE:
                serializer = "msgpack"
            else:
                logger.warning("msgpack not installed but socket_disable_msgpack=false; using JSON")

        client = socketio.AsyncClient(
            reconnection=True,
            reconnection_attempts=self.config.max_retry_attempts or None,
            reconnection_delay=seconds_from_ms(self.config.socket_reconnect_delay_ms, minimum=0.1),
            reconnection_delay_max=seconds_from_ms(self.config.socket_max_reconnect_delay_ms, minimum=0.1),
            logger=False, engineio_logger=False, serializer=serializer,
        )

        @client.event
        async def connect() -> None:
            self._ws_connected, self._ws_ready = True, False
            logger.info("Mochat websocket connected")
            subscribed = await self._subscribe_all()
            self._ws_ready = subscribed
            await (self._stop_fallback_workers() if subscribed else self._ensure_fallback_workers())

        @client.event
        async def disconnect() -> None:
            if not self._running:
                return
            self._ws_connected = self._ws_ready = False
            logger.warning("Mochat websocket disconnected")
            await self._ensure_fallback_workers()

        @client.event
        async def connect_error(data: Any) -> None:
            logger.error("Mochat websocket connect error: {}", data)

        @client.on("claw.session.events")
        async def on_session_events(payload: dict[str, Any]) -> None:
            await self._handle_watch_payload(payload, "session")

        @client.on("claw.panel.events")
        async def on_panel_events(payload: dict[str, Any]) -> None:
            await self._handle_watch_payload(payload, "panel")

        for ev in ("notify:chat.inbox.append", "notify:chat.message.add",
                    "notify:chat.message.update", "notify:chat.message.recall",
                    "notify:chat.message.delete"):
            client.on(ev, self._build_notify_handler(ev))

        socket_url = (self.config.socket_url or self.config.base_url).strip().rstrip("/")
        socket_path = (self.config.socket_path or "/socket.io").strip().lstrip("/")

        try:
            self._socket = client
            await client.connect(
                socket_url, transports=["websocket"], socketio_path=socket_path,
                auth={"token": self.config.claw_token},
                wait_timeout=seconds_from_ms(self.config.socket_connect_timeout_ms, minimum=1.0),
            )
            return True
        except Exception as e:
            logger.error("Failed to connect Mochat websocket: {}", e)
            try:
                await client.disconnect()
            except Exception:
                pass
            self._socket = None
            return False

    def _build_notify_handler(self, event_name: str):
        async def handler(payload: Any) -> None:
            if event_name == "notify:chat.inbox.append":
                await self._handle_notify_inbox_append(payload)
            elif event_name.startswith("notify:chat.message."):
                await self._handle_notify_chat_message(payload)
        return handler

    # ---- subscribe ---------------------------------------------------------

    async def _subscribe_all(self) -> bool:
        ok = await self._subscribe_sessions(sorted(self._session_set))
        ok = await self._subscribe_panels(sorted(self._panel_set)) and ok
        if self._auto_discover_sessions or self._auto_discover_panels:
            await self._refresh_targets(subscribe_new=True)
        return ok

    async def _subscribe_sessions(self, session_ids: list[str]) -> bool:
        if not session_ids:
            return True
        for sid in session_ids:
            if sid not in self._session_cursor:
                self._cold_sessions.add(sid)

        ack = await self._socket_call("com.claw.im.subscribeSessions", {
            "sessionIds": session_ids, "cursors": self._session_cursor,
            "limit": self.config.watch_limit,
        })
        if not ack.get("result"):
            logger.error("Mochat subscribeSessions failed: {}", ack.get('message', 'unknown error'))
            return False

        items = parse_subscribe_sessions_ack(ack)
        for p in items:
            await self._handle_watch_payload(p, "session")
        return True

    async def _subscribe_panels(self, panel_ids: list[str]) -> bool:
        if not self._auto_discover_panels and not panel_ids:
            return True
        ack = await self._socket_call("com.claw.im.subscribePanels", {"panelIds": panel_ids})
        if not ack.get("result"):
            logger.error("Mochat subscribePanels failed: {}", ack.get('message', 'unknown error'))
            return False
        return True

    async def _socket_call(self, event_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self._socket:
            return {"result": False, "message": "socket not connected"}
        try:
            raw = await self._socket.call(event_name, payload, timeout=10)
        except Exception as e:
            return {"result": False, "message": str(e)}
        return raw if isinstance(raw, dict) else {"result": True, "data": raw}

    # ---- refresh / discovery -----------------------------------------------

    async def _refresh_loop(self) -> None:
        interval_s = seconds_from_ms(self.config.refresh_interval_ms, minimum=1.0)
        while self._running:
            await asyncio.sleep(interval_s)
            try:
                await self._refresh_targets(subscribe_new=self._ws_ready)
            except Exception as e:
                logger.warning("Mochat refresh failed: {}", e)
            if self._fallback_mode:
                await self._ensure_fallback_workers()

    async def _refresh_targets(self, subscribe_new: bool) -> None:
        if self._auto_discover_sessions:
            await self._refresh_sessions_directory(subscribe_new)
        if self._auto_discover_panels:
            await self._refresh_panels(subscribe_new)

    async def _refresh_sessions_directory(self, subscribe_new: bool) -> None:
        try:
            response = await self._post_json("/api/claw/sessions/list", {})
        except Exception as e:
            logger.warning("Mochat listSessions failed: {}", e)
            return

        session_ids, converse_map = parse_mochat_sessions(response)
        if not session_ids:
            return

        new_ids: list[str] = []
        for sid in session_ids:
            if sid not in self._session_set:
                self._session_set.add(sid)
                new_ids.append(sid)
                if sid not in self._session_cursor:
                    self._cold_sessions.add(sid)
        self._session_by_converse.update(converse_map)

        if not new_ids:
            return
        if self._ws_ready and subscribe_new:
            await self._subscribe_sessions(new_ids)
        if self._fallback_mode:
            await self._ensure_fallback_workers()

    async def _refresh_panels(self, subscribe_new: bool) -> None:
        try:
            response = await self._post_json("/api/claw/groups/get", {})
        except Exception as e:
            logger.warning("Mochat getWorkspaceGroup failed: {}", e)
            return

        panel_ids = parse_mochat_panels(response)
        if not panel_ids:
            return

        new_ids: list[str] = []
        for pid in panel_ids:
            if pid and pid not in self._panel_set:
                self._panel_set.add(pid)
                new_ids.append(pid)

        if not new_ids:
            return
        if self._ws_ready and subscribe_new:
            await self._subscribe_panels(new_ids)
        if self._fallback_mode:
            await self._ensure_fallback_workers()

    # ---- fallback workers --------------------------------------------------

    async def _ensure_fallback_workers(self) -> None:
        if not self._running:
            return
        self._fallback_mode = True
        ensure_fallback_tasks(
            self._session_set,
            self._panel_set,
            self._session_fallback_tasks,
            self._panel_fallback_tasks,
            lambda sid: asyncio.create_task(self._session_watch_worker(sid)),
            lambda pid: asyncio.create_task(self._panel_poll_worker(pid)),
        )

    async def _stop_fallback_workers(self) -> None:
        self._fallback_mode = False
        await stop_fallback_tasks(self._session_fallback_tasks, self._panel_fallback_tasks)

    async def _session_watch_worker(self, session_id: str) -> None:
        while self._running and self._fallback_mode:
            try:
                payload = await self._post_json("/api/claw/sessions/watch", {
                    "sessionId": session_id, "cursor": self._session_cursor.get(session_id, 0),
                    "timeoutMs": self.config.watch_timeout_ms, "limit": self.config.watch_limit,
                })
                await self._handle_watch_payload(payload, "session")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("Mochat watch fallback error ({}): {}", session_id, e)
                await asyncio.sleep(seconds_from_ms(self.config.retry_delay_ms, minimum=0.1))

    async def _panel_poll_worker(self, panel_id: str) -> None:
        sleep_s = seconds_from_ms(self.config.refresh_interval_ms, minimum=1.0)
        while self._running and self._fallback_mode:
            try:
                resp = await self._post_json("/api/claw/groups/panels/messages", {
                    "panelId": panel_id, "limit": min(100, max(1, self.config.watch_limit)),
                })
                for event in parse_panel_poll_events(resp, panel_id=panel_id):
                    await self._process_inbound_event(panel_id, event, "panel")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("Mochat panel polling error ({}): {}", panel_id, e)
            await asyncio.sleep(sleep_s)

    # ---- inbound event processing ------------------------------------------

    async def _handle_watch_payload(self, payload: dict[str, Any], target_kind: str) -> None:
        parsed = parse_mochat_watch_payload(payload)
        if parsed is None:
            return
        target_id = parsed.target_id

        lock = self._target_locks.setdefault(f"{target_kind}:{target_id}", asyncio.Lock())
        async with lock:
            prev = self._session_cursor.get(target_id, 0) if target_kind == "session" else 0
            pc = parsed.cursor
            if target_kind == "session" and pc is not None and pc >= 0:
                self._mark_session_cursor(target_id, pc)

            if target_kind == "session" and target_id in self._cold_sessions:
                self._cold_sessions.discard(target_id)
                return

            for seq, event in iter_mochat_message_add_events(parsed.events):
                if target_kind == "session" and seq is not None and seq > self._session_cursor.get(target_id, prev):
                    self._mark_session_cursor(target_id, seq)
                await self._process_inbound_event(target_id, event, target_kind)

    async def _process_inbound_event(self, target_id: str, event: dict[str, Any], target_kind: str) -> None:
        parsed = parse_mochat_inbound_event(
            event,
            config=self.config,
            target_id=target_id,
            target_kind=target_kind,
        )
        if parsed is None:
            return

        author = parsed.author
        if not author or (self.config.agent_user_id and author == self.config.agent_user_id):
            return
        if not self.is_allowed(author):
            return

        message_id = parsed.message_id
        seen_key = f"{target_kind}:{target_id}"
        if message_id and self._remember_message_id(seen_key, message_id):
            return

        if parsed.should_skip:
            return

        entry = parsed.entry
        if parsed.use_delay:
            delay_key = seen_key
            if parsed.was_mentioned:
                await self._flush_delayed_entries(delay_key, target_id, target_kind, "mention", entry)
            else:
                await self._enqueue_delayed_entry(delay_key, target_id, target_kind, entry)
            return

        await self._dispatch_entries(target_id, target_kind, [entry], parsed.was_mentioned)

    # ---- dedup / buffering -------------------------------------------------

    def _remember_message_id(self, key: str, message_id: str) -> bool:
        return remember_message_id(
            self._seen_set,
            self._seen_queue,
            key=key,
            message_id=message_id,
            max_size=MAX_SEEN_MESSAGE_IDS,
        )

    async def _enqueue_delayed_entry(self, key: str, target_id: str, target_kind: str, entry: MochatBufferedEntry) -> None:
        state = self._delay_states.setdefault(key, DelayState())
        async with state.lock:
            state.entries.append(entry)
            if state.timer:
                state.timer.cancel()
            state.timer = asyncio.create_task(self._delay_flush_after(key, target_id, target_kind))

    async def _delay_flush_after(self, key: str, target_id: str, target_kind: str) -> None:
        await asyncio.sleep(seconds_from_ms(self.config.reply_delay_ms, minimum=0.0))
        await self._flush_delayed_entries(key, target_id, target_kind, "timer", None)

    async def _flush_delayed_entries(self, key: str, target_id: str, target_kind: str, reason: str, entry: MochatBufferedEntry | None) -> None:
        state = self._delay_states.setdefault(key, DelayState())
        async with state.lock:
            if entry:
                state.entries.append(entry)
            current = asyncio.current_task()
            if state.timer and state.timer is not current:
                state.timer.cancel()
            state.timer = None
            entries = state.entries[:]
            state.entries.clear()
        if entries:
            await self._dispatch_entries(target_id, target_kind, entries, reason == "mention")

    async def _dispatch_entries(self, target_id: str, target_kind: str, entries: list[MochatBufferedEntry], was_mentioned: bool) -> None:
        if not entries:
            return
        last = entries[-1]
        is_group = bool(last.group_id)
        body = build_buffered_body(entries, is_group) or "[empty message]"
        await self._handle_message(
            sender_id=last.author, chat_id=target_id, content=body,
            metadata={
                "message_id": last.message_id, "timestamp": last.timestamp,
                "is_group": is_group, "group_id": last.group_id,
                "sender_name": last.sender_name, "sender_username": last.sender_username,
                "target_kind": target_kind, "was_mentioned": was_mentioned,
                "buffered_count": len(entries),
            },
        )

    async def _cancel_delay_timers(self) -> None:
        for state in self._delay_states.values():
            if state.timer:
                state.timer.cancel()
        self._delay_states.clear()

    # ---- notify handlers ---------------------------------------------------

    async def _handle_notify_chat_message(self, payload: Any) -> None:
        parsed = build_panel_notify_event(payload, panel_set=self._panel_set)
        if parsed is None:
            return
        panel_id, evt = parsed
        await self._process_inbound_event(panel_id, evt, "panel")

    async def _handle_notify_inbox_append(self, payload: Any) -> None:
        detail = payload.get("payload") if isinstance(payload, dict) else None
        converse_id = str_field(detail or {}, "converseId")
        if not converse_id:
            return

        session_id = self._session_by_converse.get(converse_id)
        if not session_id:
            await self._refresh_sessions_directory(self._ws_ready)
            session_id = self._session_by_converse.get(converse_id)
        if not session_id:
            return

        evt = build_session_notify_event(payload, session_id=session_id)
        if evt is None:
            return
        await self._process_inbound_event(session_id, evt, "session")

    # ---- cursor persistence ------------------------------------------------

    def _mark_session_cursor(self, session_id: str, cursor: int) -> None:
        if cursor < 0 or cursor < self._session_cursor.get(session_id, 0):
            return
        self._session_cursor[session_id] = cursor
        if not self._cursor_save_task or self._cursor_save_task.done():
            self._cursor_save_task = asyncio.create_task(self._save_cursor_debounced())

    async def _save_cursor_debounced(self) -> None:
        await asyncio.sleep(CURSOR_SAVE_DEBOUNCE_S)
        await self._save_session_cursors()

    async def _load_session_cursors(self) -> None:
        try:
            self._session_cursor.update(load_mochat_session_cursors(self._cursor_path))
        except Exception as e:
            logger.warning("Failed to read Mochat cursor file: {}", e)

    async def _save_session_cursors(self) -> None:
        try:
            save_mochat_session_cursors(self._state_dir, self._cursor_path, self._session_cursor)
        except Exception as e:
            logger.warning("Failed to save Mochat cursor file: {}", e)

    # ---- HTTP helpers ------------------------------------------------------

    async def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self._http:
            raise RuntimeError("Mochat HTTP client not initialized")
        return await mochat_post_json(
            self._http,
            base_url=self.config.base_url,
            claw_token=self.config.claw_token,
            path=path,
            payload=payload,
        )

    async def _api_send(self, path: str, id_key: str, id_val: str,
                        content: str, reply_to: str | None, group_id: str | None = None) -> dict[str, Any]:
        if not self._http:
            raise RuntimeError("Mochat HTTP client not initialized")
        return await mochat_api_send(
            self._http,
            base_url=self.config.base_url,
            claw_token=self.config.claw_token,
            path=path,
            id_key=id_key,
            id_val=id_val,
            content=content,
            reply_to=reply_to,
            group_id=group_id,
        )
