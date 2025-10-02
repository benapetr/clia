from __future__ import annotations

from typing import Any, Dict

from clia.tooling import Tool
from clia.utils import strip_html, truncate

try:
    import requests
except ImportError:  # pragma: no cover - keep consistent with overall behavior
    requests = None  # type: ignore


def create_tool() -> Tool:
    def run(args: Dict[str, Any]) -> str:
        if not requests:
            return "ERROR: 'requests' package is unavailable"
        url = args.get("url")
        if not url:
            return "ERROR: 'url' argument is required"
        try:
            response = requests.get(url, timeout=20)
        except Exception as exc:
            return f"ERROR: failed to fetch URL: {exc}"
        content_type = response.headers.get("content-type", "")
        text = response.text
        if "html" in content_type.lower():
            text = strip_html(text)
        else:
            text = text.strip()
        return truncate(text)

    return Tool(
        name="read_url",
        description="Fetch the text content of a webpage and return a trimmed plain-text summary.",
        schema='{"url": "https://example.com"}',
        handler=run,
    )
