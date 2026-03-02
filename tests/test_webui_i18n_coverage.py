from __future__ import annotations

from pathlib import Path

from orbitclaw.config.schema import Config
from orbitclaw.webui import views
from orbitclaw.webui.i18n import get_copy_stats, reset_copy_stats


class _DummyHandler:
    def __init__(self, cfg: Config, lang: str) -> None:
        self._cfg = cfg
        self._ui_lang = lang
        self.last_html = ""

    def _load_config(self) -> Config:
        return self._cfg

    def _page(self, title: str, body: str, tab: str = "", msg: str = "", err: str = "") -> str:
        _ = (title, tab, msg, err)
        return body

    def _send_html(self, status: int, html: str) -> None:
        _ = status
        self.last_html = html

    def _url_with_lang(self, path: str) -> str:
        return path


def _gateway_ok() -> tuple[bool, str, str]:
    return True, "ok", "ok"


def _no_channel_issues(*args, **kwargs) -> list[str]:
    _ = (args, kwargs)
    return []


def _no_policy_issues(*args, **kwargs) -> list[str]:
    _ = (args, kwargs)
    return []


def _with_channel_issues(*args, **kwargs) -> list[str]:
    _ = (args, kwargs)
    return ["telegram: missing `token`"]


def _with_policy_issues(*args, **kwargs) -> list[str]:
    _ = (args, kwargs)
    return ["tools.enabled does not include `message`"]


def test_webui_copy_dictionary_coverage_all_pages(tmp_path: Path) -> None:
    cfg = Config()
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text("{}", encoding="utf-8")
    gateway_state_path = tmp_path / "gateway.state.json"

    for lang in ("en", "zh-CN"):
        reset_copy_stats()
        h = _DummyHandler(cfg, lang=lang)

        views.render_dashboard(
            h,
            cfg_path=cfg_path,
            gateway_state_path=gateway_state_path,
            gateway_runtime_status=_gateway_ok,
            collect_channel_runtime_issues=_no_channel_issues,
        )
        views.render_channels(
            h,
            cfg_path=cfg_path,
            gateway_runtime_status=_gateway_ok,
        )
        views.render_endpoints(h)
        views.render_mcp(h, collect_tool_policy_diagnostics=_no_policy_issues)
        views.render_skills(h)
        views.render_media(h, media_page=1, exports_page=1)

        stats = get_copy_stats()
        assert stats["fallback_hits"] == 0, stats
        assert stats["missing_keys"] == {}, stats


def test_webui_copy_dictionary_coverage_with_issue_branches(tmp_path: Path) -> None:
    cfg = Config()
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text("{}", encoding="utf-8")
    gateway_state_path = tmp_path / "gateway.state.json"

    for lang in ("en", "zh-CN"):
        reset_copy_stats()
        h = _DummyHandler(cfg, lang=lang)

        views.render_dashboard(
            h,
            cfg_path=cfg_path,
            gateway_state_path=gateway_state_path,
            gateway_runtime_status=_gateway_ok,
            collect_channel_runtime_issues=_with_channel_issues,
        )
        views.render_mcp(h, collect_tool_policy_diagnostics=_with_policy_issues)

        stats = get_copy_stats()
        assert stats["fallback_hits"] == 0, stats
        assert stats["missing_keys"] == {}, stats
