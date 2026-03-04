"""CLI diagnostics command implementations.

This module isolates large status/doctor routines from commands.py to improve
readability and reduce coupling in command registration code.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any


def run_status(console: Any, logo: str) -> None:
    """Show lunaeclaw status."""
    from lunaeclaw.capabilities.tools.web import has_exa_search_mcp
    from lunaeclaw.core.context.skills import SkillsLoader
    from lunaeclaw.platform.config.loader import _discover_env_files, get_config_path, load_config
    from lunaeclaw.platform.utils.budget import (
        collect_runtime_budget_alerts,
        estimate_tokens_from_chars,
        read_host_resource_snapshot,
    )
    from lunaeclaw.platform.utils.helpers import (
        get_env_dir,
        get_env_file,
        get_exports_dir,
        get_global_skills_path,
        get_mcp_home,
    )

    config_path = get_config_path()
    config = load_config()
    workspace = config.workspace_path

    console.print(f"{logo} lunaeclaw Status\n")

    console.print(f"Config: {config_path} {'[green]✓[/green]' if config_path.exists() else '[red]✗[/red]'}")
    console.print(f"Workspace: {workspace} {'[green]✓[/green]' if workspace.exists() else '[red]✗[/red]'}")
    console.print(f"Global skills dir: {get_global_skills_path()} {'[green]✓[/green]' if get_global_skills_path().exists() else '[red]✗[/red]'}")
    console.print(f"MCP home: {get_mcp_home()} {'[green]✓[/green]' if get_mcp_home().exists() else '[red]✗[/red]'}")
    console.print(f"Env file: {get_env_file()} {'[green]✓[/green]' if get_env_file().exists() else '[dim](not created)[/dim]'}")
    console.print(f"Env dir: {get_env_dir()} {'[green]✓[/green]' if get_env_dir().exists() else '[red]✗[/red]'}")
    env_files = _discover_env_files()
    if env_files:
        console.print(f"Env files: {len(env_files)} loaded helper file(s)")

    if not config_path.exists():
        return

    from lunaeclaw.platform.providers.registry import PROVIDERS

    console.print(f"Model: {config.agents.defaults.model}")

    for spec in PROVIDERS:
        p = getattr(config.providers, spec.name, None)
        if p is None:
            continue
        if spec.is_oauth:
            console.print(f"{spec.label}: [green]✓ (OAuth)[/green]")
        elif spec.is_local:
            if p.api_base:
                console.print(f"{spec.label}: [green]✓ {p.api_base}[/green]")
            else:
                console.print(f"{spec.label}: [dim]not set[/dim]")
        else:
            has_key = bool(p.api_key)
            console.print(f"{spec.label}: {'[green]✓[/green]' if has_key else '[dim]not set[/dim]'}")

    if config.providers.endpoints:
        console.print(f"Named endpoints: {len(config.providers.endpoints)} configured")
        for name, ep in config.providers.endpoints.items():
            enabled = bool(getattr(ep, "enabled", True))
            models_count = len(ep.models or [])
            tag = "[green]enabled[/green]" if enabled else "[dim]disabled[/dim]"
            console.print(f"  - {name}: {tag} type={ep.type} models={models_count if models_count else '*'}")

    console.print("\n[bold]Tool & Skill Diagnostics[/bold]")
    active_profile = (config.profiles.active or "").strip()
    if active_profile:
        profile_ok = active_profile in config.profiles.items
        console.print(
            f"Profile: {active_profile} "
            f"{'[green]✓[/green]' if profile_ok else '[red](missing definition)[/red]'} "
            f"({len(config.profiles.items)} defined)"
        )
    elif config.profiles.items:
        console.print(f"Profile: [dim]none active[/dim] ({len(config.profiles.items)} defined)")

    builtins = config.tools.enabled or ["(all built-in tools enabled)"]
    console.print(f"Built-in tools: {', '.join(builtins)}")
    console.print(
        "Context budget: "
        f"history={config.agents.defaults.max_history_chars} chars, "
        f"memory={config.agents.defaults.max_memory_context_chars} chars, "
        f"background={config.agents.defaults.max_background_context_chars} chars, "
        f"inlineImage<={config.agents.defaults.max_inline_image_bytes} bytes"
    )
    total_chars_budget = (
        int(config.agents.defaults.max_history_chars)
        + int(config.agents.defaults.max_memory_context_chars)
        + int(config.agents.defaults.max_background_context_chars)
    )
    console.print(
        f"Context budget tokens (coarse): ~{estimate_tokens_from_chars(total_chars_budget)}"
    )
    console.print(
        "Runtime cleanup: "
        f"sessionCache={config.agents.defaults.session_cache_max_entries}, "
        f"gcEveryTurns={config.agents.defaults.gc_every_turns}, "
        f"promptCacheTTL={config.agents.defaults.system_prompt_cache_ttl_seconds}s, "
        f"bgCompaction={'on' if config.agents.defaults.auto_compact_background else 'off'}"
    )
    console.print(
        "Runtime limits: "
        f"turnTimeout={config.agents.defaults.turn_timeout_seconds}s, "
        f"inboundQueue={config.agents.defaults.inbound_queue_maxsize}, "
        f"outboundQueue={config.agents.defaults.outbound_queue_maxsize}"
    )
    snapshot = read_host_resource_snapshot()
    load1 = snapshot.get("load1")
    mem_used = snapshot.get("mem_used_percent")
    disk_used = snapshot.get("disk_used_percent")
    console.print(
        "Host snapshot: "
        f"load1={f'{load1:.2f}' if isinstance(load1, float) else 'n/a'}, "
        f"mem={f'{mem_used:.1f}%' if isinstance(mem_used, float) else 'n/a'}, "
        f"disk={f'{disk_used:.1f}%' if isinstance(disk_used, float) else 'n/a'}"
    )
    budget_alerts = collect_runtime_budget_alerts(config, snapshot)
    if budget_alerts:
        console.print(f"Budget alerts: [yellow]{len(budget_alerts)}[/yellow]")
        for alert in budget_alerts[:5]:
            level = str(alert.get("severity") or "warn").upper()
            msg = str(alert.get("message") or "").strip()
            hint = str(alert.get("suggestion") or "").strip()
            if not msg:
                continue
            console.print(f"  - [{level}] {msg}")
            if hint:
                console.print(f"    [dim]Fix: {hint}[/dim]")
    else:
        console.print("Budget alerts: [green]none[/green]")
    effective_exports_dir = get_exports_dir(config.tools.files_hub.exports_dir)
    configured_exports = (config.tools.files_hub.exports_dir or "").strip()
    console.print(
        "Files hub exports dir: "
        f"{effective_exports_dir} "
        f"({'default' if not configured_exports else f'configured={configured_exports}'})"
    )
    ccfg = config.tools.claude_code
    cc_tool_enabled = bool(ccfg.enabled)
    cc_tool_whitelisted = (not config.tools.enabled) or ("claude_code" in {t.lower() for t in config.tools.enabled})
    cc_tmux_ok = shutil.which(ccfg.tmux_command) is not None
    cc_cmd_ok = shutil.which(ccfg.command) is not None if "/" not in ccfg.command else Path(ccfg.command).expanduser().exists()
    console.print(
        "Claude Code tool: "
        f"{'[green]enabled[/green]' if cc_tool_enabled else '[dim]disabled[/dim]'}"
        f", whitelist={'yes' if cc_tool_whitelisted else 'no'}"
        f", tmux={'ok' if cc_tmux_ok else 'missing'}"
        f", claude={'ok' if cc_cmd_ok else 'missing'}"
    )
    if cc_tool_enabled:
        console.print(f"  autoInstallTmux: {'on' if ccfg.auto_install_tmux else 'off'}")
    if config.tools.aliases:
        console.print(f"Tool aliases: {len(config.tools.aliases)} configured")
        for alias_name, target_name in config.tools.aliases.items():
            if not str(alias_name).strip() or not str(target_name).strip():
                console.print(f"  - {alias_name} -> {target_name}: [red]invalid[/red]")
                continue
            if str(alias_name).strip() == str(target_name).strip():
                console.print(f"  - {alias_name} -> {target_name}: [yellow]noop alias[/yellow]")
                continue
            console.print(f"  - {alias_name} -> {target_name}")
    else:
        console.print("Tool aliases: [dim]none[/dim]")

    disabled_skills = config.skills.disabled or []
    console.print(
        f"Disabled skills: {', '.join(disabled_skills) if disabled_skills else '[dim]none[/dim]'}"
    )
    skill_loader = SkillsLoader(workspace, disabled_skills=set(disabled_skills))
    skill_report = skill_loader.build_availability_report()
    unavailable_skills = [s for s in skill_report if not bool(s["available"])]
    if skill_report:
        console.print(
            f"Skill availability: {len(skill_report) - len(unavailable_skills)}/{len(skill_report)} ready"
        )
        if unavailable_skills[:5]:
            for s in unavailable_skills[:5]:
                reason = s.get("requires") or "requirements missing"
                console.print(f"  - {s['name']}: [dim]{reason}[/dim]")
            if len(unavailable_skills) > 5:
                console.print(f"  [dim]... {len(unavailable_skills) - 5} more unavailable skills[/dim]")

    provider_mode = (config.tools.web.search.provider or "exa_mcp").strip().lower()
    if provider_mode not in {"exa_mcp", "disabled"}:
        provider_mode = "exa_mcp"
    enabled_servers = {s.lower() for s in config.tools.mcp_enabled_servers}
    disabled_servers = {s.lower() for s in config.tools.mcp_disabled_servers}
    configured_servers = list(config.tools.mcp_servers.keys())
    active_mcp_servers: dict[str, object] = {}
    for name in configured_servers:
        lname = name.lower()
        if enabled_servers and lname not in enabled_servers:
            continue
        if lname in disabled_servers:
            continue
        active_mcp_servers[name] = config.tools.mcp_servers[name]

    enabled_mcp_tools = {s.lower() for s in config.tools.mcp_enabled_tools}
    disabled_mcp_tools = {s.lower() for s in config.tools.mcp_disabled_tools}

    def _mcp_tool_filter_allows(server_name: str, tool_name: str) -> bool:
        aliases = {
            tool_name.lower(),
            f"mcp_{server_name}_{tool_name}".lower(),
            f"{server_name}.{tool_name}".lower(),
        }
        if enabled_mcp_tools and not (aliases & enabled_mcp_tools):
            return False
        if disabled_mcp_tools and (aliases & disabled_mcp_tools):
            return False
        return True

    active_exa_servers = [
        name for name, cfg in active_mcp_servers.items()
        if has_exa_search_mcp({name: cfg})
    ]
    exa_configured = bool(active_exa_servers)
    exa_web_search_exposed = any(
        _mcp_tool_filter_allows(name, "web_search_exa") for name in active_exa_servers
    )

    if provider_mode == "disabled":
        effective_search = "disabled"
    elif provider_mode == "exa_mcp":
        if exa_configured and exa_web_search_exposed:
            effective_search = "exa_mcp"
        elif exa_configured:
            effective_search = "exa_mcp (web_search_exa filtered out)"
        else:
            effective_search = "exa_mcp (missing exa mcp server config)"
    else:
        effective_search = "unknown"
    console.print(f"Web search provider: {provider_mode}  ->  {effective_search}")

    active_servers: list[str] = []
    for name in configured_servers:
        lname = name.lower()
        if enabled_servers and lname not in enabled_servers:
            continue
        if lname in disabled_servers:
            continue
        active_servers.append(name)
    console.print(
        f"MCP servers: {len(configured_servers)} configured, {len(active_servers)} active after filters"
    )
    if config.tools.mcp_enabled_tools or config.tools.mcp_disabled_tools:
        console.print(
            "MCP tool filters: "
            f"allow={len(config.tools.mcp_enabled_tools)} deny={len(config.tools.mcp_disabled_tools)}"
        )

    for name in configured_servers:
        cfg = config.tools.mcp_servers[name]
        lname = name.lower()
        if enabled_servers and lname not in enabled_servers:
            console.print(f"  - {name}: [dim]disabled by tools.mcpEnabledServers[/dim]")
            continue
        if lname in disabled_servers:
            console.print(f"  - {name}: [dim]disabled by tools.mcpDisabledServers[/dim]")
            continue
        if cfg.url:
            console.print(f"  - {name}: [green]remote[/green] {cfg.url}")
            continue
        if cfg.command:
            cmd_ok = shutil.which(cfg.command) is not None
            status_text = "[green]ready[/green]" if cmd_ok else "[red]missing command[/red]"
            console.print(f"  - {name}: {status_text} `{cfg.command}`")
            continue
        console.print(f"  - {name}: [red]invalid config[/red] (missing command/url)")

    warnings: list[str] = []
    if provider_mode == "exa_mcp" and not exa_configured:
        warnings.append("web_search provider=exa_mcp but Exa MCP server is not configured")
    if provider_mode == "exa_mcp" and exa_configured and not exa_web_search_exposed:
        warnings.append("Exa MCP is active but web_search_exa is filtered by MCP tool filters")
    exa_url = ((config.tools.mcp_servers.get("exa").url if config.tools.mcp_servers.get("exa") else "") or "").strip()
    has_exa_key_in_url = "exaapikey=" in exa_url.lower()
    if provider_mode == "exa_mcp" and exa_configured and not has_exa_key_in_url:
        warnings.append("Exa MCP URL does not include exaApiKey. For production, set exaApiKey=${EXA_API_KEY}.")
    if provider_mode == "exa_mcp" and exa_configured and has_exa_key_in_url and not os.getenv("EXA_API_KEY"):
        warnings.append("EXA_API_KEY is not set in environment files; Exa MCP may fail or be rate-limited.")
    if config.tools.enabled and "web_search" not in {t.lower() for t in config.tools.enabled}:
        warnings.append("web_search is excluded by tools.enabled")
    for alias_name, target_name in config.tools.aliases.items():
        if not str(alias_name).strip() or not str(target_name).strip():
            warnings.append(f"invalid tool alias entry: {alias_name!r} -> {target_name!r}")
        elif str(alias_name).strip() == str(target_name).strip():
            warnings.append(f"noop tool alias: {alias_name} -> {target_name}")
    if warnings:
        console.print("[yellow]Warnings:[/yellow]")
        for item in warnings:
            console.print(f"  - {item}")


def run_doctor(console: Any, logo: str) -> None:
    """Diagnose configuration/tooling issues and suggest fixes."""
    from lunaeclaw.core.context.skills import SkillsLoader
    from lunaeclaw.platform.config.loader import _discover_env_files, get_config_path, load_config
    from lunaeclaw.platform.config.migration_checker import collect_config_migration_findings
    from lunaeclaw.platform.providers.endpoint_validator import (
        collect_default_model_endpoint_findings,
    )
    from lunaeclaw.platform.utils.budget import (
        collect_runtime_budget_alerts,
        read_host_resource_snapshot,
    )
    from lunaeclaw.platform.utils.helpers import (
        get_env_dir,
        get_env_file,
        get_exports_dir,
        get_global_skills_path,
        get_mcp_home,
    )

    config_path = get_config_path()
    config = load_config()
    workspace = config.workspace_path

    console.print(f"{logo} lunaeclaw Doctor\n")
    console.print("[bold]Summary[/bold]")
    console.print(f"- Config path: {config_path} ({'exists' if config_path.exists() else 'missing'})")
    console.print(f"- Workspace: {workspace} ({'exists' if workspace.exists() else 'missing'})")
    console.print(f"- Active profile: {config.profiles.active or 'none'}")
    console.print(f"- Global skills dir: {get_global_skills_path()}")
    console.print(f"- MCP home: {get_mcp_home()}")
    console.print(f"- Env file: {get_env_file()} ({'exists' if get_env_file().exists() else 'missing'})")
    console.print(f"- Env dir: {get_env_dir()} ({'exists' if get_env_dir().exists() else 'missing'})")
    effective_exports_dir = get_exports_dir(config.tools.files_hub.exports_dir)
    configured_exports = (config.tools.files_hub.exports_dir or "").strip()
    console.print(
        f"- Exports dir: {effective_exports_dir} "
        f"({'default' if not configured_exports else f'configured={configured_exports}'})"
    )
    console.print(
        f"- Context budget: history={config.agents.defaults.max_history_chars}, "
        f"memory={config.agents.defaults.max_memory_context_chars}, "
        f"background={config.agents.defaults.max_background_context_chars}, "
        f"inlineImage={config.agents.defaults.max_inline_image_bytes}"
    )
    console.print(
        f"- Runtime cleanup: sessionCache={config.agents.defaults.session_cache_max_entries}, "
        f"gcEveryTurns={config.agents.defaults.gc_every_turns}, "
        f"promptCacheTTL={config.agents.defaults.system_prompt_cache_ttl_seconds}s, "
        f"bgCompaction={'on' if config.agents.defaults.auto_compact_background else 'off'}"
    )
    snapshot = read_host_resource_snapshot()
    load1 = snapshot.get("load1")
    mem_used = snapshot.get("mem_used_percent")
    disk_used = snapshot.get("disk_used_percent")
    console.print(
        "- Host snapshot: "
        f"load1={f'{load1:.2f}' if isinstance(load1, float) else 'n/a'}, "
        f"mem={f'{mem_used:.1f}%' if isinstance(mem_used, float) else 'n/a'}, "
        f"disk={f'{disk_used:.1f}%' if isinstance(disk_used, float) else 'n/a'}"
    )
    env_files = _discover_env_files()
    console.print(f"- Env helper files: {len(env_files)}")

    findings: list[tuple[str, str, str]] = []

    active_profile = (config.profiles.active or "").strip()
    if active_profile and active_profile not in config.profiles.items:
        findings.append((
            "warn",
            f"profiles.active='{active_profile}' but no matching definition in profiles.items",
            "Add profiles.items.<name> or clear profiles.active to disable profile overlay.",
        ))

    for item in collect_config_migration_findings(config_path):
        findings.append((item.severity, f"config migration: {item.message}", item.suggestion))

    provider_mode = (config.tools.web.search.provider or "exa_mcp").strip().lower()
    if provider_mode not in {"exa_mcp", "disabled"}:
        provider_mode = "exa_mcp"
    exa_cfg = config.tools.mcp_servers.get("exa")
    if provider_mode == "exa_mcp" and not exa_cfg:
        findings.append((
            "error",
            "web search provider is exa_mcp but MCP server 'exa' is not configured",
            "Add tools.mcpServers.exa.url = https://mcp.exa.ai/mcp?tools=web_search_exa,get_code_context_exa&exaApiKey=${EXA_API_KEY}",
        ))
    if provider_mode == "exa_mcp" and exa_cfg:
        exa_url = (getattr(exa_cfg, "url", "") or "").strip()
        has_exa_key_in_url = "exaapikey=" in exa_url.lower()
        if not has_exa_key_in_url:
            findings.append((
                "warn",
                "Exa MCP is configured without exaApiKey in URL",
                "Use .../mcp?...&exaApiKey=${EXA_API_KEY} and set EXA_API_KEY in ~/.lunaeclaw/.env or ~/.lunaeclaw/env/*.env.",
            ))
        elif not os.getenv("EXA_API_KEY"):
            findings.append((
                "warn",
                "EXA_API_KEY is not set in environment files",
                "Set EXA_API_KEY in ~/.lunaeclaw/.env (or env/*.env) so Exa MCP can authenticate reliably.",
            ))

    ccfg = config.tools.claude_code
    tool_enabled_names = {t.lower() for t in (config.tools.enabled or [])}
    if ccfg.enabled and tool_enabled_names and "claude_code" not in tool_enabled_names:
        findings.append((
            "warn",
            "tools.claudeCode.enabled=true but `claude_code` is excluded by tools.enabled",
            "Add `claude_code` to tools.enabled or clear tools.enabled to allow all built-in tools.",
        ))
    if ccfg.enabled and shutil.which(ccfg.tmux_command) is None:
        findings.append((
            "error",
            f"Claude Code tool is enabled but tmux command '{ccfg.tmux_command}' is not found",
            (
                "tmux will be auto-installed on startup if tools.claudeCode.autoInstallTmux=true; "
                "otherwise install it manually (e.g. `brew install tmux`) or set tools.claudeCode.tmuxCommand correctly."
            ),
        ))
    if ccfg.enabled:
        claude_exists = shutil.which(ccfg.command) is not None if "/" not in ccfg.command else Path(ccfg.command).expanduser().exists()
        if not claude_exists:
            findings.append((
                "error",
                f"Claude Code tool is enabled but command '{ccfg.command}' is not found",
                "Install Claude Code CLI or set tools.claudeCode.command to the executable path.",
            ))

    doc_cfg = config.tools.mcp_servers.get("docloader")
    if doc_cfg:
        if doc_cfg.command and shutil.which(doc_cfg.command) is None:
            findings.append((
                "error",
                f"docloader MCP command '{doc_cfg.command}' not found",
                "Install uv (e.g. `brew install uv`) so `uvx` can launch the document loader MCP.",
            ))
    else:
        findings.append((
            "warn",
            "document parsing MCP is not configured (PDF/Word/PPT/Excel/image parsing will rely on limited built-ins)",
            "Add tools.mcpServers.docloader (uvx awslabs.document-loader-mcp-server@latest) and aliases doc_read/image_read.",
        ))

    if config.tools.aliases:
        for alias_name, target_name in config.tools.aliases.items():
            a = str(alias_name).strip()
            target = str(target_name).strip()
            if not a or not target:
                findings.append(("warn", f"invalid tool alias entry: {alias_name!r} -> {target_name!r}", "Remove empty alias keys/values."))
            elif a == target:
                findings.append(("warn", f"noop tool alias: {a} -> {target}", "Delete the alias or point it to a different target tool."))

    active_model = str(config.agents.defaults.model or "")
    for item in collect_default_model_endpoint_findings(config):
        findings.append((item.severity, item.problem, item.fix))

    if active_model.startswith("custom/") and "custom" not in config.providers.endpoints:
        if not config.providers.custom.api_base:
            findings.append((
                "warn",
                "default model uses custom/* but providers.custom.apiBase is empty",
                "Set providers.custom.apiBase to your OpenAI-compatible endpoint.",
            ))
        if not config.providers.custom.api_key:
            findings.append((
                "warn",
                "default model uses custom/* but providers.custom.apiKey is empty (or env placeholder not resolved)",
                "Set providers.custom.apiKey or use ${ENV_VAR} with a helper env file under ~/.lunaeclaw/.env or ~/.lunaeclaw/env/*.env.",
            ))
        elif "${" in str(config.providers.custom.api_key):
            findings.append((
                "warn",
                "providers.custom.apiKey still contains an unresolved ${ENV_VAR} placeholder",
                "Check ~/.lunaeclaw/.env or ~/.lunaeclaw/env/*.env and ensure the referenced variable name exists.",
            ))
        if config.providers.custom.api_base and "${" in str(config.providers.custom.api_base):
            findings.append((
                "warn",
                "providers.custom.apiBase still contains an unresolved ${ENV_VAR} placeholder",
                "Check your helper env files and variable names for MY_API_BASE-like values.",
            ))

    for alert in collect_runtime_budget_alerts(config, snapshot):
        severity = str(alert.get("severity") or "warn").lower()
        findings.append((
            "error" if severity == "error" else "warn",
            f"runtime budget: {str(alert.get('message') or '').strip()}",
            str(alert.get("suggestion") or "Tune agent runtime budgets in Models & APIs."),
        ))

    disabled_skills = set(config.skills.disabled or [])
    loader = SkillsLoader(workspace, disabled_skills=disabled_skills)
    for row in loader.build_availability_report():
        if bool(row["available"]):
            continue
        reason = str(row.get("requires") or "requirements missing")
        fix = "Install the missing CLI/env requirement or add the skill to skills.disabled."
        if "CLI: gh" in reason:
            fix = "Install GitHub CLI (`brew install gh`) and run `gh auth login`, or disable the github skill."
        elif "CLI: uvx" in reason or "CLI: uv" in reason:
            fix = "Install uv (`brew install uv`) to enable document/tool MCP skills."
        findings.append(("warn", f"skill '{row['name']}' unavailable: {reason}", fix))

    console.print("\n[bold]Findings[/bold]")
    if not findings:
        console.print("[green]No blocking issues found.[/green]")
    else:
        for severity, problem, fix in findings:
            color = "red" if severity == "error" else "yellow"
            console.print(f"- [{color}]{severity.upper()}[/{color}] {problem}")
            console.print(f"  Fix: {fix}")

    console.print("\n[bold]Recommended next actions[/bold]")
    console.print("1. Run `lunaeclaw onboard` to refresh config and workspace templates with current defaults.")
    console.print("2. Keep `profiles.active=cn_dev` for lightweight local use; switch to `research` when you need more tools.")
    console.print("3. Test attachments with `doc_read` / `image_read` after enabling docloader MCP.")
