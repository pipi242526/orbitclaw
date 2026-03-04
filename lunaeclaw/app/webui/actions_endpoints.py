"""POST handlers for WebUI endpoints actions."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from lunaeclaw.app.webui.common import (
    _parse_csv,
    _safe_int,
    _safe_json_object,
)
from lunaeclaw.app.webui.i18n import ui_copy as _ui_copy
from lunaeclaw.app.webui.services_endpoints import (
    apply_agent_preferences,
    apply_default_model,
    apply_runtime_budget,
    delete_endpoint,
    normalize_endpoint_models,
    save_endpoint,
    validate_default_model,
)


def handle_post_endpoints(handler: Any, form: dict[str, list[str]], *, cfg_path: Path) -> None:
    """Handle /endpoints POST actions."""
    cfg = handler._load_config()
    action = handler._form_str(form, "action")

    def t(en: str, zh_cn: str) -> str:
        return _ui_copy(handler._ui_lang, en, zh_cn)

    if action == "set_default_model":
        model = (
            handler._form_str(form, "default_model_custom").strip()
            or handler._form_str(form, "default_model_select").strip()
            or handler._form_str(form, "default_model").strip()
        )
        if not model:
            raise ValueError(t("default_model cannot be empty.", "default_model 不能为空。"))
        ok, reason = validate_default_model(cfg_path, model)
        if not ok:
            raise ValueError(t("Default model check failed: {reason}", "默认模型检测失败: {reason}").format(reason=reason))
        apply_default_model(cfg, model=model)
        handler._save_config(cfg)
        handler._redirect(
            "/endpoints",
            msg=handler._append_apply_status(
                f"Default model saved (check passed: {reason}). Gateway will auto-reload shortly.",
                f"默认模型已保存（检测通过: {reason}）。Gateway 将自动热重载生效。",
            ),
        )
        return

    if action == "set_agent_preferences":
        reply_language = handler._form_str(form, "reply_language", "auto").strip() or "auto"
        fallback_language = handler._form_str(form, "auto_reply_fallback_language", "zh-CN").strip() or "zh-CN"
        apply_agent_preferences(
            cfg,
            reply_language=reply_language,
            fallback_language=fallback_language,
            cross_lingual_search=handler._form_bool(form, "cross_lingual_search"),
        )
        handler._save_config(cfg)
        handler._redirect(
            "/endpoints",
            msg=handler._append_apply_status(
                "Language/search policy saved. Gateway will auto-reload shortly.",
                "语言与搜索策略已保存。Gateway 将自动热重载生效。",
            ),
        )
        return

    if action == "set_agent_runtime_budget":
        values: dict[str, int | bool] = {
            "max_history_chars": _safe_int(
                handler._form_str(form, "max_history_chars", str(cfg.agents.defaults.max_history_chars)),
                "max_history_chars",
                minimum=0,
            ),
            "max_memory_context_chars": _safe_int(
                handler._form_str(form, "max_memory_context_chars", str(cfg.agents.defaults.max_memory_context_chars)),
                "max_memory_context_chars",
                minimum=0,
            ),
            "max_background_context_chars": _safe_int(
                handler._form_str(
                    form,
                    "max_background_context_chars",
                    str(cfg.agents.defaults.max_background_context_chars),
                ),
                "max_background_context_chars",
                minimum=0,
            ),
            "max_inline_image_bytes": _safe_int(
                handler._form_str(form, "max_inline_image_bytes", str(cfg.agents.defaults.max_inline_image_bytes)),
                "max_inline_image_bytes",
                minimum=0,
            ),
            "auto_compact_background": handler._form_bool(form, "auto_compact_background"),
            "system_prompt_cache_ttl_seconds": _safe_int(
                handler._form_str(
                    form,
                    "system_prompt_cache_ttl_seconds",
                    str(cfg.agents.defaults.system_prompt_cache_ttl_seconds),
                ),
                "system_prompt_cache_ttl_seconds",
                minimum=0,
            ),
            "session_cache_max_entries": _safe_int(
                handler._form_str(form, "session_cache_max_entries", str(cfg.agents.defaults.session_cache_max_entries)),
                "session_cache_max_entries",
                minimum=1,
            ),
            "gc_every_turns": _safe_int(
                handler._form_str(form, "gc_every_turns", str(cfg.agents.defaults.gc_every_turns)),
                "gc_every_turns",
                minimum=0,
            ),
            "turn_timeout_seconds": _safe_int(
                handler._form_str(
                    form,
                    "turn_timeout_seconds",
                    str(cfg.agents.defaults.turn_timeout_seconds),
                ),
                "turn_timeout_seconds",
                minimum=5,
            ),
            "inbound_queue_maxsize": _safe_int(
                handler._form_str(
                    form,
                    "inbound_queue_maxsize",
                    str(cfg.agents.defaults.inbound_queue_maxsize),
                ),
                "inbound_queue_maxsize",
                minimum=0,
            ),
            "outbound_queue_maxsize": _safe_int(
                handler._form_str(
                    form,
                    "outbound_queue_maxsize",
                    str(cfg.agents.defaults.outbound_queue_maxsize),
                ),
                "outbound_queue_maxsize",
                minimum=0,
            ),
        }
        apply_runtime_budget(cfg, values=values)
        handler._save_config(cfg)
        handler._redirect(
            "/endpoints",
            msg=handler._append_apply_status(
                "Runtime budget settings saved. Gateway will auto-reload shortly.",
                "资源策略已保存。Gateway 将自动热重载生效。",
            ),
        )
        return

    if action == "delete_endpoint":
        original_name = handler._form_str(form, "original_name") or handler._form_str(form, "name")
        name = original_name.strip()
        if not name:
            raise ValueError(t("Missing endpoint name.", "缺少端点名称。"))
        if delete_endpoint(cfg, name=name):
            handler._save_config(cfg)
            handler._redirect(
                "/endpoints",
                msg=handler._append_apply_status(
                    f"Deleted endpoint: {name}. Gateway will auto-reload shortly.",
                    f"已删除端点: {name}。Gateway 将自动热重载生效。",
                ),
            )
            return
        raise ValueError(t("Endpoint not found: {name}", "端点不存在: {name}").format(name=name))

    if action != "save_endpoint":
        raise ValueError(t("Unsupported endpoints action", "不支持的端点操作"))

    original_name = handler._form_str(form, "original_name").strip()
    name = handler._form_str(form, "name").strip()
    if not name:
        raise ValueError(t("Endpoint name cannot be empty.", "端点名称不能为空。"))

    cfg_type = (handler._form_str(form, "type") or "openai_compatible").strip().lower().replace("-", "_")
    api_base = handler._form_str(form, "api_base").strip() or None
    api_key = handler._form_str(form, "api_key").strip()
    models = _parse_csv(handler._form_str(form, "models_csv"))
    normalized_models = normalize_endpoint_models(name, models)
    headers = _safe_json_object(handler._form_str(form, "extra_headers_json", "{}"), "extra_headers")
    save_endpoint(
        cfg,
        original_name=original_name,
        name=name,
        cfg_type=cfg_type,
        api_base=api_base,
        api_key=api_key,
        headers=headers,
        models=normalized_models,
        enabled=handler._form_bool(form, "enabled"),
    )
    handler._save_config(cfg)
    handler._redirect(
        "/endpoints",
        msg=handler._append_apply_status(
            f"Endpoint saved: {name}. Gateway will auto-reload shortly.",
            f"端点已保存: {name}。Gateway 将自动热重载生效。",
        ),
    )
