---
name: attachment-analyzer
description: Analyze chat attachments (images, PDF, Word, PowerPoint, Excel/CSV) using MCP document/image tools and return concise findings plus recommended next steps.
category: analysis
lang: zh,en
requires_cli: uvx
metadata: {"nanobot":{"emoji":"📎"}}
---

# Attachment Analyzer

Use this skill when the user sends or references attachments and asks to:

- summarize a file
- extract key points
- read PDF / Word / PPT / spreadsheet
- analyze an image / screenshot / chart
- compare multiple attachments

## Goal

Produce a useful result quickly with a stable structure:

1. What the file is
2. Key findings
3. Risks / missing data (if any)
4. Suggested next actions

## Recommended Tools

Prefer MCP document/image tools when available (for example):

- `read_document` (PDF/DOCX/PPT/XLS/XLSX/TXT)
- `read_image` (image analysis / OCR-friendly image loading)

If aliases exist, use the alias names configured by the project (for example `doc_read`, `image_read`).

## Workflow

1. Identify attachment paths from the user message/context.
2. Group by file type:
   - image (`png/jpg/jpeg/webp/gif`)
   - document (`pdf/doc/docx/ppt/pptx/xls/xlsx/csv/txt`)
3. For each file:
   - images: use image tool first
   - documents: use document tool first
   - if tool unavailable, fall back to built-in capabilities (e.g. image vision) or explain limitation clearly
4. Summarize in Chinese by default unless the user asks another language.
5. End with a practical next-step suggestion.

## Output Template (Chinese, concise)

```markdown
## 文件识别
- 文件A: 类型 / 主题（推测）

## 关键信息
- ...

## 风险或不确定点
- ...

## 建议下一步
1. ...
2. ...
```

## Guardrails

- Do not fabricate unreadable content.
- If parsing fails, report the exact file and suggest a retry path (another tool / file format conversion).
- For spreadsheets, summarize sheet names / columns / notable values before deep analysis.
