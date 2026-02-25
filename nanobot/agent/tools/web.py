"""Web tools: web_search and web_fetch."""

import html
import json
import os
import re
from typing import Any
from urllib.parse import urlparse

import httpx

from nanobot.agent.tools.base import Tool

# Shared constants
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7_2) AppleWebKit/537.36"
MAX_REDIRECTS = 5  # Limit redirects to prevent DoS attacks
_BINARY_DOC_CTYPES = (
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument",
    "application/vnd.ms-excel",
    "application/vnd.ms-powerpoint",
    "application/octet-stream",
    "image/",
    "audio/",
    "video/",
)


def _strip_tags(text: str) -> str:
    """Remove HTML tags and decode entities."""
    text = re.sub(r'<script[\s\S]*?</script>', '', text, flags=re.I)
    text = re.sub(r'<style[\s\S]*?</style>', '', text, flags=re.I)
    text = re.sub(r'<[^>]+>', '', text)
    return html.unescape(text).strip()


def _normalize(text: str) -> str:
    """Normalize whitespace."""
    text = re.sub(r'[ \t]+', ' ', text)
    return re.sub(r'\n{3,}', '\n\n', text).strip()


def _validate_url(url: str) -> tuple[bool, str]:
    """Validate URL: must be http(s) with valid domain."""
    try:
        p = urlparse(url)
        if p.scheme not in ('http', 'https'):
            return False, f"Only http/https allowed, got '{p.scheme or 'none'}'"
        if not p.netloc:
            return False, "Missing domain"
        return True, ""
    except Exception as e:
        return False, str(e)


class WebSearchTool(Tool):
    """Search the web using Brave Search API."""
    
    name = "web_search"
    description = "Search the web. Returns titles, URLs, and snippets."
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "count": {"type": "integer", "description": "Results (1-10)", "minimum": 1, "maximum": 10}
        },
        "required": ["query"]
    }
    
    def __init__(self, api_key: str | None = None, max_results: int = 5):
        self._config_api_key = api_key
        self.max_results = max_results

    def _resolve_api_key(self) -> str:
        """Resolve API key at call time so env/config changes are picked up."""
        return self._config_api_key or os.environ.get("BRAVE_API_KEY", "")
    
    async def execute(self, query: str, count: int | None = None, **kwargs: Any) -> str:
        api_key = self._resolve_api_key()
        if not api_key:
            return (
                "Error: Brave Search API key not configured. "
                "Set it in ~/.nanobot/config.json under tools.web.search.apiKey "
                "(or export BRAVE_API_KEY / use env placeholders), then retry."
            )
        
        try:
            n = min(max(count or self.max_results, 1), 10)
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    params={"q": query, "count": n},
                    headers={"Accept": "application/json", "X-Subscription-Token": api_key},
                    timeout=10.0
                )
                r.raise_for_status()
            
            results = r.json().get("web", {}).get("results", [])
            if not results:
                return f"No results for: {query}"
            
            lines = [f"Results for: {query}\n"]
            for i, item in enumerate(results[:n], 1):
                lines.append(f"{i}. {item.get('title', '')}\n   {item.get('url', '')}")
                if desc := item.get("description"):
                    lines.append(f"   {desc}")
            return "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"


class MCPWebSearchCompatTool(Tool):
    """Expose an MCP search tool behind the built-in `web_search` interface."""

    name = "web_search"
    description = "Search the web (via MCP/Exa). Returns titles, URLs, and snippets."
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "count": {"type": "integer", "description": "Results (1-10)", "minimum": 1, "maximum": 10}
        },
        "required": ["query"]
    }

    def __init__(self, delegate: Tool, max_results: int = 5):
        self._delegate = delegate
        self._max_results = max_results

    def _map_args(self, query: str, count: int | None) -> dict[str, Any]:
        schema = self._delegate.parameters or {}
        props = schema.get("properties", {}) if isinstance(schema, dict) else {}
        mapped: dict[str, Any] = {}

        # Query parameter (Exa MCP uses "query")
        for key in ("query", "q", "searchQuery", "search_query"):
            if key in props:
                mapped[key] = query
                break
        else:
            mapped["query"] = query

        n = min(max(count or self._max_results, 1), 10)
        for key in ("count", "numResults", "num_results", "limit", "max_results", "k"):
            if key in props:
                mapped[key] = n
                break

        return mapped

    async def execute(self, query: str, count: int | None = None, **kwargs: Any) -> str:
        return await self._delegate.execute(**self._map_args(query=query, count=count))


def _mcp_cfg_field(cfg: Any, field: str) -> str:
    if isinstance(cfg, dict):
        value = cfg.get(field, "")
    else:
        value = getattr(cfg, field, "")
    return value if isinstance(value, str) else ""


def has_exa_search_mcp(mcp_servers: dict[str, Any] | None) -> bool:
    """Detect whether an Exa MCP server is configured."""
    if not mcp_servers:
        return False
    for name, cfg in mcp_servers.items():
        if str(name).lower() == "exa":
            return True
        url = _mcp_cfg_field(cfg, "url").lower()
        if "exa.ai" in url:
            return True
        cmd = _mcp_cfg_field(cfg, "command").lower()
        args = []
        if isinstance(cfg, dict):
            args = cfg.get("args", []) or []
        else:
            args = getattr(cfg, "args", []) or []
        joined = " ".join(str(x).lower() for x in args)
        if "exa" in cmd or "exa-mcp" in joined or "mcp.exa.ai" in joined:
            return True
    return False


def install_exa_web_search_alias(registry: Any) -> str | None:
    """Register `web_search` alias for an Exa MCP tool if present. Returns wrapped tool name."""
    names = list(getattr(registry, "tool_names", []))
    if not names:
        return None

    candidates = [n for n in names if n.startswith("mcp_") and n.endswith("_web_search_exa")]
    if not candidates:
        return None

    candidates.sort(key=lambda n: (0 if n.startswith("mcp_exa_") else 1, n))
    delegate_name = candidates[0]
    delegate = registry.get(delegate_name)
    if not delegate:
        return None

    registry.register(MCPWebSearchCompatTool(delegate=delegate))
    return delegate_name


class WebFetchTool(Tool):
    """Fetch and extract content from a URL using Readability."""
    
    name = "web_fetch"
    description = "Fetch URL and extract readable content (HTML → markdown/text)."
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to fetch"},
            "extractMode": {"type": "string", "enum": ["markdown", "text"], "default": "markdown"},
            "maxChars": {"type": "integer", "minimum": 100}
        },
        "required": ["url"]
    }
    
    def __init__(self, max_chars: int = 50000, max_download_bytes: int = 2_000_000):
        self.max_chars = max_chars
        self.max_download_bytes = max_download_bytes

    @staticmethod
    def _dump(payload: dict[str, Any]) -> str:
        return json.dumps(payload, ensure_ascii=False)

    @staticmethod
    def _response_content_length(response: httpx.Response) -> int:
        content_len_hdr = response.headers.get("content-length")
        if (content_len_hdr or "").isdigit():
            return int(content_len_hdr)
        return len(response.content)

    def _response_meta(self, request_url: str, response: httpx.Response) -> dict[str, Any]:
        return {
            "url": request_url,
            "finalUrl": str(response.url),
            "status": response.status_code,
            "contentType": (response.headers.get("content-type", "") or "").lower(),
            "contentLength": self._response_content_length(response),
        }

    def _preflight_error(self, meta: dict[str, Any]) -> dict[str, Any] | None:
        content_len = int(meta.get("contentLength", 0) or 0)
        ctype = str(meta.get("contentType", "") or "")

        if content_len > self.max_download_bytes:
            return {
                "error": "response_too_large",
                **meta,
                "hint": f"Response is {content_len} bytes (> {self.max_download_bytes}). Narrow the URL or use a specialized tool.",
            }

        if self._is_binary_like_content(ctype):
            return {
                "error": "unsupported_binary_content",
                **meta,
                "hint": "Use doc_read for PDF/Office/image attachments, or download and parse with a document/image MCP tool.",
            }

        return None
    
    async def execute(self, url: str, extractMode: str = "markdown", maxChars: int | None = None, **kwargs: Any) -> str:
        from readability import Document

        max_chars = maxChars or self.max_chars

        # Validate URL before fetching
        is_valid, error_msg = _validate_url(url)
        if not is_valid:
            return self._dump({"error": f"URL validation failed: {error_msg}", "url": url})

        try:
            async with httpx.AsyncClient(
                follow_redirects=True,
                max_redirects=MAX_REDIRECTS,
                timeout=30.0
            ) as client:
                r = await client.get(url, headers={"User-Agent": USER_AGENT})
                r.raise_for_status()

            meta = self._response_meta(url, r)
            if preflight_error := self._preflight_error(meta):
                return self._dump(preflight_error)

            text, extractor, title = self._extract_text(r, extract_mode=extractMode, readability_document=Document)
            text = _normalize(text) if extractor != "json" else text

            original_length = len(text)
            truncated = original_length > max_chars
            if truncated:
                text = text[:max_chars]

            return self._dump(
                {
                    **meta,
                    "extractor": extractor,
                    "title": title,
                    "truncated": truncated,
                    "length": len(text),
                    "originalLength": original_length,
                    "text": text,
                }
            )
        except Exception as e:
            return self._dump({"error": str(e), "url": url})

    def _is_binary_like_content(self, content_type: str) -> bool:
        ctype = (content_type or "").lower()
        if not ctype:
            return False
        return any(ctype.startswith(prefix) for prefix in _BINARY_DOC_CTYPES)

    def _extract_text(
        self,
        response: httpx.Response,
        extract_mode: str,
        readability_document: Any,
    ) -> tuple[str, str, str]:
        """Return (text, extractor, title)."""
        ctype = (response.headers.get("content-type", "") or "").lower()

        if "application/json" in ctype:
            try:
                return json.dumps(response.json(), indent=2, ensure_ascii=False), "json", ""
            except Exception:
                # fall through to text/raw parsing if JSON header lies
                pass

        body_text = response.text or ""
        probe = body_text[:512].lower()
        looks_html = "text/html" in ctype or probe.startswith(("<!doctype", "<html")) or "<body" in probe

        if looks_html:
            title, content, extractor = self._extract_html(body_text, extract_mode=extract_mode, readability_document=readability_document)
            final_text = f"# {title}\n\n{content}" if (title and extract_mode == "markdown" and content) else (f"{title}\n\n{content}" if title and content and extract_mode != "markdown" else content)
            return final_text or body_text[: self.max_chars], extractor, title

        return body_text, "raw", ""

    def _extract_html(self, html_text: str, extract_mode: str, readability_document: Any) -> tuple[str, str, str]:
        """Extract readable content from HTML with fallbacks."""
        title = ""
        extractor = "html_fallback"
        content = ""
        try:
            doc = readability_document(html_text)
            title = (doc.title() or "").strip()
            summary_html = doc.summary() or ""
            if summary_html:
                content = self._to_markdown(summary_html) if extract_mode == "markdown" else _strip_tags(summary_html)
                extractor = "readability"
        except Exception:
            pass

        if not content.strip():
            body_match = re.search(r"<body[^>]*>([\s\S]*?)</body>", html_text, flags=re.I)
            source = body_match.group(1) if body_match else html_text
            content = self._to_markdown(source) if extract_mode == "markdown" else _strip_tags(source)
            extractor = "html_fallback"

        if not title:
            m = re.search(r"<title[^>]*>([\s\S]*?)</title>", html_text, flags=re.I)
            if m:
                title = _normalize(_strip_tags(m.group(1)))
        return title, content, extractor
    
    def _to_markdown(self, html: str) -> str:
        """Convert HTML to markdown."""
        # Convert links, headings, lists before stripping tags
        text = re.sub(r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>([\s\S]*?)</a>',
                      lambda m: f'[{_strip_tags(m[2])}]({m[1]})', html, flags=re.I)
        text = re.sub(r'<h([1-6])[^>]*>([\s\S]*?)</h\1>',
                      lambda m: f'\n{"#" * int(m[1])} {_strip_tags(m[2])}\n', text, flags=re.I)
        text = re.sub(r'<li[^>]*>([\s\S]*?)</li>', lambda m: f'\n- {_strip_tags(m[1])}', text, flags=re.I)
        text = re.sub(r'</(p|div|section|article)>', '\n\n', text, flags=re.I)
        text = re.sub(r'<(br|hr)\s*/?>', '\n', text, flags=re.I)
        return _normalize(_strip_tags(text))
