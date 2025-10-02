from __future__ import annotations

from typing import Any, Dict, List

from clia.tooling import Tool
from clia.utils import truncate

try:
    import requests
except ImportError:  # pragma: no cover - aligned with other tools
    requests = None  # type: ignore


def create_tool() -> Tool:
    def run(args: Dict[str, Any]) -> str:
        if not requests:
            return "ERROR: 'requests' package is unavailable"
        query = args.get("query")
        if not query:
            return "ERROR: 'query' argument is required"
        params = {
            "q": query,
            "format": "json",
            "no_html": 1,
            "no_redirect": 1,
        }
        try:
            response = requests.get(
                "https://duckduckgo.com/",
                params=params,
                headers={"User-Agent": "clia-agent/1.0"},
                timeout=20,
            )
            response.raise_for_status()
        except Exception as exc:
            return f"ERROR: search request failed: {exc}"
        try:
            data = response.json()
        except ValueError as exc:
            return f"ERROR: failed to parse search results: {exc}"
        snippets: List[str] = []
        for item in data.get("Results", []):
            text = item.get("Text")
            url = item.get("FirstURL")
            if text and url:
                snippets.append(f"- {text} ({url})")
        for topic in data.get("RelatedTopics", []):
            if isinstance(topic, dict):
                text = topic.get("Text")
                url = topic.get("FirstURL")
                if text and url:
                    snippets.append(f"- {text} ({url})")
            elif isinstance(topic, list):
                for entry in topic:
                    text = entry.get("Text")
                    url = entry.get("FirstURL")
                    if text and url:
                        snippets.append(f"- {text} ({url})")
        if not snippets:
            abstract = data.get("AbstractText")
            if abstract:
                snippets.append(abstract)
        if not snippets:
            return "No search results found."
        return truncate("Search results:\n" + "\n".join(snippets[:10]))

    return Tool(
        name="search_internet",
        description="Run a DuckDuckGo query and return the top matching snippets.",
        schema='{"query": "open source llm agents"}',
        handler=run,
    )
