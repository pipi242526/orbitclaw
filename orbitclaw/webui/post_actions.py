"""POST action handlers for Web UI pages.

This module keeps mutation logic out of the HTTP server class to reduce coupling
and make later extension/testing simpler.
"""

from __future__ import annotations

import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from orbitclaw.config.loader import load_config
from orbitclaw.config.presets import (
    apply_recommended_tool_defaults as _apply_recommended_tool_defaults,
)
from orbitclaw.config.presets import merge_unique as _merge_unique
from orbitclaw.config.schema import (
    ChannelsConfig,
    EndpointProviderConfig,
    MCPServerConfig,
    SkillsConfig,
    ToolsConfig,
)
from orbitclaw.utils.helpers import get_exports_dir, get_global_skills_path, get_media_dir
from orbitclaw.webui.catalog import (
    find_mcp_library_entry,
    find_skill_library_entry,
    install_skill_from_library,
)
from orbitclaw.webui.common import (
    _CHANNEL_QUICK_SPECS,
    _MAX_SKILL_IMPORT_BYTES,
    _check_default_model_ref,
    _collect_skill_rows,
    _fetch_public_json,
    _get_nested_attr,
    _is_private_or_local_host,
    _parse_csv,
    _safe_int,
    _safe_json_object,
    _sanitize_env_key,
    _set_nested_attr,
)
from orbitclaw.webui.i18n import ui_copy as _ui_copy
from orbitclaw.webui.services import safe_positive_int as _safe_positive_int


def _localize_skill_install_reason(reason: str, *, zh: bool) -> str:
    """Convert skill installer internal reason to localized UI-friendly text."""
    text = str(reason or "").strip()
    if not text:
        return "未知错误" if zh else "unknown error"
    if text == "skill_name is required":
        return "skill_name 必填" if zh else text
    if text.startswith("built-in skill source not found: "):
        name = text.split(":", 1)[1].strip()
        return f"未找到内置技能源：{name}" if zh else text
    if text.startswith("skill already exists: "):
        name = text.split(":", 1)[1].strip()
        return f"技能已存在：{name}" if zh else text
    if text.startswith("installed skill: "):
        name = text.split(":", 1)[1].strip()
        return f"技能已安装：{name}" if zh else text
    return text


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
        ok, reason = _check_default_model_ref(
            load_config(cfg_path, apply_profiles=False, resolve_env=True),
            model,
            probe_remote=True,
        )
        if not ok:
            raise ValueError(t("Default model check failed: {reason}", "默认模型检测失败: {reason}").format(reason=reason))
        cfg.agents.defaults.model = model
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
        cfg.agents.defaults.reply_language = reply_language
        cfg.agents.defaults.auto_reply_fallback_language = fallback_language
        cfg.agents.defaults.cross_lingual_search = handler._form_bool(form, "cross_lingual_search")
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
        cfg.agents.defaults.max_history_chars = _safe_int(
            handler._form_str(form, "max_history_chars", str(cfg.agents.defaults.max_history_chars)),
            "max_history_chars",
            minimum=0,
        )
        cfg.agents.defaults.max_memory_context_chars = _safe_int(
            handler._form_str(form, "max_memory_context_chars", str(cfg.agents.defaults.max_memory_context_chars)),
            "max_memory_context_chars",
            minimum=0,
        )
        cfg.agents.defaults.max_background_context_chars = _safe_int(
            handler._form_str(
                form,
                "max_background_context_chars",
                str(cfg.agents.defaults.max_background_context_chars),
            ),
            "max_background_context_chars",
            minimum=0,
        )
        cfg.agents.defaults.max_inline_image_bytes = _safe_int(
            handler._form_str(form, "max_inline_image_bytes", str(cfg.agents.defaults.max_inline_image_bytes)),
            "max_inline_image_bytes",
            minimum=0,
        )
        cfg.agents.defaults.auto_compact_background = handler._form_bool(form, "auto_compact_background")
        cfg.agents.defaults.system_prompt_cache_ttl_seconds = _safe_int(
            handler._form_str(
                form,
                "system_prompt_cache_ttl_seconds",
                str(cfg.agents.defaults.system_prompt_cache_ttl_seconds),
            ),
            "system_prompt_cache_ttl_seconds",
            minimum=0,
        )
        cfg.agents.defaults.session_cache_max_entries = _safe_int(
            handler._form_str(form, "session_cache_max_entries", str(cfg.agents.defaults.session_cache_max_entries)),
            "session_cache_max_entries",
            minimum=1,
        )
        cfg.agents.defaults.gc_every_turns = _safe_int(
            handler._form_str(form, "gc_every_turns", str(cfg.agents.defaults.gc_every_turns)),
            "gc_every_turns",
            minimum=0,
        )
        cfg.agents.defaults.turn_timeout_seconds = _safe_int(
            handler._form_str(
                form,
                "turn_timeout_seconds",
                str(cfg.agents.defaults.turn_timeout_seconds),
            ),
            "turn_timeout_seconds",
            minimum=5,
        )
        cfg.agents.defaults.inbound_queue_maxsize = _safe_int(
            handler._form_str(
                form,
                "inbound_queue_maxsize",
                str(cfg.agents.defaults.inbound_queue_maxsize),
            ),
            "inbound_queue_maxsize",
            minimum=0,
        )
        cfg.agents.defaults.outbound_queue_maxsize = _safe_int(
            handler._form_str(
                form,
                "outbound_queue_maxsize",
                str(cfg.agents.defaults.outbound_queue_maxsize),
            ),
            "outbound_queue_maxsize",
            minimum=0,
        )
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
        if name in cfg.providers.endpoints:
            del cfg.providers.endpoints[name]
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
    normalized_models: list[str] = []
    for item in models:
        text = item.strip()
        if text.startswith(f"{name}/"):
            text = text[len(name) + 1 :].strip()
        if text and text not in normalized_models:
            normalized_models.append(text)
    headers = _safe_json_object(handler._form_str(form, "extra_headers_json", "{}"), "extra_headers")
    ep = EndpointProviderConfig(
        type=cfg_type,
        api_base=api_base,
        api_key=api_key,
        extra_headers=headers or None,
        models=normalized_models,
        enabled=handler._form_bool(form, "enabled"),
    )

    if original_name and original_name != name and original_name in cfg.providers.endpoints:
        del cfg.providers.endpoints[original_name]
    cfg.providers.endpoints[name] = ep
    handler._save_config(cfg)
    handler._redirect(
        "/endpoints",
        msg=handler._append_apply_status(
            f"Endpoint saved: {name}. Gateway will auto-reload shortly.",
            f"端点已保存: {name}。Gateway 将自动热重载生效。",
        ),
    )


def handle_post_channels(handler: Any, form: dict[str, list[str]]) -> None:
    """Handle /channels POST actions."""
    cfg = handler._load_config()
    action = handler._form_str(form, "action")
    def t(en: str, zh_cn: str) -> str:
        return _ui_copy(handler._ui_lang, en, zh_cn)
    if action == "save_channels_quick":
        selected_channel = handler._form_str(form, "quick_channel_id", "").strip().lower()
        selected_specs = [s for s in _CHANNEL_QUICK_SPECS if str(s["id"]).lower() == selected_channel]
        if not selected_specs:
            raise ValueError(t("Please select a valid channel.", "请选择一个有效渠道。"))
        for spec in selected_specs:
            sid = str(spec["id"])
            channel_obj = getattr(cfg.channels, sid)
            setattr(channel_obj, "enabled", handler._form_bool(form, f"ch_{sid}_enabled"))

            auth_mode = handler._form_str(form, f"ch_{sid}_auth_mode", "env_placeholders").strip()
            env_prefix = _sanitize_env_key(
                handler._form_str(form, f"ch_{sid}_env_prefix", str(spec["env_prefix"])),
                str(spec["env_prefix"]),
            )
            for field in spec["fields"]:
                path = str(field["path"])
                form_key = f"ch_{sid}_{path.replace('.', '__')}"
                current_value = str(_get_nested_attr(channel_obj, path) or "")
                submitted = handler._form_str(form, form_key, "").strip()
                if auth_mode == "env_placeholders" and field.get("env_suffix"):
                    next_value = f"${{{env_prefix}_{field['env_suffix']}}}"
                else:
                    next_value = submitted if submitted != "" else current_value
                _set_nested_attr(channel_obj, path, next_value)

            allow_values = _parse_csv(handler._form_str(form, f"ch_{sid}_allow_csv", ""))
            allow_mode = handler._form_str(form, f"ch_{sid}_allow_mode", "env_placeholders").strip()
            allow_prefix = _sanitize_env_key(
                handler._form_str(form, f"ch_{sid}_allow_env_prefix", str(spec["allow_env_prefix"])),
                str(spec["allow_env_prefix"]),
            )
            if allow_mode == "env_placeholders":
                allow_from = [f"${{{allow_prefix}_{idx + 1}}}" for idx, _ in enumerate(allow_values)]
            else:
                allow_from = allow_values
            _set_nested_attr(channel_obj, str(spec["allow_field"]), allow_from)
            setattr(cfg.channels, sid, channel_obj)

        handler._save_config(cfg)
        handler._redirect(
            "/channels",
            msg=handler._append_apply_status(
                f"Channel `{selected_channel}` saved (gateway auto-reloads if token/secret changed).",
                f"渠道 `{selected_channel}` 配置已保存（如改 token/secret，Gateway 将自动热重载）。",
            ),
        )
        return

    if action == "save_channels_json":
        raw = handler._form_str(form, "channels_json")
        data = _safe_json_object(raw, "channels")
        cfg.channels = ChannelsConfig.model_validate(data)
        handler._save_config(cfg)
        handler._redirect(
            "/channels",
            msg=handler._append_apply_status(
                "Channels JSON saved (gateway auto-reloads if token/secret changed).",
                "Channels 配置已保存（如改了 token/secret，Gateway 将自动热重载）。",
            ),
        )
        return

    raise ValueError(t("Unsupported channels action", "不支持的渠道操作"))


def handle_post_mcp(handler: Any, form: dict[str, list[str]]) -> None:
    """Handle /mcp POST actions."""
    cfg = handler._load_config()
    action = handler._form_str(form, "action")
    def t(en: str, zh_cn: str) -> str:
        return _ui_copy(handler._ui_lang, en, zh_cn)

    if action == "apply_recommended_mcp":
        _apply_recommended_tool_defaults(cfg)
        handler._save_config(cfg)
        handler._redirect("/mcp", msg=t("Recommended MCP defaults applied (Exa + Docloader).", "推荐 MCP 默认配置已应用（Exa + Docloader）。"))
        return

    if action == "install_mcp_library":
        library_id = handler._form_str(form, "library_id").strip()
        overwrite = handler._form_bool(form, "overwrite_existing")
        item = find_mcp_library_entry(library_id)
        if not item:
            raise ValueError(
                t("Unknown MCP library entry: {library_id}", "未知 MCP 库条目: {library_id}").format(
                    library_id=library_id
                )
            )
        name = str(item["server_name"])
        if name in cfg.tools.mcp_servers and not overwrite:
            handler._redirect(
                "/mcp",
                err=t(
                    "MCP server '{name}' already exists. Enable overwrite to replace.",
                    "MCP 服务 '{name}' 已存在。勾选覆盖后可替换。",
                ).format(name=name),
            )
            return
        cfg.tools.mcp_servers[name] = item["config"]
        cfg.tools.mcp_enabled_servers = _merge_unique(cfg.tools.mcp_enabled_servers, [name])
        handler._save_config(cfg)
        handler._redirect(
            "/mcp",
            msg=t("Installed MCP library entry: {name}", "已安装 MCP 库条目: {name}").format(name=name),
        )
        return

    if action == "install_mcp_from_manifest_url":
        manifest_url = handler._form_str(form, "manifest_url").strip()
        entry_id = handler._form_str(form, "entry_id").strip()
        overwrite = handler._form_bool(form, "overwrite_existing")
        if not manifest_url:
            raise ValueError(t("manifest_url is required", "manifest_url 必填"))
        if not entry_id:
            raise ValueError(t("entry_id is required", "entry_id 必填"))
        payload = _fetch_public_json(manifest_url)
        if not isinstance(payload, list):
            raise ValueError(t("manifest JSON must be an array", "manifest JSON 必须是数组"))
        selected = None
        for item in payload:
            if isinstance(item, dict) and str(item.get("id", "")).strip() == entry_id:
                selected = item
                break
        if not selected:
            raise ValueError(
                t("entry_id not found in manifest: {entry_id}", "manifest 中未找到 entry_id: {entry_id}").format(
                    entry_id=entry_id
                )
            )
        server_name = str(selected.get("server_name", "")).strip()
        config_obj = selected.get("config")
        if not server_name:
            raise ValueError(t("manifest entry missing server_name", "manifest 条目缺少 server_name"))
        if not isinstance(config_obj, dict):
            raise ValueError(t("manifest entry missing config object", "manifest 条目缺少 config 对象"))
        if server_name in cfg.tools.mcp_servers and not overwrite:
            handler._redirect(
                "/mcp",
                err=t(
                    "MCP server '{name}' already exists. Enable overwrite to replace.",
                    "MCP 服务 '{name}' 已存在。勾选覆盖后可替换。",
                ).format(name=server_name),
            )
            return
        cfg.tools.mcp_servers[server_name] = MCPServerConfig.model_validate(config_obj)
        cfg.tools.mcp_enabled_servers = _merge_unique(cfg.tools.mcp_enabled_servers, [server_name])
        handler._save_config(cfg)
        handler._redirect(
            "/mcp",
            msg=t("Installed MCP from manifest: {server_name}", "已从 manifest 安装 MCP: {server_name}").format(
                server_name=server_name
            ),
        )
        return

    if action == "save_custom_mcp":
        server_name = handler._form_str(form, "server_name").strip()
        mode = handler._form_str(form, "mode", "url").strip().lower()
        if not server_name:
            raise ValueError(t("server_name is required", "server_name 必填"))
        if mode == "url":
            url = handler._form_str(form, "url").strip()
            if not url:
                raise ValueError(t("url is required for HTTP mode", "HTTP 模式下 url 必填"))
            cfg.tools.mcp_servers[server_name] = MCPServerConfig(url=url)
        elif mode == "stdio":
            cmd = handler._form_str(form, "command").strip()
            if not cmd:
                raise ValueError(t("command is required for stdio mode", "stdio 模式下 command 必填"))
            args = _parse_csv(handler._form_str(form, "args_csv", ""))
            env = _safe_json_object(handler._form_str(form, "env_json", "{}"), "env_json")
            cfg.tools.mcp_servers[server_name] = MCPServerConfig(
                command=cmd,
                args=args,
                env={str(k): str(v) for k, v in env.items()},
            )
        else:
            raise ValueError(t("mode must be url or stdio", "mode 必须是 url 或 stdio"))
        if handler._form_bool(form, "enable_now"):
            cfg.tools.mcp_enabled_servers = _merge_unique(cfg.tools.mcp_enabled_servers, [server_name])
        handler._save_config(cfg)
        handler._redirect(
            "/mcp",
            msg=t("Saved MCP server: {server_name}", "MCP 服务已保存: {server_name}").format(
                server_name=server_name
            ),
        )
        return

    if action == "save_tools_json":
        data = _safe_json_object(handler._form_str(form, "tools_json"), "tools")
        cfg.tools = ToolsConfig.model_validate(data)
        handler._save_config(cfg)
        handler._redirect("/mcp", msg=t("Tools config saved", "Tools 配置已保存"))
        return

    raise ValueError(t("Unsupported MCP action", "不支持的 MCP 操作"))


def handle_post_skills(handler: Any, form: dict[str, list[str]]) -> None:
    """Handle /skills POST actions."""
    cfg = handler._load_config()
    action = handler._form_str(form, "action")
    zh = handler._ui_lang == "zh-CN"

    def t(en: str, zh_cn: str) -> str:
        return _ui_copy(handler._ui_lang, en, zh_cn)

    if action == "install_skill_library":
        entry_id = handler._form_str(form, "library_skill_id").strip()
        item = find_skill_library_entry(entry_id)
        if not item:
            raise ValueError(
                t("Unknown skill library entry: {entry_id}", "未知技能库条目: {entry_id}").format(entry_id=entry_id)
            )
        ok, reason = install_skill_from_library(str(item["name"]), overwrite=handler._form_bool(form, "overwrite_existing"))
        reason = _localize_skill_install_reason(reason, zh=zh)
        if not ok:
            raise ValueError(reason)
        cfg.skills.disabled = [s for s in (cfg.skills.disabled or []) if s != str(item["name"])]
        handler._save_config(cfg)
        handler._redirect("/skills", msg=reason)
        return

    if action == "enable_skill_from_library":
        name = handler._form_str(form, "skill_name").strip()
        if not name:
            raise ValueError(t("skill_name is required", "skill_name 必填"))
        disabled = [s for s in (cfg.skills.disabled or []) if s != name]
        cfg.skills.disabled = disabled
        handler._save_config(cfg)
        handler._redirect("/skills", msg=t("Skill enabled: {name}", "技能已启用: {name}").format(name=name))
        return

    if action == "import_skill_from_url":
        skill_name = handler._form_str(form, "skill_name").strip()
        skill_url = handler._form_str(form, "skill_url").strip()
        if not skill_name:
            raise ValueError(t("skill_name is required", "skill_name 必填"))
        parsed = urlparse(skill_url)
        if parsed.scheme != "https":
            raise ValueError(t("skill_url must use https://", "skill_url 必须使用 https://"))
        if not parsed.hostname:
            raise ValueError(t("skill_url must include host", "skill_url 必须包含主机名"))
        if _is_private_or_local_host(parsed.hostname):
            raise ValueError(t("skill_url host must be public", "skill_url 主机必须是公网地址"))
        try:
            req = urllib.request.Request(skill_url, headers={"User-Agent": "orbitclaw-webui/0.1"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                content_type = (resp.headers.get("Content-Type") or "").lower()
                if content_type and "text" not in content_type and "markdown" not in content_type:
                    raise ValueError(t("skill_url must return text/markdown content", "skill_url 必须返回 text/markdown 内容"))
                content = resp.read(_MAX_SKILL_IMPORT_BYTES + 1)
                if len(content) > _MAX_SKILL_IMPORT_BYTES:
                    raise ValueError(t("skill file is too large (max 512KB)", "技能文件过大（最大 512KB）"))
                content = content.decode("utf-8", errors="replace")
        except urllib.error.URLError as e:
            raise ValueError(
                t("failed to fetch skill URL: {error}", "拉取 skill URL 失败: {error}").format(error=e)
            ) from e
        if "# " not in content and "SKILL" not in content.upper():
            raise ValueError(t("fetched content does not look like SKILL.md", "下载内容看起来不是 SKILL.md"))
        skill_dir = get_global_skills_path() / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")
        disabled = [s for s in (cfg.skills.disabled or []) if s != skill_name]
        cfg.skills.disabled = disabled
        handler._save_config(cfg)
        handler._redirect(
            "/skills",
            msg=t("Imported skill: {name}", "已导入技能: {name}").format(name=skill_name),
        )
        return

    if action == "save_skills_enabled":
        enabled_skills = {s.strip() for s in form.get("enabled_skill", []) if s.strip()}
        rows = _collect_skill_rows(cfg)
        all_known = [row["name"] for row in rows]
        cfg.skills.disabled = [name for name in all_known if name not in enabled_skills]
        handler._save_config(cfg)
        handler._redirect("/skills", msg=t("Skill selection saved", "技能选择已保存"))
        return

    if action == "save_tools_json":
        data = _safe_json_object(handler._form_str(form, "tools_json"), "tools")
        cfg.tools = ToolsConfig.model_validate(data)
        handler._save_config(cfg)
        handler._redirect("/skills", msg=t("Tools config saved", "Tools 配置已保存"))
        return

    if action == "save_skills_json":
        data = _safe_json_object(handler._form_str(form, "skills_json"), "skills")
        cfg.skills = SkillsConfig.model_validate(data)
        handler._save_config(cfg)
        handler._redirect("/skills", msg=t("Skills config saved", "Skills 配置已保存"))
        return

    raise ValueError(t("Unsupported skills action", "不支持的技能操作"))


def handle_post_media(handler: Any, form: dict[str, list[str]]) -> None:
    """Handle /media POST actions."""
    def t(en: str, zh_cn: str) -> str:
        return _ui_copy(handler._ui_lang, en, zh_cn)
    action = handler._form_str(form, "action")
    media_page = _safe_positive_int(handler._form_str(form, "media_page", "1"), default=1)
    exports_page = _safe_positive_int(handler._form_str(form, "exports_page", "1"), default=1)
    media_target = f"/media?media_page={media_page}&exports_page={exports_page}"
    if action in {"save_exports_dir", "save_exports_dir_default"}:
        cfg = handler._load_config()
        raw = handler._form_str(form, "exports_dir", "").strip()
        cfg.tools.files_hub.exports_dir = "" if action == "save_exports_dir_default" else raw
        handler._save_config(cfg)
        handler._redirect(
            media_target,
            msg=t("Exports directory setting saved.", "导出目录设置已保存。"),
        )
        return

    scope = (handler._form_str(form, "scope", "media") or "media").strip().lower()
    if scope == "exports":
        cfg = handler._load_config()
        root_dir = get_exports_dir(cfg.tools.files_hub.exports_dir).resolve()
        scope_label = t("exports", "导出目录")
    else:
        scope = "media"
        root_dir = get_media_dir().resolve()
        scope_label = t("media", "媒体目录")
    if action == "refresh":
        handler._redirect(
            media_target,
            msg=t("Refreshed {scope} list.", "已刷新{scope}列表。").format(scope=scope_label),
        )
        return

    names: list[str] = []
    if action == "delete_selected":
        names = [n.strip() for n in form.get("selected_name", []) if n.strip()]
    elif action.startswith("delete_one:"):
        names = [action.split(":", 1)[1].strip()]
    else:
        raise ValueError(t("Unsupported media action", "不支持的媒体操作"))

    if not names:
        raise ValueError(t("Please select at least one file to delete.", "请选择要删除的文件。"))

    deleted = 0
    missing = 0
    for name in names:
        if "/" in name or "\\" in name or name in {".", ".."}:
            continue
        p = (root_dir / name).resolve()
        try:
            p.relative_to(root_dir)
        except ValueError:
            continue
        if not p.exists():
            missing += 1
            continue
        if not p.is_file():
            continue
        p.unlink(missing_ok=True)
        deleted += 1
    handler._redirect(
        media_target,
        msg=(
            t(
                "{scope}: deleted {deleted}{missing_en}",
                "{scope}已删除 {deleted} 个文件{missing_zh}",
            ).format(
                scope=scope_label,
                deleted=deleted,
                missing_en=(f", missing {missing}" if missing else ""),
                missing_zh=(f"，缺失 {missing} 个" if missing else ""),
            )
        ),
    )
