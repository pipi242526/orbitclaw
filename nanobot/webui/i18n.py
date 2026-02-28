"""WebUI language labels and language helpers."""

from __future__ import annotations

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
        "ui_lang": "Language",
        "not_found": "Not Found",
        "error": "Error",
    },
    "zh-CN": {
        "tab_dashboard": "仪表盘",
        "tab_models": "模型与接口",
        "tab_channels": "渠道",
        "tab_mcp": "MCP",
        "tab_skills": "技能",
        "tab_media": "媒体文件",
        "ui_lang": "语言",
        "not_found": "未找到页面",
        "error": "错误",
    },
}


def ui_text(lang: str, key: str) -> str:
    return UI_TEXTS.get(lang, UI_TEXTS["en"]).get(key, key)


def normalize_ui_lang(value: str | None) -> str:
    lang = (value or "en").strip().lower()
    return "zh-CN" if lang in {"zh", "zh-cn", "cn"} else "en"

