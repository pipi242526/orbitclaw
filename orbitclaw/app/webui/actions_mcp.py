"""POST handlers for WebUI MCP actions."""

from __future__ import annotations

from typing import Any

from orbitclaw.app.webui.catalog import find_mcp_library_entry
from orbitclaw.app.webui.common import _fetch_public_json, _parse_csv, _safe_json_object
from orbitclaw.app.webui.i18n import ui_copy as _ui_copy
from orbitclaw.app.webui.services_mcp import (
    install_mcp_server,
    is_mcp_server_enabled,
    remove_mcp_server,
    set_mcp_server_enabled,
)
from orbitclaw.platform.config.schema import MCPServerConfig, ToolsConfig


def handle_post_mcp(handler: Any, form: dict[str, list[str]]) -> None:
    """Handle /mcp POST actions."""
    cfg = handler._load_config()
    action = handler._form_str(form, "action")

    def t(en: str, zh_cn: str) -> str:
        return _ui_copy(handler._ui_lang, en, zh_cn)

    if action == "toggle_mcp_server":
        server_name = handler._form_str(form, "server_name").strip()
        if not server_name:
            raise ValueError(t("server_name is required", "server_name 必填"))
        if server_name not in cfg.tools.mcp_servers:
            raise ValueError(t("MCP server not found: {name}", "MCP 服务不存在: {name}").format(name=server_name))
        next_enabled = not is_mcp_server_enabled(cfg, server_name)
        set_mcp_server_enabled(cfg, server_name=server_name, enabled=next_enabled)
        handler._save_config(cfg)
        handler._redirect(
            "/mcp",
            msg=(
                t("MCP server enabled: {server_name}", "MCP 服务已启用: {server_name}")
                if next_enabled
                else t("MCP server paused: {server_name}", "MCP 服务已暂停: {server_name}")
            ).format(server_name=server_name),
        )
        return

    if action == "uninstall_mcp_server":
        server_name = handler._form_str(form, "server_name").strip()
        if not server_name:
            raise ValueError(t("server_name is required", "server_name 必填"))
        if server_name not in cfg.tools.mcp_servers:
            raise ValueError(t("MCP server not found: {name}", "MCP 服务不存在: {name}").format(name=server_name))
        remove_mcp_server(cfg, server_name=server_name)
        handler._save_config(cfg)
        ok_msg = (
            f"MCP 服务已卸载: {server_name}"
            if handler._ui_lang == "zh-CN"
            else f"MCP server uninstalled: {server_name}"
        )
        handler._redirect(
            "/mcp",
            msg=ok_msg,
        )
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
        install_mcp_server(cfg, server_name=name, server_config=item["config"], enable_now=True)
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
        install_mcp_server(
            cfg,
            server_name=server_name,
            server_config=MCPServerConfig.model_validate(config_obj),
            enable_now=True,
        )
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
            server_cfg = MCPServerConfig(url=url)
        elif mode == "stdio":
            cmd = handler._form_str(form, "command").strip()
            if not cmd:
                raise ValueError(t("command is required for stdio mode", "stdio 模式下 command 必填"))
            args = _parse_csv(handler._form_str(form, "args_csv", ""))
            env = _safe_json_object(handler._form_str(form, "env_json", "{}"), "env_json")
            server_cfg = MCPServerConfig(
                command=cmd,
                args=args,
                env={str(k): str(v) for k, v in env.items()},
            )
        else:
            raise ValueError(t("mode must be url or stdio", "mode 必须是 url 或 stdio"))
        install_mcp_server(
            cfg,
            server_name=server_name,
            server_config=server_cfg,
            enable_now=handler._form_bool(form, "enable_now"),
        )
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
