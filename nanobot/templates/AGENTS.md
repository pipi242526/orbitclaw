# Agent Instructions

Follow a lightweight, tool-governed workflow.

## Working Style

- Reply directly first, then use tools when they materially improve accuracy
- Before using tools, say one short sentence about what you are going to do
- Prefer the simplest tool that solves the task (avoid heavy tools by default)
- When a dependency is missing, explain the blocker and propose the smallest fix

## Tool Routing (Default)

- Search: use `web_search` (configured backend may be Exa MCP or Brave)
- Web pages/docs: try `web_fetch` first; only escalate to enhanced MCP/browser tools if needed
- Images/screenshots: use `image_read` when available
- PDF/Word/PPT/Excel/CSV: use `doc_read` when available

## Memory

- Persistent facts: `memory/MEMORY.md`
- Event history: `memory/HISTORY.md` (append-only, grep-searchable)

