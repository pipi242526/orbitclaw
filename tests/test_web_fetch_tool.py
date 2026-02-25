import json
import sys
import types

import httpx
import pytest

from nanobot.agent.tools.web import WebFetchTool


class _FakeReadabilityDoc:
    def __init__(self, html_text: str):
        self._html = html_text

    def title(self) -> str:
        return "Example Page"

    def summary(self) -> str:
        return "<article><p>Hello <strong>world</strong>.</p></article>"


class _FakeAsyncClient:
    def __init__(self, response: httpx.Response):
        self._response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url: str, headers=None):
        return self._response


def _install_fake_readability(monkeypatch: pytest.MonkeyPatch) -> None:
    module = types.SimpleNamespace(Document=_FakeReadabilityDoc)
    monkeypatch.setitem(sys.modules, "readability", module)


def _patch_async_client(monkeypatch: pytest.MonkeyPatch, response: httpx.Response) -> None:
    monkeypatch.setattr(
        "nanobot.agent.tools.web.httpx.AsyncClient",
        lambda *args, **kwargs: _FakeAsyncClient(response),
    )


def _response(url: str, *, content_type: str, content: bytes, headers: dict[str, str] | None = None) -> httpx.Response:
    req = httpx.Request("GET", url)
    merged_headers = {"content-type": content_type}
    if headers:
        merged_headers.update(headers)
    return httpx.Response(200, headers=merged_headers, content=content, request=req)


@pytest.mark.asyncio
async def test_web_fetch_json_response(monkeypatch: pytest.MonkeyPatch):
    _install_fake_readability(monkeypatch)
    resp = _response(
        "https://example.com/data.json",
        content_type="application/json",
        content=b'{"ok": true, "items": [1,2]}',
    )
    _patch_async_client(monkeypatch, resp)

    tool = WebFetchTool()
    raw = await tool.execute(url="https://example.com/data.json")
    data = json.loads(raw)

    assert data["extractor"] == "json"
    assert data["contentType"].startswith("application/json")
    assert '"ok": true' in data["text"]
    assert data["truncated"] is False


@pytest.mark.asyncio
async def test_web_fetch_html_response_uses_readability(monkeypatch: pytest.MonkeyPatch):
    _install_fake_readability(monkeypatch)
    html = b"<html><head><title>Ignored</title></head><body><p>Hello</p></body></html>"
    resp = _response("https://example.com/page", content_type="text/html; charset=utf-8", content=html)
    _patch_async_client(monkeypatch, resp)

    tool = WebFetchTool()
    raw = await tool.execute(url="https://example.com/page", extractMode="markdown")
    data = json.loads(raw)

    assert data["extractor"] == "readability"
    assert data["title"] == "Example Page"
    assert "Hello world." in data["text"]
    assert data["text"].startswith("# Example Page")


@pytest.mark.asyncio
async def test_web_fetch_binary_content_returns_hint(monkeypatch: pytest.MonkeyPatch):
    _install_fake_readability(monkeypatch)
    resp = _response("https://example.com/file.pdf", content_type="application/pdf", content=b"%PDF-1.7")
    _patch_async_client(monkeypatch, resp)

    tool = WebFetchTool()
    raw = await tool.execute(url="https://example.com/file.pdf")
    data = json.loads(raw)

    assert data["error"] == "unsupported_binary_content"
    assert "doc_read" in data["hint"]
    assert data["contentType"].startswith("application/pdf")


@pytest.mark.asyncio
async def test_web_fetch_oversized_response_rejected(monkeypatch: pytest.MonkeyPatch):
    _install_fake_readability(monkeypatch)
    resp = _response(
        "https://example.com/big.txt",
        content_type="text/plain",
        content=b"x",
        headers={"content-length": "9999"},
    )
    _patch_async_client(monkeypatch, resp)

    tool = WebFetchTool(max_download_bytes=100)
    raw = await tool.execute(url="https://example.com/big.txt")
    data = json.loads(raw)

    assert data["error"] == "response_too_large"
    assert data["contentLength"] == 9999
    assert "specialized tool" in data["hint"]
