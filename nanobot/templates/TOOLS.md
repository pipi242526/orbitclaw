# Tools & Skills Policy

This workspace uses a lightweight default setup.

## Core Built-in Tools (usually keep enabled)

- `read_file`, `write_file`, `edit_file`, `list_dir`, `exec`
- `web_search`, `web_fetch`
- `message`, `spawn`

## Optional MCP Enhancements

- Exa MCP: web search and code/document search context
- Document loader MCP: `doc_read` / `image_read` for attachments
- Optional web fetch enhancement MCP (enable only when built-in `web_fetch` fails)

## Skills Strategy

- Keep always-useful skills enabled (e.g. memory, cron, github if `gh` exists)
- Hide skills that lack local dependencies
- Prefer profiles to switch bundles instead of editing many fields manually

