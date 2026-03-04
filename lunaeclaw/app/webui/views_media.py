"""Media/files page renderer for Web UI."""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any

from lunaeclaw.app.webui.common import _MEDIA_PAGE_SIZE, _list_media_rows, _list_store_rows
from lunaeclaw.app.webui.i18n import ui_copy as _ui_copy
from lunaeclaw.app.webui.i18n import ui_term as _ui_term
from lunaeclaw.app.webui.icons import icon_svg
from lunaeclaw.platform.utils.helpers import get_exports_dir, get_media_dir


def render_media(handler: Any, *, msg: str = "", err: str = "", media_page: int = 1, exports_page: int = 1) -> None:
    """Render media/files page."""
    cfg = handler._load_config()
    zh = handler._ui_lang == "zh-CN"

    def t(en: str, zh_cn: str) -> str:
        return _ui_copy(handler._ui_lang, en, zh_cn)

    def term(key: str) -> str:
        return _ui_term(handler._ui_lang, key)
    icon_delete = icon_svg("delete")
    icon_refresh = icon_svg("refresh")
    icon_save = icon_svg("save")
    icon_reset = icon_svg("reset")
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
            parts.append(f'<span class="btn subtle is-disabled">← {term("prev")}</span>')
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
            parts.append(f'<span class="btn subtle is-disabled">{term("next")} →</span>')
        return f'<div class="row mt-10">{"".join(parts)}</div>'

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
        show_refresh: bool,
    ) -> str:
        table_rows = []
        selected_label = "已选" if zh else "Selected"
        delete_with_count = "删除选中" if zh else "Delete selected"
        confirm_delete_prefix = "确认删除所选文件？数量：" if zh else "Delete selected files? Count: "
        no_selection_warning = "请先选择至少一个文件" if zh else "Select at least one file first"
        for r in rows_page:
            size_kb = f"{r['size']/1024:.1f} KB"
            from datetime import datetime

            mtime = datetime.fromtimestamp(r["mtime"]).strftime("%Y-%m-%d %H:%M:%S")
            table_rows.append(
                f"""
<tr class="file-row" data-row-select="1">
  <td><input type="checkbox" name="selected_name" value="{escape(r['name'])}" data-role="row-checkbox"></td>
  <td><code>{escape(r['display_name'])}</code><div class="muted mono">{escape(r['name'])}</div></td>
  <td>{escape(size_kb)}</td>
  <td class="small">{escape(mtime)}</td>
  <td class="mono small">{escape(r['path'])}</td>
  <td>
    <button class="btn danger icon-btn" type="submit" name="action" value="delete_one:{escape(r['name'])}" onclick="return confirm('{t('Delete this file?', '删除该文件？')}');">
      {icon_delete}{term("delete")}
    </button>
  </td>
</tr>
"""
            )
        pager = _render_pager(scope, current_page, total_pages)
        refresh_html = (
            f'<button class="refresh-mini" type="submit" name="action" value="refresh" title="{term("refresh")}" '
            f'aria-label="{term("refresh")}">{icon_refresh}</button>'
            if show_refresh
            else ""
        )
        desc_html = f'<div class="muted mt-8">{escape(desc)}</div>' if desc else ""
        return f"""
<section class="card mt-14">
  <h2>{escape(title)}</h2>
  <table>
    <tr><th>{t("Directory", "目录")}</th><td><code>{escape(str(root_dir))}</code></td></tr>
    <tr><th>{t("File count", "文件数")}</th><td>{len(rows_all)}</td></tr>
    <tr><th>{t("Page", "分页")}</th><td>{term("page")} {current_page}/{total_pages} · {term("showing")} {len(rows_page)} / {len(rows_all)}</td></tr>
  </table>
  {desc_html}
  <form method="post" data-scope="{escape(scope)}" data-select-form="1" class="mt-14">
    <input type="hidden" name="scope" value="{escape(scope)}">
    <input type="hidden" name="media_page" value="{media_page}">
    <input type="hidden" name="exports_page" value="{exports_page}">
    <div class="row glass-toolbar mb-10">
      <span class="glass-chip">{selected_label}: <strong data-role="selected-count">0</strong></span>
      <button class="btn danger icon-btn" type="submit" name="action" value="delete_selected" data-role="delete-selected" data-confirm-prefix="{escape(confirm_delete_prefix)}" data-empty-tip="{escape(no_selection_warning)}" disabled>{icon_delete}{delete_with_count}</button>
    </div>
    <table>
      <tr><th><input type="checkbox" data-role="select-all-toggle" aria-label="{term('select_all')}"></th><th>{t("Display name / filename", "显示名 / 文件名")} {refresh_html}</th><th>{t("Size", "大小")}</th><th>{t("Modified", "修改时间")}</th><th>{t("Path", "路径")}</th><th></th></tr>
      {''.join(table_rows) or f'<tr><td colspan="6" class="muted">{t("Directory is empty", "目录为空")}</td></tr>'}
    </table>
    {pager}
  </form>
</section>
"""

    media_dir = get_media_dir()
    exports_dir = effective_exports_dir
    body = f"""
<style>
  .btn.is-disabled {{
    opacity: .45;
    cursor: default;
    pointer-events: none;
  }}
  .glass-toolbar .btn[disabled] {{
    opacity: .45;
    cursor: not-allowed;
    transform: none;
    box-shadow: none;
  }}
  .refresh-mini {{
    margin-left: 6px;
    width: 24px;
    height: 24px;
    padding: 0;
    border: 1px solid transparent;
    border-radius: 8px;
    background: transparent;
    color: var(--muted);
    vertical-align: middle;
    line-height: 1;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    box-shadow: none;
  }}
  .refresh-mini .ui-icon {{
    width: 14px;
    height: 14px;
  }}
  .refresh-mini:hover {{
    border-color: var(--line);
    background: var(--subtle-bg);
    color: var(--ink);
  }}
  tr.file-row {{
    cursor: pointer;
  }}
  tr.file-row.is-selected td {{
    background: color-mix(in srgb, var(--accent) 11%, transparent);
  }}
</style>
<form method="post" class="card mt-14">
  <h2>{t("Exports Directory", "导出目录设置")}</h2>
  <input type="hidden" name="media_page" value="{media_page}">
  <input type="hidden" name="exports_page" value="{exports_page}">
  <div class="field">
    <label>{t("tools.filesHub.exportsDir (empty = default", "tools.filesHub.exportsDir（留空=默认")} <code>~/.lunaeclaw/exports</code>{t(")", "）")}</label>
    <input name="exports_dir" value="{escape(configured_exports_dir)}" placeholder="{t('Example: /data/lunaeclaw-exports or exports', '例如：/data/lunaeclaw-exports 或 exports')}">
  </div>
  <div class="row">
    <button class="btn primary icon-btn" type="submit" name="action" value="save_exports_dir">{icon_save}{t("Save exports directory", "保存导出目录")}</button>
    <button class="btn subtle icon-btn" type="submit" name="action" value="save_exports_dir_default">{icon_reset}{t("Reset to default", "恢复默认目录")}</button>
  </div>
</form>
{_render_store_block(
    scope="media",
    title=t("Media Directory (Uploaded Attachments)", "媒体目录（上传附件）"),
    desc="",
    rows_all=media_rows,
    rows_page=media_page_rows,
    current_page=media_page,
    total_pages=media_total_pages,
    root_dir=media_dir,
    show_refresh=True,
)}
{_render_store_block(
    scope="exports",
    title=t("Exports Directory (Generated Files)", "导出目录（生成文件）"),
    desc="",
    rows_all=export_rows,
    rows_page=export_page_rows,
    current_page=exports_page,
    total_pages=exports_total_pages,
    root_dir=exports_dir,
    show_refresh=True,
)}
<script>
  (function bindMediaSelection() {{
    for (const form of document.querySelectorAll('form[data-select-form="1"]')) {{
      const checkboxes = Array.from(form.querySelectorAll('input[data-role="row-checkbox"]'));
      const countNode = form.querySelector('[data-role="selected-count"]');
      const deleteBtn = form.querySelector('[data-role="delete-selected"]');
      const toggleAll = form.querySelector('[data-role="select-all-toggle"]');
      const refreshView = () => {{
        let count = 0;
        for (const cb of checkboxes) {{
          const row = cb.closest('tr');
          if (cb.checked) {{
            count += 1;
            row && row.classList.add('is-selected');
          }} else {{
            row && row.classList.remove('is-selected');
          }}
        }}
        if (countNode) countNode.textContent = String(count);
        if (deleteBtn) deleteBtn.disabled = count === 0;
        if (toggleAll) toggleAll.checked = checkboxes.length > 0 && count === checkboxes.length;
      }};
      for (const cb of checkboxes) {{
        cb.addEventListener('change', refreshView);
      }}
      for (const row of form.querySelectorAll('tr[data-row-select="1"]')) {{
        row.addEventListener('click', (e) => {{
          const t = e.target;
          if (t instanceof Element && (t.closest('button') || t.closest('a') || t.closest('input[type="checkbox"]'))) return;
          const cb = row.querySelector('input[data-role="row-checkbox"]');
          if (!cb) return;
          cb.checked = !cb.checked;
          refreshView();
        }});
      }}
      if (toggleAll) toggleAll.addEventListener('change', () => {{
        for (const cb of checkboxes) cb.checked = toggleAll.checked;
        refreshView();
      }});
      form.addEventListener('submit', (e) => {{
        const submitter = e.submitter;
        if (!(submitter instanceof HTMLElement)) return;
        if (submitter.getAttribute('data-role') !== 'delete-selected') return;
        const selected = checkboxes.filter((x) => x.checked).length;
        if (selected <= 0) {{
          e.preventDefault();
          const tip = submitter.getAttribute('data-empty-tip') || 'Select at least one file first';
          window.alert(tip);
          return;
        }}
        const prefix = submitter.getAttribute('data-confirm-prefix') || 'Delete selected files? Count: ';
        if (!window.confirm(prefix + selected)) {{
          e.preventDefault();
        }}
      }});
      refreshView();
    }}
  }})();
</script>
"""
    handler._send_html(200, handler._page(t("Media", "媒体文件"), body, tab="/media", msg=msg, err=err))
