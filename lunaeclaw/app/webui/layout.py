"""Shared WebUI layout renderer."""

from __future__ import annotations

from lunaeclaw.app.webui.html_utils import escape
from lunaeclaw.app.webui.icons import icon_svg, logo_svg


def render_page_shell(
    *,
    title: str,
    body: str,
    subtitle: str,
    nav_html: str,
    flash_html: str,
    ui_lang: str,
    lang_label: str,
    lang_options_html: str,
    theme_label: str,
    theme_options_html: str,
    copied_label: str,
    brand_name: str = "LunaeClaw Control Hub",
) -> str:
    """Render the full HTML shell for WebUI pages."""
    lang_icon = icon_svg("globe")
    theme_icon = icon_svg("theme")
    brand_logo = logo_svg(title=brand_name)
    return f"""<!doctype html>
<html lang="{escape(ui_lang)}" data-theme="auto">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)} - {escape(brand_name)}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #edf3ff;
      --card: rgba(255, 255, 255, .72);
      --card-strong: rgba(255, 255, 255, .88);
      --ink: #102238;
      --muted: #5c6f86;
      --line: rgba(160, 183, 216, .55);
      --line-soft: rgba(160, 183, 216, .34);
      --accent: #2a6fd8;
      --accent-deep: #225fc3;
      --accent-2: #587fcc;
      --accent-2-deep: #456fe2;
      --warning: #d17a43;
      --warning-deep: #b96534;
      --success: #1d9e70;
      --success-deep: #157f5a;
      --err: #b42318;
      --ok: #067647;
      --meter-track-a: color-mix(in srgb, var(--line-soft) 64%, #edf2fb 36%);
      --meter-track-b: color-mix(in srgb, var(--line-soft) 44%, transparent);
      --meter-teal-a: #75b5ad;
      --meter-teal-b: #4e938c;
      --meter-orange-a: #dfad8a;
      --meter-orange-b: #c5794c;
      --meter-ink-a: #8ea0b7;
      --meter-ink-b: #607186;
      --surface-strong: linear-gradient(180deg, rgba(255, 255, 255, .9), rgba(236, 245, 255, .58));
      --surface-soft: linear-gradient(180deg, rgba(255, 255, 255, .84), rgba(231, 242, 255, .5));
      --surface-sheen: linear-gradient(180deg, rgba(255,255,255,.5), rgba(255,255,255,.12));
      --input-bg: rgba(248, 252, 255, .82);
      --nav-bg: rgba(244, 249, 255, .66);
      --subtle-bg: rgba(241, 248, 255, .62);
      --code-bg: rgba(231, 241, 255, .72);
      --badge-ok-bg: rgba(16, 185, 129, .12);
      --badge-off-bg: rgba(217, 79, 71, .13);
      --shadow: 0 16px 40px rgba(32, 68, 130, .16);
      --shadow-lift: 0 24px 58px rgba(32, 68, 130, .23);
      --mono: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      --sans: "Avenir Next", "PingFang SC", "Noto Sans SC", "Helvetica Neue", sans-serif;
    }}
    :root[data-theme="dark"] {{
      color-scheme: dark;
      --bg: #10182a;
      --card: rgba(24, 38, 61, .82);
      --card-strong: rgba(28, 45, 72, .9);
      --ink: #edf4ff;
      --muted: #c4d3e8;
      --line: rgba(156, 182, 220, .56);
      --line-soft: rgba(156, 182, 220, .34);
      --accent: #528de4;
      --accent-deep: #3e79d0;
      --accent-2: #6a90d2;
      --accent-2-deep: #4e7be0;
      --warning: #f29a62;
      --warning-deep: #dc7f49;
      --success: #32bb85;
      --success-deep: #239665;
      --err: #ff7f78;
      --ok: #6de6b0;
      --meter-track-a: color-mix(in srgb, rgba(140, 167, 208, .42) 70%, #2b3f63 30%);
      --meter-track-b: color-mix(in srgb, rgba(140, 167, 208, .24) 70%, transparent);
      --meter-teal-a: #63a89f;
      --meter-teal-b: #41877e;
      --meter-orange-a: #ca8c67;
      --meter-orange-b: #aa6a43;
      --meter-ink-a: #8090a8;
      --meter-ink-b: #56667c;
      --surface-strong: linear-gradient(180deg, rgba(35, 52, 80, .84), rgba(22, 35, 56, .8));
      --surface-soft: linear-gradient(180deg, rgba(31, 48, 75, .72), rgba(21, 32, 52, .64));
      --surface-sheen: linear-gradient(180deg, rgba(236, 246, 255, .12), rgba(236, 246, 255, .02));
      --input-bg: rgba(32, 48, 74, .9);
      --nav-bg: rgba(41, 61, 94, .84);
      --subtle-bg: rgba(45, 66, 100, .74);
      --code-bg: rgba(30, 45, 72, .74);
      --badge-ok-bg: rgba(38, 198, 138, .18);
      --badge-off-bg: rgba(255, 127, 120, .2);
      --shadow: 0 18px 42px rgba(3, 10, 24, .58);
      --shadow-lift: 0 28px 70px rgba(3, 10, 24, .74);
    }}
    @media (prefers-color-scheme: dark) {{
      :root[data-theme="auto"] {{
        color-scheme: dark;
        --bg: #10182a;
        --card: rgba(24, 38, 61, .82);
        --card-strong: rgba(28, 45, 72, .9);
        --ink: #edf4ff;
        --muted: #c4d3e8;
        --line: rgba(156, 182, 220, .56);
        --line-soft: rgba(156, 182, 220, .34);
        --accent: #528de4;
        --accent-deep: #3e79d0;
        --accent-2: #6a90d2;
        --accent-2-deep: #4e7be0;
        --warning: #f29a62;
        --warning-deep: #dc7f49;
        --success: #32bb85;
        --success-deep: #239665;
        --err: #ff7f78;
        --ok: #6de6b0;
        --meter-track-a: color-mix(in srgb, rgba(140, 167, 208, .42) 70%, #2b3f63 30%);
        --meter-track-b: color-mix(in srgb, rgba(140, 167, 208, .24) 70%, transparent);
        --meter-teal-a: #63a89f;
        --meter-teal-b: #41877e;
        --meter-orange-a: #ca8c67;
        --meter-orange-b: #aa6a43;
        --meter-ink-a: #8090a8;
        --meter-ink-b: #56667c;
        --surface-strong: linear-gradient(180deg, rgba(35, 52, 80, .84), rgba(22, 35, 56, .8));
        --surface-soft: linear-gradient(180deg, rgba(31, 48, 75, .72), rgba(21, 32, 52, .64));
        --surface-sheen: linear-gradient(180deg, rgba(236, 246, 255, .12), rgba(236, 246, 255, .02));
        --input-bg: rgba(32, 48, 74, .9);
        --nav-bg: rgba(41, 61, 94, .84);
        --subtle-bg: rgba(45, 66, 100, .74);
        --code-bg: rgba(30, 45, 72, .74);
        --badge-ok-bg: rgba(38, 198, 138, .18);
        --badge-off-bg: rgba(255, 127, 120, .2);
        --shadow: 0 18px 42px rgba(3, 10, 24, .58);
        --shadow-lift: 0 28px 70px rgba(3, 10, 24, .74);
      }}
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0; padding: 0; font-family: var(--sans); color: var(--ink);
      background:
        radial-gradient(circle at 8% 8%, color-mix(in srgb, var(--accent-2) 24%, transparent), transparent 42%),
        radial-gradient(circle at 92% 0%, color-mix(in srgb, var(--accent) 28%, transparent), transparent 40%),
        radial-gradient(circle at 50% 120%, color-mix(in srgb, #7cafff 18%, transparent), transparent 44%),
        var(--bg);
    }}
    .layout {{ max-width: 1200px; margin: 0 auto; padding: 18px; }}
    .top {{
      display:grid; gap:12px; margin-bottom:16px;
      background: var(--surface-strong);
      border:1px solid color-mix(in srgb, var(--line) 84%, #fff 16%); box-shadow: var(--shadow); border-radius: 18px; padding: 14px;
      backdrop-filter: blur(18px) saturate(122%);
      -webkit-backdrop-filter: blur(18px) saturate(122%);
      position: relative;
      overflow: hidden;
    }}
    .top-head {{
      display:flex;
      align-items:flex-start;
      justify-content:space-between;
      gap:16px;
    }}
    .top-controls {{
      display:grid;
      gap:8px;
      justify-items:end;
    }}
    .top::before {{
      content: "";
      position: absolute;
      inset: 0;
      background: var(--surface-sheen);
      pointer-events: none;
    }}
    .brand-title {{ display:flex; align-items:center; gap:10px; }}
    .brand-logo {{
      width: 34px;
      height: 34px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      border-radius: 11px;
      box-shadow: 0 8px 20px color-mix(in srgb, var(--accent) 24%, transparent), inset 0 1px 0 rgba(255,255,255,.35);
      overflow: hidden;
    }}
    .brand-logo svg {{ width:100%; height:100%; display:block; }}
    .brand h1 {{ margin:0; font-size: 22px; letter-spacing:.2px; }}
    .brand p {{ margin:6px 0 0; color: var(--muted); font-size: 13px; }}
    .nav {{
      display:flex;
      gap:8px;
      flex-wrap: nowrap;
      overflow-x: auto;
      overflow-y: visible;
      padding: 2px 0 4px;
      align-items: center;
    }}
    .nav-item {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      text-decoration:none; color: var(--ink); border:1px solid var(--line);
      background: var(--nav-bg); padding:8px 12px; border-radius: 999px; font-size: 13px;
      backdrop-filter: blur(10px);
      -webkit-backdrop-filter: blur(10px);
      transition: box-shadow .12s ease, background .12s ease, border-color .12s ease;
    }}
    .nav-item:hover {{
      box-shadow: 0 5px 14px color-mix(in srgb, var(--accent) 20%, transparent);
      border-color: color-mix(in srgb, var(--accent) 35%, var(--line));
    }}
    .nav-item.active {{ background: linear-gradient(180deg, var(--accent), var(--accent-deep)); color: #fff; border-color: var(--accent-deep); }}
    .flash {{ border-radius: 10px; padding: 10px 12px; margin-bottom: 12px; font-size: 13px; }}
    .flash.ok {{ background: color-mix(in srgb, var(--success) 16%, transparent); color: var(--ok); border:1px solid color-mix(in srgb, var(--success) 35%, #ffffff 65%); }}
    .flash.err {{ background: color-mix(in srgb, var(--err) 16%, transparent); color: var(--err); border:1px solid color-mix(in srgb, var(--err) 35%, #ffffff 65%); }}
    .grid {{ display:grid; gap: 14px; }}
    .grid.cols-2 {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    .grid.cols-3 {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }}
    .card {{
      background: var(--card); border:1px solid var(--line); border-radius: 14px; box-shadow: var(--shadow);
      padding: 14px;
      backdrop-filter: blur(18px) saturate(126%);
      -webkit-backdrop-filter: blur(18px) saturate(126%);
      position: relative;
      overflow: hidden;
      transition: box-shadow .2s ease, transform .2s ease;
    }}
    .card::before {{
      content: "";
      position: absolute;
      inset: 0;
      background: var(--surface-sheen);
      pointer-events: none;
    }}
    .card:hover {{
      box-shadow: var(--shadow-lift);
      transform: translateY(-1px);
    }}
    .card h2 {{
      margin:0 0 12px;
      display:inline-flex;
      align-items:center;
      padding:4px 10px;
      border-radius: 999px;
      border:1px solid color-mix(in srgb, var(--line) 78%, #fff 22%);
      background: var(--subtle-bg);
      box-shadow: inset 0 1px 0 color-mix(in srgb, #fff 36%, transparent);
      backdrop-filter: blur(11px);
      -webkit-backdrop-filter: blur(11px);
      color: var(--ink);
      letter-spacing:.1px;
    }}
    .card h2 {{ font-size: 16px; }}
    .card h3 {{
      margin: 0;
      display: block;
      padding: 0;
      border: 0;
      background: transparent;
      box-shadow: none;
      font-size: 14px;
      color: var(--ink);
      letter-spacing: .1px;
    }}
    .muted {{ color: var(--muted); font-size: 12px; }}
    .kpi {{ font-size: 28px; font-weight: 700; }}
    .row {{ display:flex; gap:10px; align-items:center; flex-wrap:wrap; }}
    .row.end {{ justify-content: flex-end; }}
    .field {{ display:grid; gap:6px; margin-bottom:10px; }}
    .field label {{ font-size: 12px; color: var(--muted); }}
    input[type=text], input[type=number], textarea, select {{
      width:100%; border:1px solid var(--line); border-radius:10px; background: var(--input-bg); color:var(--ink);
      padding:10px 12px; font: inherit;
      backdrop-filter: blur(8px);
      -webkit-backdrop-filter: blur(8px);
    }}
    textarea {{ min-height: 120px; font-family: var(--mono); font-size: 12px; line-height: 1.35; }}
    textarea.tall-sm {{ min-height: 120px; }}
    textarea.tall-md {{ min-height: 360px; }}
    textarea.tall-lg {{ min-height: 420px; }}
    .mono {{ font-family: var(--mono); font-size: 12px; }}
    .btn {{
      border:1px solid var(--line); background: var(--input-bg); color: var(--ink); border-radius: 10px;
      padding:8px 12px; cursor:pointer; font-weight:600;
      box-shadow: inset 0 1px 0 rgba(255,255,255,.48), 0 2px 10px rgba(31,35,40,.1);
      transition: transform .12s ease, box-shadow .12s ease, filter .12s ease;
      text-decoration: none;
    }}
    .btn:hover {{ transform: translateY(-1px); box-shadow: inset 0 1px 0 rgba(255,255,255,.52), 0 6px 14px rgba(31,35,40,.14); }}
    .btn:active {{ transform: translateY(0); }}
    .icon-btn {{ display:inline-flex; align-items:center; gap:6px; }}
    .icon-only {{
      width: 34px;
      min-width: 34px;
      height: 34px;
      padding: 0;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      border-radius: 999px;
    }}
    .ui-icon {{
      width: 15px;
      height: 15px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      flex: 0 0 auto;
    }}
    .ui-icon svg {{
      width: 15px;
      height: 15px;
      display: block;
    }}
    .btn.primary {{ background: linear-gradient(180deg, var(--accent), var(--accent-deep)); color: #fff; border-color: var(--accent-deep); }}
    .btn.warn {{ background: linear-gradient(180deg, var(--accent-2), var(--accent-2-deep)); color: #fff; border-color: var(--accent-2-deep); }}
    .btn.success {{ background: linear-gradient(180deg, var(--success), var(--success-deep)); color: #fff; border-color: var(--success-deep); }}
    .btn.subtle {{ background: var(--subtle-bg); }}
    .btn.danger {{
      background: linear-gradient(180deg, color-mix(in srgb, var(--err) 76%, #fff 24%), color-mix(in srgb, var(--err) 88%, #300 12%));
      color: #fff;
      border-color: color-mix(in srgb, var(--err) 82%, #210 18%);
    }}
    .lang-switch {{
      display:inline-flex; align-items:center; gap:8px; border:1px solid var(--line);
      border-radius:10px; padding:6px 8px; background: var(--subtle-bg);
      backdrop-filter: blur(10px);
      -webkit-backdrop-filter: blur(10px);
    }}
    .picker {{
      border:none; background:transparent; padding:0 2px; min-width:96px;
      font: inherit; color: var(--ink);
    }}
    .picker:focus {{ outline:none; }}
    .lang-icon-btn {{
      width:28px; height:28px; display:inline-flex; align-items:center; justify-content:center;
      border:1px solid var(--line); border-radius:8px; background: var(--input-bg);
      line-height:1;
    }}
    .lang-select {{ min-width:120px; }}
    table {{ width:100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ border-bottom:1px solid var(--line-soft); text-align:left; vertical-align: top; padding:8px 6px; }}
    th {{ color: var(--muted); font-weight:600; }}
    tbody tr:hover td {{ background: color-mix(in srgb, var(--accent) 8%, transparent); }}
    code {{ font-family: var(--mono); background: var(--code-bg); padding:2px 4px; border-radius:4px; }}
    .pill {{ display:inline-flex; align-items:center; justify-content:center; white-space:nowrap; line-height:1.15; border-radius:999px; padding:2px 8px; font-size:11px; border:1px solid var(--line); }}
    .pill.ok {{ border-color: color-mix(in srgb, var(--ok) 42%, var(--line)); color: var(--ok); background: var(--badge-ok-bg); }}
    .pill.off {{ border-color: color-mix(in srgb, var(--err) 40%, var(--line)); color: var(--err); background: var(--badge-off-bg); }}
    .glass-toolbar {{
      position: sticky;
      top: 8px;
      z-index: 2;
      padding: 8px;
      border-radius: 12px;
      background: var(--subtle-bg);
      backdrop-filter: blur(10px);
      -webkit-backdrop-filter: blur(10px);
      border: 1px solid var(--line);
      box-shadow: inset 0 1px 0 color-mix(in srgb, #fff 30%, transparent);
    }}
    .glass-chip {{
      border:1px solid var(--line);
      border-radius:999px;
      padding:4px 10px;
      font-size:12px;
      background: var(--subtle-bg);
      box-shadow: inset 0 1px 0 color-mix(in srgb, #fff 35%, transparent);
    }}
    .switch-btn {{
      position: relative;
      width: 66px;
      height: 36px;
      border-radius: 999px;
      border: 1px solid var(--line);
      cursor: pointer;
      padding: 0;
      transition: background .18s ease, box-shadow .18s ease, transform .12s ease, filter .18s ease;
      box-shadow: inset 0 1px 0 rgba(255,255,255,.45), 0 8px 16px rgba(20, 38, 58, .12);
    }}
    .switch-btn span {{
      position: absolute;
      top: 50%;
      transform: translateY(-50%);
      font-size: 11px;
      font-weight: 700;
      letter-spacing: .4px;
      z-index: 3;
      user-select: none;
      text-shadow: 0 1px 2px rgba(15, 24, 33, .3);
    }}
    .switch-btn::after {{
      content: "";
      position: absolute;
      top: 3px;
      left: 3px;
      width: 28px;
      height: 28px;
      border-radius: 999px;
      background: linear-gradient(180deg, rgba(255,255,255,.98), rgba(240,244,248,.95));
      box-shadow: 0 2px 8px rgba(17, 27, 37, .2);
      transition: transform .2s ease;
    }}
    .switch-btn.on {{
      background: linear-gradient(180deg, rgba(58, 194, 132, .96), rgba(17, 137, 88, .96));
      border-color: rgba(17, 120, 78, .94);
    }}
    .switch-btn.on span {{
      left: 11px;
      color: rgba(233, 255, 245, .98);
    }}
    .switch-btn.on::after {{ transform: translateX(30px); }}
    .switch-btn.off {{
      background: linear-gradient(180deg, rgba(247, 156, 86, .98), rgba(221, 123, 49, .96));
      border-color: rgba(191, 103, 34, .92);
    }}
    .switch-btn.off span {{
      right: 11px;
      color: rgba(255, 245, 237, .98);
    }}
    .switch-btn:hover {{ filter: brightness(1.05) saturate(1.08); }}
    .switch-btn:active {{ transform: translateY(1px) scale(.99); }}
    .split {{ display:grid; grid-template-columns: 1.15fr .85fr; gap: 14px; }}
    .small {{ font-size: 12px; }}
    .is-hidden {{ display: none !important; }}
    .mt-8 {{ margin-top: 8px; }}
    .mt-10 {{ margin-top: 10px; }}
    .mt-12 {{ margin-top: 12px; }}
    .mt-14 {{ margin-top: 14px; }}
    .mb-10 {{ margin-bottom: 10px; }}
    .stack-gap > * + * {{ margin-top: 14px; }}
    .list {{ margin:0; padding-left: 18px; }}
    .list li {{ margin: 4px 0; }}
    .endpoint-card {{
      border:1px solid var(--line); border-radius: 12px; padding: 12px; margin-bottom:10px;
      background: var(--card-strong); backdrop-filter: blur(9px); -webkit-backdrop-filter: blur(9px);
      box-shadow: inset 0 1px 0 rgba(255,255,255,.5), var(--shadow);
    }}
    .endpoint-head {{ display:flex; justify-content:space-between; gap:8px; align-items:center; }}
    .endpoint-fields {{ display:grid; grid-template-columns: repeat(2, minmax(0,1fr)); gap:10px; margin-top:10px; }}
    .endpoint-fields .field.full {{ grid-column: 1 / -1; }}
    .toast {{
      position: fixed; right: 16px; bottom: 16px; background: #122b24; color: #fff; border-radius: 10px;
      padding: 10px 12px; font-size: 12px; opacity: 0; transform: translateY(8px); pointer-events:none;
      transition: all .18s ease;
    }}
    .toast.show {{ opacity: .96; transform: translateY(0); }}
    html[data-theme="dark"] .brand h1,
    html[data-theme="dark"] .brand p {{
      text-shadow: 0 1px 1px rgba(7, 12, 20, .45);
    }}
    html[data-theme="dark"] .nav-item,
    html[data-theme="dark"] .lang-switch {{
      border-color: color-mix(in srgb, var(--line) 88%, #fff 12%);
    }}
    html[data-theme="dark"] .card,
    html[data-theme="dark"] .top {{
      box-shadow: 0 18px 46px rgba(3, 8, 16, .62);
    }}
    @media (prefers-color-scheme: dark) {{
      html[data-theme="auto"] .brand h1,
      html[data-theme="auto"] .brand p {{
        text-shadow: 0 1px 1px rgba(7, 12, 20, .45);
      }}
      html[data-theme="auto"] .nav-item,
      html[data-theme="auto"] .lang-switch {{
        border-color: color-mix(in srgb, var(--line) 88%, #fff 12%);
      }}
      html[data-theme="auto"] .card,
      html[data-theme="auto"] .top {{
        box-shadow: 0 18px 46px rgba(3, 8, 16, .62);
      }}
    }}
    @media (max-width: 980px) {{
      .grid.cols-2, .grid.cols-3, .split, .endpoint-fields {{ grid-template-columns: 1fr; }}
      .top-head {{ flex-direction: column; }}
      .top-controls {{ justify-items: start; width: 100%; }}
      .top .row {{ justify-content:flex-start !important; }}
    }}
    @media (max-width: 640px) {{
      .layout {{ padding: 12px; }}
      .card {{ padding: 12px; border-radius: 12px; }}
      .nav {{ padding-bottom: 4px; }}
      .nav-item {{ white-space: nowrap; }}
    }}
  </style>
</head>
<body>
  <div class="layout">
    <div class="top">
      <div class="top-head">
        <div class="brand">
          <div class="brand-title">{brand_logo}<h1>{escape(brand_name)}</h1></div>
        </div>
        <div class="top-controls">
        <div class="row end">
          <span class="muted">{lang_label}</span>
          <div class="lang-switch" title="{lang_label}">
            <span class="lang-icon-btn" aria-hidden="true">{lang_icon}</span>
            <select id="nb-lang-picker" class="picker lang-select" aria-label="{lang_label}">
              {lang_options_html}
            </select>
          </div>
          <span class="muted">{theme_label}</span>
          <div class="lang-switch" title="{theme_label}">
            <span class="lang-icon-btn" aria-hidden="true">{theme_icon}</span>
            <select id="nb-theme-picker" class="picker" aria-label="{theme_label}">
              {theme_options_html}
            </select>
          </div>
        </div>
        </div>
      </div>
      <nav class="nav">{nav_html}</nav>
    </div>
    {flash_html}
    {body}
  </div>
  <script>
    async function nbCopy(text) {{
      try {{
        await navigator.clipboard.writeText(text);
      }} catch (e) {{
        const ta = document.createElement('textarea');
        ta.value = text;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        ta.remove();
      }}
      const toast = document.getElementById('nb-toast');
      if (toast) {{
        toast.textContent = '{escape(copied_label)}';
        toast.classList.add('show');
        window.clearTimeout(window.__nbToastTimer);
        window.__nbToastTimer = window.setTimeout(() => toast.classList.remove('show'), 1200);
      }}
    }}
    function nbSelectAll(form, checked) {{
      if (!form) return;
      for (const box of form.querySelectorAll('input[name="selected_name"]')) {{
        box.checked = !!checked;
      }}
    }}
    (function bindLangPicker() {{
      const picker = document.getElementById('nb-lang-picker');
      if (!picker) return;
      picker.addEventListener('change', () => {{
        const u = new URL(window.location.href);
        u.searchParams.set('lang', picker.value);
        window.location.href = u.pathname + u.search;
      }});
    }})();
    (function bindThemePicker() {{
      const key = "lunaeclaw.app.webui.theme";
      const root = document.documentElement;
      const picker = document.getElementById("nb-theme-picker");
      if (!picker) return;
      const applyTheme = (theme) => {{
        const value = (theme === "light" || theme === "dark") ? theme : "auto";
        root.setAttribute("data-theme", value);
        window.localStorage.setItem(key, value);
        picker.value = value;
      }};
      const stored = window.localStorage.getItem(key) || "auto";
      applyTheme(stored);
      picker.addEventListener("change", () => applyTheme(picker.value));
    }})();
    (function bindUiLang() {{
      const uiLang = "{escape(ui_lang)}";
      for (const form of document.querySelectorAll('form')) {{
        if (!form.querySelector('input[name="ui_lang"]')) {{
          const hidden = document.createElement('input');
          hidden.type = 'hidden';
          hidden.name = 'ui_lang';
          hidden.value = uiLang;
          form.appendChild(hidden);
        }}
      }}
      for (const a of document.querySelectorAll('a[href^="/"]')) {{
        try {{
          const u = new URL(a.getAttribute('href'), window.location.origin);
          if (!u.searchParams.get('lang')) {{
            u.searchParams.set('lang', uiLang);
            a.setAttribute('href', u.pathname + u.search);
          }}
        }} catch (e) {{}}
      }}
    }})();
  </script>
  <div id="nb-toast" class="toast" aria-live="polite"></div>
</body>
</html>"""
