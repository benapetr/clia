from __future__ import annotations

from typing import Any, Dict

from bs4 import BeautifulSoup

from clia.tooling import Tool
from clia.utils import truncate

import requests


def create_tool() -> Tool:
    def run(args: Dict[str, Any]) -> str:
        url = args.get("url")
        if not url:
            return "ERROR: 'url' argument is required"
        try:
            response = requests.get(url, timeout=20)
            response.raise_for_status()
        except Exception as exc:
            return f"ERROR: failed to fetch URL: {exc}"
        content_type = response.headers.get("content-type", "")
        if "html" in content_type.lower() or not content_type:
            soup = BeautifulSoup(response.text, "html.parser")
            links: list[str] = []
            for anchor in soup.find_all("a"):
                href = anchor.get("href")
                label = anchor.get_text(" ", strip=True)
                if href and label:
                    links.append(f"- {label} -> {href}")
            text = soup.get_text(" ", strip=True)
            combined = text
            if links:
                combined = text + "\n\nLinks:\n" + "\n".join(links)
        else:
            combined = response.text.strip()
        return truncate(combined)

    return Tool(
        name="read_url",
        description="Fetch the text content of a webpage and return a trimmed plain-text summary.",
        schema='{"url": "https://example.com"}',
        handler=run,
    )
