"""WebUI language labels and i18n helpers."""

from __future__ import annotations

import hashlib

from lunaeclaw.app.webui.copy_catalog import WEBUI_COPY_CATALOG

UI_LANGUAGE_CHOICES: list[tuple[str, str]] = [
    ("en", "English"),
    ("zh-CN", "简体中文"),
]

UI_TEXTS = {
    "en": {
        "tab_dashboard": "Dashboard",
        "tab_models": "Models & APIs",
        "tab_channels": "Channels",
        "tab_mcp": "MCP",
        "tab_skills": "Skills",
        "tab_media": "Media",
        "tab_chat": "Chat",
        "ui_lang": "Language",
        "ui_theme": "Theme",
        "theme_auto": "Auto",
        "theme_light": "Light",
        "theme_dark": "Dark",
        "not_found": "Not Found",
        "error": "Error",
        "subtitle": "Lightweight control hub (Host: {host}:{port}) · Path-token protected",
        "copied": "Copied",
        "unsupported_action": "Unsupported action",
        "stopping_webui": "Stopping Web UI...",
        "warn_not_localhost": (
            "Warning: Web UI is not bound to localhost. Keep the path token secret "
            "and prefer a trusted network/reverse proxy."
        ),
    },
    "zh-CN": {
        "tab_dashboard": "仪表盘",
        "tab_models": "模型与接口",
        "tab_channels": "渠道",
        "tab_mcp": "MCP",
        "tab_skills": "技能",
        "tab_media": "媒体文件",
        "tab_chat": "聊天",
        "ui_lang": "语言",
        "ui_theme": "主题",
        "theme_auto": "跟随系统",
        "theme_light": "浅色",
        "theme_dark": "深色",
        "not_found": "未找到页面",
        "error": "错误",
        "subtitle": "轻量控制中心（Host: {host}:{port}） · 使用路径密钥访问",
        "copied": "已复制",
        "unsupported_action": "不支持的操作",
        "stopping_webui": "正在停止 Web UI...",
        "warn_not_localhost": "警告：Web UI 未绑定到 localhost。请妥善保管路径密钥，并优先使用可信网络/反向代理。",
    },
}

# Shared terms used across multiple pages to avoid repeated inline translation
# branches inside render functions.
UI_TERM_TEXTS = {
    "en": {
        "enabled": "enabled",
        "disabled": "disabled",
        "filtered": "filtered",
        "ready": "ready",
        "missing_env": "missing env",
        "missing_command": "missing cmd",
        "not_installed": "not installed",
        "invalid": "invalid",
        "none": "none",
        "no_action": "No action",
        "install_from_library": "install from library",
        "installed_but_filtered": "installed but filtered by policy",
        "enabled_hint": "enabled",
        "alive": "alive",
        "not_ready": "not ready",
        "on": "on",
        "off": "off",
        "prev": "Prev",
        "next": "Next",
        "page": "Page",
        "showing": "showing",
        "delete": "Delete",
        "select_all": "Select all",
        "clear": "Clear",
        "refresh": "Refresh",
    },
    "zh-CN": {
        "enabled": "已启用",
        "disabled": "已禁用",
        "filtered": "已过滤",
        "ready": "就绪",
        "missing_env": "缺少环境变量",
        "missing_command": "缺少命令",
        "not_installed": "未安装",
        "invalid": "无效",
        "none": "无",
        "no_action": "无操作",
        "install_from_library": "可从库中安装",
        "installed_but_filtered": "已安装但被策略过滤",
        "enabled_hint": "已启用",
        "alive": "在线",
        "not_ready": "未就绪",
        "on": "开",
        "off": "关",
        "prev": "上一页",
        "next": "下一页",
        "page": "页",
        "showing": "显示",
        "delete": "删除",
        "select_all": "全选",
        "clear": "清空",
        "refresh": "刷新",
    },
}

_MISSING_COPY_KEYS: dict[str, int] = {}
_FALLBACK_HITS = 0


def ui_text(lang: str, key: str) -> str:
    return UI_TEXTS.get(lang, UI_TEXTS["en"]).get(key, key)


def ui_term(lang: str, key: str) -> str:
    """Return localized shared term used by Web UI renderers."""
    norm = normalize_ui_lang(lang)
    return UI_TERM_TEXTS.get(norm, UI_TERM_TEXTS["en"]).get(key, key)


def normalize_ui_lang(value: str | None) -> str:
    lang = (value or "en").strip().lower()
    return "zh-CN" if lang in {"zh", "zh-cn", "cn"} else "en"


def is_zh(lang: str | None) -> bool:
    return normalize_ui_lang(lang) == "zh-CN"


def tr(lang: str | None, en: str, zh_cn: str) -> str:
    """Translate a short UI string using the current UI language."""
    return ui_copy(lang, en, zh_cn)


def _copy_key(en: str, zh_cn: str) -> str:
    digest = hashlib.sha1(f"{en}\n{zh_cn}".encode("utf-8")).hexdigest()
    return f"copy_{digest[:10]}"


def ui_copy(lang: str | None, en: str, zh_cn: str, *, track: bool = True) -> str:
    """Translate pair-based UI copy through the generated dictionary catalog."""
    global _FALLBACK_HITS
    norm = normalize_ui_lang(lang)
    key = _copy_key(en, zh_cn)
    row = WEBUI_COPY_CATALOG.get(key)
    if row:
        value = row.get(norm)
        if isinstance(value, str) and value:
            return value
        value = row.get("en")
        if isinstance(value, str) and value:
            if track:
                _FALLBACK_HITS += 1
            return value
    if track:
        _MISSING_COPY_KEYS[key] = _MISSING_COPY_KEYS.get(key, 0) + 1
        _FALLBACK_HITS += 1
    return zh_cn if norm == "zh-CN" else en


def reset_copy_stats() -> None:
    """Reset runtime missing/fallback counters for copy coverage tests."""
    global _FALLBACK_HITS
    _MISSING_COPY_KEYS.clear()
    _FALLBACK_HITS = 0


def get_copy_stats() -> dict[str, object]:
    """Get runtime statistics for copy dictionary coverage."""
    return {
        "fallback_hits": _FALLBACK_HITS,
        "missing_keys": dict(_MISSING_COPY_KEYS),
    }


_REPLY_LANGUAGE_LABELS: dict[str, dict[str, str]] = {
    "auto": {"en": "auto (follow user message)", "zh-CN": "auto (跟随用户消息)"},
    "zh-CN": {"en": "zh-CN (Simplified Chinese)", "zh-CN": "zh-CN (简体中文)"},
    "en": {"en": "en (English)", "zh-CN": "en (英语)"},
    "ja": {"en": "ja (Japanese)", "zh-CN": "ja (日语)"},
    "ko": {"en": "ko (Korean)", "zh-CN": "ko (韩语)"},
    "fr": {"en": "fr (French)", "zh-CN": "fr (法语)"},
    "de": {"en": "de (German)", "zh-CN": "de (德语)"},
    "es": {"en": "es (Spanish)", "zh-CN": "es (西班牙语)"},
}


def reply_language_label(ui_lang: str, code: str) -> str:
    key = normalize_ui_lang(ui_lang)
    labels = _REPLY_LANGUAGE_LABELS.get(code)
    if not labels:
        return code
    return labels.get(key) or labels.get("en") or code
