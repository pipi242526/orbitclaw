"""Runtime and language hint helpers for ContextBuilder."""

from __future__ import annotations

import os
import platform
import re
import time as _time
from datetime import datetime
from pathlib import Path


def detect_runtime_environment(
    *,
    override: str | None = None,
    dockerenv_exists: bool | None = None,
    cgroup_text: str | None = None,
) -> tuple[str, str]:
    """Detect whether orbitclaw runs in host or container-like environment."""
    forced = (override if override is not None else os.getenv("ORBITCLAW_RUNTIME_KIND", "")).strip().lower()
    forced_aliases = {
        "local": "host",
        "host": "host",
        "docker": "docker",
        "container": "container",
        "k8s": "kubernetes",
        "kubernetes": "kubernetes",
    }
    if forced in forced_aliases:
        normalized = forced_aliases[forced]
        return normalized, f"forced by ORBITCLAW_RUNTIME_KIND={forced}"

    if dockerenv_exists is None:
        dockerenv_exists = Path("/.dockerenv").exists()
    if dockerenv_exists:
        return "docker", "detected /.dockerenv"

    if cgroup_text is None:
        try:
            cgroup_text = Path("/proc/1/cgroup").read_text(encoding="utf-8", errors="ignore")
        except Exception:
            cgroup_text = ""

    low = (cgroup_text or "").lower()
    markers = (
        "docker",
        "containerd",
        "kubepods",
        "kubelet",
        "podman",
        "lxc",
    )
    for marker in markers:
        if marker in low:
            kind = "kubernetes" if marker in {"kubepods", "kubelet"} else "container"
            return kind, f"detected cgroup marker '{marker}'"

    return "host", "no container marker detected"


def build_runtime_summary() -> str:
    """Build a compact runtime summary for system prompt context."""
    system = platform.system()
    os_label = "macOS" if system == "Darwin" else system
    arch = platform.machine()
    py_ver = platform.python_version()
    runtime_kind, runtime_hint = detect_runtime_environment()
    return (
        f"{os_label} {arch}, Python {py_ver}\n"
        f"- Environment: {runtime_kind}\n"
        f"- Runtime Hint: {runtime_hint}"
    )


def normalize_language_code(value: str | None) -> str:
    raw = (value or "").strip()
    if not raw:
        return "auto"
    lowered = raw.lower()
    aliases = {
        "auto": "auto",
        "zh": "zh-CN",
        "zh-cn": "zh-CN",
        "zh-hans": "zh-CN",
        "cn": "zh-CN",
        "en": "en",
        "en-us": "en",
        "ja": "ja",
        "ja-jp": "ja",
        "jp": "ja",
        "ko": "ko",
        "ko-kr": "ko",
    }
    return aliases.get(lowered, raw)


def detect_reply_language(
    message: str,
    preferred_language: str | None = "auto",
    fallback_language: str | None = "zh-CN",
) -> tuple[str, str]:
    """Heuristic language hint for the current user message."""
    pref = normalize_language_code(preferred_language)
    if pref != "auto":
        return (
            pref,
            f"Final reply MUST be in {pref} unless the user explicitly requests another language.",
        )
    text = (message or "").strip()
    if not text:
        fallback = normalize_language_code(fallback_language)
        if fallback != "auto":
            return (
                fallback,
                f"User language is unclear. Use fallback language {fallback} unless explicitly requested otherwise.",
            )
        return ("same_as_user", "Reply in the same language as the user.")

    cjk_count = len(re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff]", text))
    kana_count = len(re.findall(r"[\u3040-\u30ff]", text))
    hangul_count = len(re.findall(r"[\uac00-\ud7af]", text))
    latin_count = len(re.findall(r"[A-Za-z]", text))
    if kana_count >= 1 and (kana_count + cjk_count) >= 2:
        return ("ja", "The user's message appears Japanese. Final reply should be in Japanese unless they ask otherwise.")
    if hangul_count >= 1:
        return ("ko", "The user's message appears Korean. Final reply should be in Korean unless they ask otherwise.")
    if cjk_count >= 2 and cjk_count >= latin_count and kana_count == 0:
        return (
            "zh-CN",
            "The user's message is in Chinese. Final reply MUST be in Simplified Chinese unless they explicitly request another language.",
        )
    if latin_count >= 4 and cjk_count == 0 and kana_count == 0 and hangul_count == 0:
        return ("en", "The user's message appears to be English. Final reply should be in English unless they ask otherwise.")
    fallback = normalize_language_code(fallback_language)
    if fallback != "auto":
        return (
            fallback,
            f"Language detection is ambiguous. Use fallback language {fallback} unless explicitly requested otherwise.",
        )
    return ("same_as_user", "Final reply should follow the user's language.")


def detect_search_locale_hint(message: str) -> str | None:
    """Heuristic hint for cross-lingual search based on user topic region."""
    text = (message or "").strip()
    if not text:
        return None
    text_lower = text.lower()
    locale_hints = (
        {
            "country": "Japan",
            "language_name": "Japanese",
            "language_code": "ja",
            "markers": ("日本", "东京", "大阪", "京都", "札幌", "横滨", "日元", "日经", "日本股市", "japan", "tokyo"),
        },
        {
            "country": "Korea",
            "language_name": "Korean",
            "language_code": "ko",
            "markers": ("韩国", "首尔", "釜山", "韩元", "韩国股市", "korea", "seoul"),
        },
        {
            "country": "Russia",
            "language_name": "Russian",
            "language_code": "ru",
            "markers": ("俄罗斯", "莫斯科", "卢布", "俄股", "russia", "moscow"),
        },
        {
            "country": "France",
            "language_name": "French",
            "language_code": "fr",
            "markers": ("法国", "巴黎", "欧元区法国", "france", "paris"),
        },
        {
            "country": "Germany",
            "language_name": "German",
            "language_code": "de",
            "markers": ("德国", "柏林", "德国股市", "germany", "berlin"),
        },
        {
            "country": "Spain",
            "language_name": "Spanish",
            "language_code": "es",
            "markers": ("西班牙", "马德里", "spain", "madrid"),
        },
    )
    for hint in locale_hints:
        for marker in hint["markers"]:
            if marker.isascii():
                if marker in text_lower:
                    return (
                        f"Cross-lingual search hint: topic appears {hint['country']}-related. "
                        f"Prefer {hint['language_name']} ({hint['language_code']}) search keywords first (and optionally English), then answer in the user's language."
                    )
            elif marker in text:
                return (
                    f"Cross-lingual search hint: topic appears {hint['country']}-related. "
                    f"Prefer {hint['language_name']} ({hint['language_code']}) search keywords first (and optionally English), then answer in the user's language."
                )
    return None


def build_runtime_context(
    channel: str | None,
    chat_id: str | None,
    current_message: str | None = None,
    *,
    reply_language_preference: str = "auto",
    auto_reply_fallback_language: str = "zh-CN",
    cross_lingual_search: bool = True,
) -> str:
    """Build dynamic runtime context and attach it to the tail user message."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M (%A)")
    tz = _time.strftime("%Z") or "UTC"
    lines = [f"Current Time: {now} ({tz})"]
    lang_code, lang_rule = detect_reply_language(
        current_message or "",
        preferred_language=reply_language_preference,
        fallback_language=auto_reply_fallback_language,
    )
    lines.append(f"Reply Language Hint: {lang_code}")
    lines.append(f"Reply Language Rule: {lang_rule}")
    search_hint = detect_search_locale_hint(current_message or "") if cross_lingual_search else None
    if search_hint:
        lines.append(f"Search Locale Hint: {search_hint}")
    if channel and chat_id:
        lines.append(f"Channel: {channel}")
        lines.append(f"Chat ID: {chat_id}")
    return "\n".join(lines)
