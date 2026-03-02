"""Media/files page renderer for Web UI."""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any

from nanobot.utils.helpers import get_exports_dir, get_media_dir
from nanobot.webui.common import _MEDIA_PAGE_SIZE, _list_media_rows, _list_store_rows
from nanobot.webui.i18n import ui_copy as _ui_copy
from nanobot.webui.i18n import ui_term as _ui_term


def render_media(handler: Any, *, msg: str = "", err: str = "", media_page: int = 1, exports_page: int = 1) -> None:
    """Render media/files page."""
    cfg = handler._load_config()
    def t(en: str, zh_cn: str) -> str:
        return _ui_copy(handler._ui_lang, en, zh_cn)

    def term(key: str) -> str:
        return _ui_term(handler._ui_lang, key)
    configured_exports_dir = (cfg.tools.files_hub.exports_dir or "").strip()
    effective_exports_dir = get_exports_dir(configured_exports_dir)

    media_rows = _list_media_rows()
    export_rows = _list_store_rows(effective_exports_dir)

    def _slice_page(rows: list[dict[str, Any]], page: int) -> tuple[list[dict[str, Any]], int, int]:
        total_pages = max(1, (len(rows) + _MEDIA_PAGE_SIZE - 1) // _MEDIA_PAGE_SIZE)
        current = min(max(1, page), total_pages)
        start = (current - 1) * _MEDIA_PAGE_SIZE
        return rows[start : start + _MEDIA_PAGE_SIZE], current, total_pages

    media_page_rows, media_page, media_total_pages = _slice_page(media_rows, media_page)
    export_page_rows, exports_page, exports_total_pages = _slice_page(export_rows, exports_page)

    def _media_tab_url(*, m_page: int, e_page: int) -> str:
        return handler._url_with_lang(f"/media?media_page={m_page}&exports_page={e_page}")

    def _render_pager(scope: str, current: int, total: int) -> str:
        if total <= 1:
            return ""
        other = exports_page if scope == "media" else media_page

        def _page_url(target: int) -> str:
            if scope == "media":
                return _media_tab_url(m_page=target, e_page=other)
            return _media_tab_url(m_page=other, e_page=target)

        parts: list[str] = []
        if current > 1:
            parts.append(f'<a class="btn subtle" href="{_page_url(current - 1)}">← {term("prev")}</a>')
        else:
            parts.append(f'<span class="btn subtle" style="opacity:.45; cursor:default;">← {term("prev")}</span>')
        start = max(1, current - 2)
        end = min(total, current + 2)
        if start > 1:
            parts.append(f'<a class="btn subtle" href="{_page_url(1)}">1</a>')
        if start > 2:
            parts.append('<span class="muted">…</span>')
        for idx in range(start, end + 1):
            klass = "btn primary" if idx == current else "btn subtle"
            parts.append(f'<a class="{klass}" href="{_page_url(idx)}">{idx}</a>')
        if end < total - 1:
            parts.append('<span class="muted">…</span>')
        if end < total:
            parts.append(f'<a class="btn subtle" href="{_page_url(total)}">{total}</a>')
        if current < total:
            parts.append(f'<a class="btn subtle" href="{_page_url(current + 1)}">{term("next")} →</a>')
        else:
            parts.append(f'<span class="btn subtle" style="opacity:.45; cursor:default;">{term("next")} →</span>')
        return f'<div class="row" style="margin-top:10px">{"".join(parts)}</div>'

    def _render_store_block(
        *,
        scope: str,
        title: str,
        desc: str,
        rows_all: list[dict[str, Any]],
        rows_page: list[dict[str, Any]],
        current_page: int,
        total_pages: int,
        root_dir: Path,
    ) -> str:
        table_rows = []
        for r in rows_page:
            size_kb = f"{r['size']/1024:.1f} KB"
            from datetime import datetime

            mtime = datetime.fromtimestamp(r["mtime"]).strftime("%Y-%m-%d %H:%M:%S")
            table_rows.append(
                f"""
<tr>
  <td><input type="checkbox" name="selected_name" value="{escape(r['name'])}"></td>
  <td><code>{escape(r['display_name'])}</code><div class="muted mono">{escape(r['name'])}</div></td>
  <td>{escape(size_kb)}</td>
  <td class="small">{escape(mtime)}</td>
  <td class="mono small">{escape(r['path'])}</td>
  <td>
    <button class="btn icon-btn" type="submit" name="action" value="delete_one:{escape(r['name'])}" onclick="return confirm('{t('Delete this file?', '删除该文件？')}');">
      <span aria-hidden="true">🗑</span>{term("delete")}
    </button>
  </td>
</tr>
"""
            )
        pager = _render_pager(scope, current_page, total_pages)
        return f"""
<section class="card" style="margin-top:14px">
  <h2>{escape(title)}</h2>
  <table>
    <tr><th>{t("Directory", "目录")}</th><td><code>{escape(str(root_dir))}</code></td></tr>
    <tr><th>{t("File count", "文件数")}</th><td>{len(rows_all)}</td></tr>
    <tr><th>{t("Page", "分页")}</th><td>{term("page")} {current_page}/{total_pages} · {term("showing")} {len(rows_page)} / {len(rows_all)}</td></tr>
  </table>
  <div class="muted" style="margin-top:8px">{escape(desc)}</div>
  <form method="post" data-scope="{escape(scope)}" style="margin-top:14px">
    <input type="hidden" name="scope" value="{escape(scope)}">
    <input type="hidden" name="media_page" value="{media_page}">
    <input type="hidden" name="exports_page" value="{exports_page}">
    <div class="row" style="margin-bottom:10px">
      <button class="btn subtle icon-btn" type="button" onclick="nbSelectAll(this.form, true)"><span aria-hidden="true">☑</span>{term("select_all")}</button>
      <button class="btn subtle icon-btn" type="button" onclick="nbSelectAll(this.form, false)"><span aria-hidden="true">☐</span>{term("clear")}</button>
      <button class="btn warn icon-btn" type="submit" name="action" value="delete_selected" onclick="return confirm('{t('Delete selected files?', '删除选中文件？')}');"><span aria-hidden="true">🗑</span>{t("Delete selected", "删除选中项")}</button>
      <button class="btn subtle icon-btn" type="submit" name="action" value="refresh"><span aria-hidden="true">↻</span>{term("refresh")}</button>
    </div>
    <table>
      <tr><th></th><th>{t("Display name / filename", "显示名 / 文件名")}</th><th>{t("Size", "大小")}</th><th>{t("Modified", "修改时间")}</th><th>{t("Path", "路径")}</th><th></th></tr>
      {''.join(table_rows) or f'<tr><td colspan="6" class="muted">{t("Directory is empty", "目录为空")}</td></tr>'}
    </table>
    {pager}
  </form>
</section>
"""

    media_dir = get_media_dir()
    exports_dir = effective_exports_dir
    body = f"""
<div class="grid cols-2">
  <section class="card">
    <h2>{t("File Operations Overview", "文件处理总览")}</h2>
    <table>
      <tr><th>{t("Uploaded attachments (media)", "上传附件（media）")}</th><td>{len(media_rows)}</td></tr>
      <tr><th>{t("Generated outputs (exports)", "生成输出（exports）")}</th><td>{len(export_rows)}</td></tr>
      <tr><th>{t("Route hint", "路由建议")}</th><td><code>files_hub(scope=...)</code> {t("for unified management", "统一管理")}</td></tr>
    </table>
    <div class="muted" style="margin-top:8px">{t("Use input(media) / process(workspace) / output(exports) layering to reduce accidental deletion and duplicated tools.", "遵循“输入(media) / 处理(workspace) / 输出(exports)”分层，减少误删原件和工具重复。")}</div>
  </section>
  <section class="card">
    <h2>{t("In-chat File Commands (Recommended)", "聊天内文件管理命令（推荐）")}</h2>
    <ul class="list small">
      <li>{t("List (recommended)", "列出（推荐）")}：<code>files_hub(action=&quot;list&quot;, scope=&quot;media&quot;)</code></li>
      <li>{term("delete")}：<code>files_hub(action=&quot;delete&quot;, scope=&quot;media&quot;, names=[...])</code></li>
      <li>{t("Export list", "导出目录")}：<code>files_hub(action=&quot;list&quot;, scope=&quot;exports&quot;)</code></li>
      <li>{t("If TG filename looks random, check", "如果 TG 文件名看起来像随机串，请查看")} <code>displayName</code>（{t("new uploads try to keep original filename/extension", "新上传文件会尽量保留原文件名/后缀")}）</li>
    </ul>
  </section>
</div>
<form method="post" class="card" style="margin-top:14px">
  <h2>{t("Exports Directory", "导出目录设置")}</h2>
  <input type="hidden" name="media_page" value="{media_page}">
  <input type="hidden" name="exports_page" value="{exports_page}">
  <div class="field">
    <label>{t("tools.filesHub.exportsDir (empty = default", "tools.filesHub.exportsDir（留空=默认")} <code>~/.nanobot/exports</code>{t(")", "）")}</label>
    <input name="exports_dir" value="{escape(configured_exports_dir)}" placeholder="{t('Example: /data/nanobot-exports or exports', '例如：/data/nanobot-exports 或 exports')}">
  </div>
  <div class="row">
    <button class="btn primary icon-btn" type="submit" name="action" value="save_exports_dir"><span aria-hidden="true">💾</span>{t("Save exports directory", "保存导出目录")}</button>
    <button class="btn subtle icon-btn" type="submit" name="action" value="save_exports_dir_default"><span aria-hidden="true">↺</span>{t("Reset to default", "恢复默认目录")}</button>
  </div>
</form>
{_render_store_block(
    scope="media",
    title=t("Media Directory (Uploaded Attachments)", "媒体目录（上传附件）"),
    desc=t("This directory stores attachments downloaded from chat channels (TG/Discord/Feishu/etc). Review before deletion.", "这里是聊天渠道（TG/Discord/Feishu 等）下载的附件目录。建议先查看再删除。"),
    rows_all=media_rows,
    rows_page=media_page_rows,
    current_page=media_page,
    total_pages=media_total_pages,
    root_dir=media_dir,
)}
{_render_store_block(
    scope="exports",
    title=t("Exports Directory (Generated Files)", "导出目录（生成文件）"),
    desc=t("Store generated result files here (txt/docx/pdf/xlsx/etc) for unified download and cleanup.", "这里建议存放机器人生成的结果文件（如 txt/docx/pdf/xlsx 等），便于统一下载和清理。"),
    rows_all=export_rows,
    rows_page=export_page_rows,
    current_page=exports_page,
    total_pages=exports_total_pages,
    root_dir=exports_dir,
)}
"""
    handler._send_html(200, handler._page(t("Media", "媒体文件"), body, tab="/media", msg=msg, err=err))
