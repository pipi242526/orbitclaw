# Development Rules (orbitclaw-s)

**Language / 语言**: [English](DEVELOPMENT_RULES.md) | [简体中文](DEVELOPMENT_RULES.zh-CN.md)

This fork follows a pragmatic, lightweight engineering policy.

## 0) Project Guardrails (Default Rules)

1. Resource law:
   - Every release should keep explicit budget ceilings for free memory, per-turn token usage, tool timeout, and queue length.
   - New features should include budget impact notes; urgent exceptions are allowed with follow-up tasks.
2. Output law:
   - Final output must follow the configured language strategy.
   - Internal tool/MCP invocation details must not leak to end users by default.
   - Failures must include reason and actionable fix suggestions.
3. Interface law:
   - Keep one unified message contract (`reply_to`, `actions`, `attachments`).
   - Channel adapters should mainly map protocol differences; business logic should stay in core/runtime services.
4. Configuration law:
   - Environment variables first, plaintext secrets minimized.
   - Every config mutation path should be reversible (clear fallback or rollback path).
5. Extension law:
   - New channel / MCP / skill integrations should be plug-in style and avoid invasive core-loop rewrites.
6. Evolution law:
   - Every release should include an upstream patch audit record with explicit accept/reject/defer decisions.
7. Quality law:
   - New/modified code must include focused tests and pass incremental lint checks.
   - Legacy lint debt is allowed temporarily but must never increase unnoticed.

### Exceptions

Temporary exceptions are allowed when needed for emergency fixes or release timing, but each exception should include:

1. reason and impact scope
2. rollback or mitigation path
3. follow-up issue/commit target

## 1) Priorities

1. Bot core behavior first (gateway/chat/tools), WebUI second.
2. Reliability before feature breadth.
3. Keep architecture simple and composable.

## 2) Design Principles

1. One capability, one primary tool entrypoint.
2. Prefer configuration over hardcoded branching.
3. Keep optional integrations optional (MCP/dependencies should degrade gracefully).
4. Remove compatibility shims once migration is complete.

## 3) File Handling Policy

1. `~/.orbitclaw/media` = inbound attachments (user-uploaded source files).
2. `workspace` = working/intermediate files.
3. `exports` = generated outputs (reports, transformed files, final artifacts).
4. Use `files_hub` for listing/deleting in `media|exports`.
5. Use `export_file` for writing generated outputs.

## 4) Security Defaults

1. Restrict exposure by default (`allowFrom`, path-token WebUI access).
2. Never expose secrets in UI text or logs.
3. Avoid claiming success without tool-confirmed output.

## 5) Language & Search

1. Final answer language follows user preference/config.
2. Region-specific topics should support cross-lingual search hints.
3. Tool outputs can be multilingual; final answer should still obey language policy.

## 6) Testing & Release Discipline

1. Add focused tests for each new tool or behavior change.
2. Run lightweight regression before deployment.
3. Use small, reviewable commits and clear rollback path.

## 7) Non-goals

1. No heavy framework expansion without a concrete production need.
2. No duplicate tools for the same job.
3. No permanent compatibility code if active usage has migrated.
