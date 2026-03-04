"""Feishu interactive card element builders."""

from __future__ import annotations

import re

_TABLE_RE = re.compile(
    r"((?:^[ \t]*\|.+\|[ \t]*\n)(?:^[ \t]*\|[-:\s|]+\|[ \t]*\n)(?:^[ \t]*\|.+\|[ \t]*\n?)+)",
    re.MULTILINE,
)
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
_CODE_BLOCK_RE = re.compile(r"(```[\s\S]*?```)", re.MULTILINE)


def parse_feishu_md_table(table_text: str) -> dict | None:
    """Parse a markdown table into one Feishu table element."""
    lines = [line.strip() for line in table_text.strip().split("\n") if line.strip()]
    if len(lines) < 3:
        return None

    def split_row(row_text: str) -> list[str]:
        return [cell.strip() for cell in row_text.strip("|").split("|")]

    headers = split_row(lines[0])
    rows = [split_row(line) for line in lines[2:]]
    columns = [
        {"tag": "column", "name": f"c{i}", "display_name": header, "width": "auto"}
        for i, header in enumerate(headers)
    ]
    return {
        "tag": "table",
        "page_size": len(rows) + 1,
        "columns": columns,
        "rows": [{f"c{i}": row[i] if i < len(row) else "" for i in range(len(headers))} for row in rows],
    }


def split_feishu_headings(content: str) -> list[dict]:
    """Split markdown content by headings, preserving fenced code blocks."""
    protected = content
    code_blocks: list[str] = []
    for match in _CODE_BLOCK_RE.finditer(content):
        code_blocks.append(match.group(1))
        protected = protected.replace(match.group(1), f"\x00CODE{len(code_blocks)-1}\x00", 1)

    elements: list[dict] = []
    last_end = 0
    for match in _HEADING_RE.finditer(protected):
        before = protected[last_end : match.start()].strip()
        if before:
            elements.append({"tag": "markdown", "content": before})
        text = match.group(2).strip()
        elements.append(
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**{text}**",
                },
            }
        )
        last_end = match.end()
    remaining = protected[last_end:].strip()
    if remaining:
        elements.append({"tag": "markdown", "content": remaining})

    for i, code_block in enumerate(code_blocks):
        for element in elements:
            if element.get("tag") == "markdown":
                element["content"] = element["content"].replace(f"\x00CODE{i}\x00", code_block)

    return elements or [{"tag": "markdown", "content": content}]


def build_feishu_card_elements(content: str) -> list[dict]:
    """Split message content into Feishu card elements."""
    elements: list[dict] = []
    last_end = 0
    for match in _TABLE_RE.finditer(content):
        before = content[last_end : match.start()]
        if before.strip():
            elements.extend(split_feishu_headings(before))
        elements.append(parse_feishu_md_table(match.group(1)) or {"tag": "markdown", "content": match.group(1)})
        last_end = match.end()
    remaining = content[last_end:]
    if remaining.strip():
        elements.extend(split_feishu_headings(remaining))
    return elements or [{"tag": "markdown", "content": content}]
