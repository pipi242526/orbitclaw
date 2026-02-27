# Development Rules (nanobot-s)

This fork follows a pragmatic, lightweight engineering policy.

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

1. `~/.nanobot/media` = inbound attachments (user-uploaded source files).
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

