"""Telegram channel implementation using python-telegram-bot."""

from __future__ import annotations

import asyncio
import re
import secrets
import time

from loguru import logger
from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, ReplyParameters, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from telegram.request import HTTPXRequest

from lunaeclaw.capabilities.channels.base import BaseChannel
from lunaeclaw.core.bus.events import OutboundMessage
from lunaeclaw.core.bus.queue import MessageBus
from lunaeclaw.platform.config.schema import TelegramConfig
from lunaeclaw.platform.utils.helpers import safe_filename


def _markdown_to_telegram_html(text: str) -> str:
    """
    Convert markdown to Telegram-safe HTML.
    """
    if not text:
        return ""

    # 1. Extract and protect code blocks (preserve content from other processing)
    code_blocks: list[str] = []
    def save_code_block(m: re.Match) -> str:
        code_blocks.append(m.group(1))
        return f"\x00CB{len(code_blocks) - 1}\x00"

    text = re.sub(r'```[\w]*\n?([\s\S]*?)```', save_code_block, text)

    # 2. Extract and protect inline code
    inline_codes: list[str] = []
    def save_inline_code(m: re.Match) -> str:
        inline_codes.append(m.group(1))
        return f"\x00IC{len(inline_codes) - 1}\x00"

    text = re.sub(r'`([^`]+)`', save_inline_code, text)

    # 3. Headers # Title -> just the title text
    text = re.sub(r'^#{1,6}\s+(.+)$', r'\1', text, flags=re.MULTILINE)

    # 4. Blockquotes > text -> just the text (before HTML escaping)
    text = re.sub(r'^>\s*(.*)$', r'\1', text, flags=re.MULTILINE)

    # 5. Escape HTML special characters
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # 6. Links [text](url) - must be before bold/italic to handle nested cases
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)

    # 7. Bold **text** or __text__
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'__(.+?)__', r'<b>\1</b>', text)

    # 8. Italic _text_ (avoid matching inside words like some_var_name)
    text = re.sub(r'(?<![a-zA-Z0-9])_([^_]+)_(?![a-zA-Z0-9])', r'<i>\1</i>', text)

    # 9. Strikethrough ~~text~~
    text = re.sub(r'~~(.+?)~~', r'<s>\1</s>', text)

    # 10. Bullet lists - item -> • item
    text = re.sub(r'^[-*]\s+', '• ', text, flags=re.MULTILINE)

    # 11. Restore inline code with HTML tags
    for i, code in enumerate(inline_codes):
        # Escape HTML in code content
        escaped = code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        text = text.replace(f"\x00IC{i}\x00", f"<code>{escaped}</code>")

    # 12. Restore code blocks with HTML tags
    for i, code in enumerate(code_blocks):
        # Escape HTML in code content
        escaped = code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        text = text.replace(f"\x00CB{i}\x00", f"<pre><code>{escaped}</code></pre>")

    return text


def _split_message(content: str, max_len: int = 4000) -> list[str]:
    """Split content into chunks within max_len, preferring line breaks."""
    if len(content) <= max_len:
        return [content]
    chunks: list[str] = []
    while content:
        if len(content) <= max_len:
            chunks.append(content)
            break
        cut = content[:max_len]
        pos = cut.rfind('\n')
        if pos == -1:
            pos = cut.rfind(' ')
        if pos == -1:
            pos = max_len
        chunks.append(content[:pos])
        content = content[pos:].lstrip()
    return chunks


class TelegramChannel(BaseChannel):
    """
    Telegram channel using long polling.

    Simple and reliable - no webhook/public IP needed.
    """

    name = "telegram"

    # Commands registered with Telegram's command menu
    BOT_COMMANDS = [
        BotCommand("start", "Start the bot"),
        BotCommand("new", "Start a new conversation"),
        BotCommand("help", "Show available commands"),
        BotCommand("whoami", "Show your Telegram sender ID"),
    ]
    _TOKEN_PATTERN = re.compile(r"^[0-9]{6,}:[A-Za-z0-9_-]{20,}$")

    def __init__(
        self,
        config: TelegramConfig,
        bus: MessageBus,
        groq_api_key: str = "",
    ):
        super().__init__(config, bus)
        self.config: TelegramConfig = config
        self.groq_api_key = groq_api_key
        self._app: Application | None = None
        self._chat_ids: dict[str, int] = {}  # Map sender_id to chat_id for replies
        self._typing_tasks: dict[str, asyncio.Task] = {}  # chat_id -> typing loop task
        self._callback_registry: dict[str, dict] = {}

    async def start(self) -> None:
        """Start the Telegram bot with long polling."""
        token_text = self._prepare_credential("token", self.config.token, required=True)
        if not token_text:
            return
        self.config.token = token_text
        if not self._TOKEN_PATTERN.match(token_text):
            logger.error("Telegram bot token format invalid after sanitize (expected <digits>:<token>)")
            return
        proxy_text = self._prepare_credential("proxy", self.config.proxy, required=False) if self.config.proxy else None
        self.config.proxy = proxy_text

        self._running = True

        # Build the application with larger connection pool to avoid pool-timeout on long runs
        req = HTTPXRequest(connection_pool_size=16, pool_timeout=5.0, connect_timeout=30.0, read_timeout=30.0)
        builder = Application.builder().token(token_text).request(req).get_updates_request(req)
        if proxy_text:
            builder = builder.proxy(proxy_text).get_updates_proxy(proxy_text)
        self._app = builder.build()
        self._app.add_error_handler(self._on_error)

        # Add command handlers
        self._app.add_handler(CommandHandler("start", self._on_start))
        self._app.add_handler(CommandHandler("new", self._forward_command))
        self._app.add_handler(CommandHandler("help", self._on_help))
        self._app.add_handler(CommandHandler("whoami", self._on_whoami))
        self._app.add_handler(CallbackQueryHandler(self._on_callback_query))

        # Add message handler for text, photos, voice, documents
        self._app.add_handler(
            MessageHandler(
                (filters.TEXT | filters.PHOTO | filters.VOICE | filters.AUDIO | filters.Document.ALL)
                & ~filters.COMMAND,
                self._on_message
            )
        )

        logger.info("Starting Telegram bot (polling mode)...")

        # Initialize and start polling
        await self._app.initialize()
        await self._app.start()

        # Get bot info and register command menu
        bot_info = await self._app.bot.get_me()
        logger.info("Telegram bot @{} connected", bot_info.username)

        try:
            await self._app.bot.set_my_commands(self.BOT_COMMANDS)
            logger.debug("Telegram bot commands registered")
        except Exception as e:
            logger.warning("Failed to register bot commands: {}", e)

        # Start polling (this runs until stopped)
        await self._app.updater.start_polling(
            allowed_updates=["message", "callback_query"],
            drop_pending_updates=True  # Ignore old messages on startup
        )

        # Keep running until stopped
        while self._running:
            await asyncio.sleep(1)

    async def stop(self) -> None:
        """Stop the Telegram bot."""
        self._running = False
        self._callback_registry.clear()

        # Cancel all typing indicators
        for chat_id in list(self._typing_tasks):
            self._stop_typing(chat_id)

        if self._app:
            logger.info("Stopping Telegram bot...")
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
            self._app = None

    @staticmethod
    def _get_media_type(path: str) -> str:
        """Guess media type from file extension."""
        ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
        if ext in ("jpg", "jpeg", "png", "gif", "webp"):
            return "photo"
        if ext == "ogg":
            return "voice"
        if ext in ("mp3", "m4a", "wav", "aac"):
            return "audio"
        return "document"

    async def send(self, msg: OutboundMessage) -> None:
        """Send a message through Telegram."""
        if not self._app:
            logger.warning("Telegram bot not running")
            return

        self._stop_typing(msg.chat_id)

        try:
            chat_id = int(msg.chat_id)
        except ValueError:
            logger.error("Invalid chat_id: {}", msg.chat_id)
            return

        reply_params = None
        resolved_reply_to = msg.reply_to
        if not resolved_reply_to:
            resolved_reply_to = msg.metadata.get("reply_to") or msg.metadata.get("message_id")
        if not resolved_reply_to and self.config.reply_to_message:
            resolved_reply_to = msg.metadata.get("message_id")
        if resolved_reply_to:
            try:
                reply_params = ReplyParameters(
                    message_id=int(resolved_reply_to),
                    allow_sending_without_reply=True
                )
            except Exception:
                logger.debug("Invalid Telegram reply target ignored: {}", resolved_reply_to)

        reply_markup = self._build_inline_keyboard(msg.actions, str(chat_id))
        media_items = list(msg.media or [])
        for item in (msg.attachments or []):
            if isinstance(item, dict):
                path = item.get("path")
                if isinstance(path, str) and path and path not in media_items:
                    media_items.append(path)

        # Send media files
        for media_path in media_items:
            try:
                media_type = self._get_media_type(media_path)
                sender = {
                    "photo": self._app.bot.send_photo,
                    "voice": self._app.bot.send_voice,
                    "audio": self._app.bot.send_audio,
                }.get(media_type, self._app.bot.send_document)
                param = "photo" if media_type == "photo" else media_type if media_type in ("voice", "audio") else "document"
                with open(media_path, 'rb') as f:
                    await sender(
                        chat_id=chat_id,
                        **{param: f},
                        reply_parameters=reply_params
                    )
            except Exception as e:
                filename = media_path.rsplit("/", 1)[-1]
                logger.error("Failed to send media {}: {}", media_path, e)
                await self._app.bot.send_message(
                    chat_id=chat_id,
                    text=f"[Failed to send: {filename}]",
                    reply_parameters=reply_params
                )

        # Send text content
        if msg.content and msg.content != "[empty message]":
            for i, chunk in enumerate(_split_message(msg.content)):
                try:
                    html = _markdown_to_telegram_html(chunk)
                    kwargs = {
                        "chat_id": chat_id,
                        "text": html,
                        "parse_mode": "HTML",
                        "reply_parameters": reply_params,
                    }
                    if i == 0 and reply_markup:
                        kwargs["reply_markup"] = reply_markup
                    await self._app.bot.send_message(**kwargs)
                except Exception as e:
                    logger.warning("HTML parse failed, falling back to plain text: {}", e)
                    try:
                        kwargs = {
                            "chat_id": chat_id,
                            "text": chunk,
                            "reply_parameters": reply_params,
                        }
                        if i == 0 and reply_markup:
                            kwargs["reply_markup"] = reply_markup
                        await self._app.bot.send_message(**kwargs)
                    except Exception as e2:
                        logger.error("Error sending Telegram message: {}", e2)

    def _build_inline_keyboard(self, actions: list[dict] | None, chat_id: str) -> InlineKeyboardMarkup | None:
        """Build inline keyboard from outbound actions and bind nonce callbacks."""
        if not self.config.inline_actions or not actions:
            return None

        rows: list[list[InlineKeyboardButton]] = []
        for idx, raw in enumerate(actions[:12]):
            if not isinstance(raw, dict):
                continue
            title = str(raw.get("title") or raw.get("text") or raw.get("label") or "").strip()
            if not title:
                title = f"Option {idx + 1}"
            action_id = str(raw.get("id") or raw.get("value") or title).strip()
            payload = {
                "id": action_id,
                "title": title,
                "value": raw.get("value"),
                "prompt": raw.get("prompt"),
            }
            token = self._mint_callback_token(chat_id=chat_id, payload=payload)
            rows.append([InlineKeyboardButton(text=title, callback_data=f"nb:{token}")])

        return InlineKeyboardMarkup(rows) if rows else None

    def _mint_callback_token(self, *, chat_id: str, payload: dict) -> str:
        """Create one-time callback token with TTL to prevent replay."""
        self._cleanup_callback_registry()
        ttl = max(30, int(self.config.callback_ttl_seconds or 0))
        token = secrets.token_urlsafe(9)
        while token in self._callback_registry:
            token = secrets.token_urlsafe(9)
        self._callback_registry[token] = {
            "chat_id": str(chat_id),
            "payload": payload,
            "expires_at": time.time() + ttl,
        }
        return token

    def _cleanup_callback_registry(self) -> None:
        now = time.time()
        expired = [key for key, item in self._callback_registry.items() if float(item.get("expires_at", 0.0)) <= now]
        for key in expired:
            self._callback_registry.pop(key, None)
        # Hard cap to avoid unbounded memory growth if callbacks are never consumed.
        if len(self._callback_registry) > 4096:
            keys = sorted(
                self._callback_registry.keys(),
                key=lambda k: float(self._callback_registry[k].get("expires_at", 0.0)),
            )
            for key in keys[: len(self._callback_registry) - 2048]:
                self._callback_registry.pop(key, None)

    async def _on_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle inline keyboard callback with nonce+TTL replay protection."""
        _ = context
        self._cleanup_callback_registry()
        query = update.callback_query
        if not query:
            return
        data = (query.data or "").strip()
        if not data.startswith("nb:"):
            await query.answer("Unsupported action", show_alert=False)
            return

        token = data[3:]
        entry = self._callback_registry.pop(token, None)
        if not entry:
            await query.answer("Action expired, please retry.", show_alert=False)
            return
        if float(entry.get("expires_at", 0.0)) <= time.time():
            await query.answer("Action expired, please retry.", show_alert=False)
            return

        message = query.message
        if not message:
            await query.answer("Message context missing.", show_alert=False)
            return
        if str(message.chat_id) != str(entry.get("chat_id")):
            await query.answer("Action is not valid in this chat.", show_alert=False)
            return

        await query.answer("Received", show_alert=False)
        sender = update.effective_user
        sender_id = self._sender_id(sender) if sender else "unknown"
        if not self.is_allowed(sender_id):
            await query.answer("Not allowed", show_alert=True)
            if message:
                await self._reply_access_denied(message, sender_id)
            return
        action = entry.get("payload", {})
        content = str(action.get("prompt") or action.get("value") or action.get("title") or action.get("id") or "")
        if not content:
            content = "button_clicked"

        self._start_typing(str(message.chat_id))
        await self._handle_message(
            sender_id=sender_id,
            chat_id=str(message.chat_id),
            content=content,
            metadata={
                "message_id": message.message_id,
                "reply_to": message.message_id,
                "user_id": sender.id if sender else None,
                "username": sender.username if sender else None,
                "first_name": sender.first_name if sender else None,
                "is_group": message.chat.type != "private",
                "callback_action": {
                    "id": action.get("id"),
                    "title": action.get("title"),
                    "value": action.get("value"),
                    "token": token,
                },
            },
        )

    async def _on_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command."""
        if not update.message or not update.effective_user:
            return

        user = update.effective_user
        await update.message.reply_text(
            f"👋 Hi {user.first_name}! I'm lunaeclaw.\n\n"
            "Send me a message and I'll respond!\n"
            "Type /help to see available commands."
        )

    async def _on_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /help command, bypassing ACL so all users can access it."""
        if not update.message:
            return
        await update.message.reply_text(
            "🐈 lunaeclaw commands:\n"
            "/new — Start a new conversation\n"
            "/help — Show available commands\n"
            "/whoami — Show your sender ID (for allowFrom)"
        )

    async def _on_whoami(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show sender id/username for allowFrom troubleshooting."""
        _ = context
        if not update.message or not update.effective_user:
            return
        user = update.effective_user
        sender_id = self._sender_id(user)
        chat_type = update.message.chat.type if update.message.chat else "unknown"
        await update.message.reply_text(
            "Your sender_id:\n"
            f"{sender_id}\n\n"
            "Use either numeric ID or username in allowFrom.\n"
            f"chat_type={chat_type}"
        )

    @staticmethod
    def _sender_id(user) -> str:
        """Build sender_id with username for allowlist matching."""
        sid = str(user.id)
        return f"{sid}|{user.username}" if user.username else sid

    async def _forward_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Forward slash commands to the bus for unified handling in AgentLoop."""
        _ = context
        if not update.message or not update.effective_user:
            return
        message = update.message
        user = update.effective_user
        sender_id = self._sender_id(user)
        if not self.is_allowed(sender_id):
            await self._reply_access_denied(message, sender_id)
            return
        await self._handle_message(
            sender_id=sender_id,
            chat_id=str(message.chat_id),
            content=message.text,
            metadata={
                "message_id": message.message_id,
                "reply_to": message.reply_to_message.message_id if message.reply_to_message else None,
                "user_id": user.id,
                "username": user.username,
                "first_name": user.first_name,
                "is_group": message.chat.type != "private",
            },
        )

    async def _on_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle incoming messages (text, photos, voice, documents)."""
        _ = context
        if not update.message or not update.effective_user:
            return

        message = update.message
        user = update.effective_user
        chat_id = message.chat_id
        sender_id = self._sender_id(user)
        if not self.is_allowed(sender_id):
            await self._reply_access_denied(message, sender_id)
            return

        # Store chat_id for replies
        self._chat_ids[sender_id] = chat_id

        # Build content from text and/or media
        content_parts = []
        media_paths = []
        attachments: list[dict] = []

        # Text content
        if message.text:
            content_parts.append(message.text)
        if message.caption:
            content_parts.append(message.caption)

        # Handle media files
        media_file = None
        media_type = None

        if message.photo:
            media_file = message.photo[-1]  # Largest photo
            media_type = "image"
        elif message.voice:
            media_file = message.voice
            media_type = "voice"
        elif message.audio:
            media_file = message.audio
            media_type = "audio"
        elif message.document:
            media_file = message.document
            media_type = "file"

        # Download media if present
        if media_file and self._app:
            try:
                file = await self._app.bot.get_file(media_file.file_id)
                mime_type = getattr(media_file, 'mime_type', None)
                self._get_extension(media_type, mime_type)
                original_name = getattr(media_file, "file_name", None)

                # Save to centralized lunaeclaw media directory
                from lunaeclaw.platform.utils.helpers import get_media_dir
                media_dir = get_media_dir()

                file_path = self._build_media_path(
                    media_dir=media_dir,
                    file_id=media_file.file_id,
                    media_type=media_type,
                    mime_type=mime_type,
                    original_name=original_name,
                )
                await file.download_to_drive(str(file_path))

                media_paths.append(str(file_path))
                attachments.append(
                    {
                        "path": str(file_path),
                        "name": original_name or file_path.name,
                        "kind": media_type,
                        "mime_type": mime_type or "",
                        "source": "telegram",
                    }
                )

                # Handle voice transcription
                if media_type == "voice" or media_type == "audio":
                    from lunaeclaw.platform.providers.transcription import GroqTranscriptionProvider
                    transcriber = GroqTranscriptionProvider(api_key=self.groq_api_key)
                    transcription = await transcriber.transcribe(file_path)
                    if transcription:
                        logger.info("Transcribed {}: {}...", media_type, transcription[:50])
                        content_parts.append(f"[transcription: {transcription}]")
                    else:
                        note = f" (original: {original_name})" if original_name else ""
                        content_parts.append(f"[{media_type}: {file_path}{note}]")
                else:
                    note = f" (original: {original_name})" if original_name else ""
                    content_parts.append(f"[{media_type}: {file_path}{note}]")

                logger.debug("Downloaded {} to {}", media_type, file_path)
            except Exception as e:
                logger.error("Failed to download media: {}", e)
                content_parts.append(f"[{media_type}: download failed]")

        content = "\n".join(content_parts) if content_parts else "[empty message]"

        logger.debug("Telegram message from {}: {}...", sender_id, content[:50])

        str_chat_id = str(chat_id)

        # Start typing indicator before processing
        self._start_typing(str_chat_id)

        # Forward to the message bus
        await self._handle_message(
            sender_id=sender_id,
            chat_id=str_chat_id,
            content=content,
            media=media_paths,
            attachments=attachments,
            metadata={
                "message_id": message.message_id,
                "reply_to": message.reply_to_message.message_id if message.reply_to_message else None,
                "user_id": user.id,
                "username": user.username,
                "first_name": user.first_name,
                "is_group": message.chat.type != "private"
            }
        )

    def _start_typing(self, chat_id: str) -> None:
        """Start sending 'typing...' indicator for a chat."""
        # Cancel any existing typing task for this chat
        self._stop_typing(chat_id)
        self._typing_tasks[chat_id] = asyncio.create_task(self._typing_loop(chat_id))

    def _stop_typing(self, chat_id: str) -> None:
        """Stop the typing indicator for a chat."""
        task = self._typing_tasks.pop(chat_id, None)
        if task and not task.done():
            task.cancel()

    async def _typing_loop(self, chat_id: str) -> None:
        """Repeatedly send 'typing' action until cancelled."""
        try:
            while self._app:
                await self._app.bot.send_chat_action(chat_id=int(chat_id), action="typing")
                await asyncio.sleep(4)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug("Typing indicator stopped for {}: {}", chat_id, e)

    async def _on_error(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Log polling / handler errors instead of silently swallowing them."""
        logger.error("Telegram error: {}", context.error)

    async def _reply_access_denied(self, message, sender_id: str) -> None:
        """Return explicit ACL denial message instead of silent drop."""
        try:
            allow = [str(x).strip() for x in (self.config.allow_from or []) if str(x).strip()]
            allow_preview = ", ".join(allow[:8]) if allow else "(empty)"
            if len(allow) > 8:
                allow_preview += ", ..."
            await message.reply_text(
                "未授权访问。\n"
                f"sender_id={sender_id}\n"
                "请将上面的 sender_id（或用户名）加入 allowFrom 后重试。\n"
                f"当前 allowFrom={allow_preview}"
            )
            logger.warning("Access denied for sender {} on channel telegram", sender_id)
        except Exception as e:
            logger.warning("Failed to send ACL denial tip: {}", e)

    def _get_extension(self, media_type: str, mime_type: str | None) -> str:
        """Get file extension based on media type."""
        if mime_type:
            ext_map = {
                "image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif",
                "audio/ogg": ".ogg", "audio/mpeg": ".mp3", "audio/mp4": ".m4a",
            }
            if mime_type in ext_map:
                return ext_map[mime_type]

        type_map = {"image": ".jpg", "voice": ".ogg", "audio": ".mp3", "file": ""}
        return type_map.get(media_type, "")

    def _build_media_path(
        self,
        media_dir,
        file_id: str,
        media_type: str,
        mime_type: str | None,
        original_name: str | None = None,
    ):
        """Build saved media path and preserve original filename/extension when available."""
        ext = self._get_extension(media_type, mime_type)
        original = (original_name or "").strip()
        if original:
            safe = safe_filename(original).replace(" ", "_")
            candidate = safe if "." in safe else f"{safe}{ext}"
        else:
            candidate = f"{media_type}{ext}"

        stem = file_id[:12]
        path = media_dir / f"{stem}_{candidate}"
        if not path.exists():
            return path
        for i in range(2, 1000):
            p = media_dir / f"{stem}_{i}_{candidate}"
            if not p.exists():
                return p
        return media_dir / f"{stem}_{candidate}"
