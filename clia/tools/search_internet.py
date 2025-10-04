from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from clia.tooling import Tool
from clia.utils import truncate
import requests
from ddgs import DDGS


@dataclass
class SearchConfig:
    provider: str = "duckduckgo"
    google_api_key: Optional[str] = None
    google_engine_id: Optional[str] = None


def create_tool(search_config: Optional[SearchConfig] = None) -> Tool:
    config = search_config or SearchConfig()
    provider = (config.provider or "duckduckgo").lower()
    if provider not in {"duckduckgo", "google"}:
        provider = "duckduckgo"

    def run(args: Dict[str, Any]) -> str:
        query = args.get("query")
        if not query:
            return "ERROR: 'query' argument is required"
        if provider == "google":
            if not config.google_api_key or not config.google_engine_id:
                return "ERROR: Google search requires api_key and engine_id in config.ini"
            params = {
                "key": config.google_api_key,
                "cx": config.google_engine_id,
                "q": query,
                "num": 10,
            }
            try:
                response = requests.get(
                    "https://www.googleapis.com/customsearch/v1",
                    params=params,
                    timeout=20,
                )
                response.raise_for_status()
            except Exception as exc:
                return f"ERROR: Google search request failed: {exc}"
            try:
                data = response.json()
            except ValueError as exc:
                return f"ERROR: failed to parse Google search results: {exc}"
            items = data.get("items") or []
            if not items:
                return "No search results found."
            snippets = []
            for item in items[:10]:
                title = item.get("title") or "(untitled)"
                link = item.get("link") or ""
                snippet_text = item.get("snippet") or ""
                entry = f"- {title}"
                if snippet_text:
                    entry += f" — {snippet_text}"
                if link:
                    entry += f" ({link})"
                snippets.append(entry)
            return truncate("Search results:\n" + "\n".join(snippets))
        # default to DuckDuckGo
        snippets: List[str] = []
        try:
            with DDGS() as ddgs_client:
                for result in ddgs_client.text(
                    query,
                    safesearch="moderate",
                    timelimit=None,
                    max_results=10,
                ):
                    title = result.get("title") or "(untitled)"
                    body = result.get("body") or ""
                    href = result.get("href") or ""
                    entry = f"- {title}"
                    if body:
                        entry += f" — {body}"
                    if href:
                        entry += f" ({href})"
                    snippets.append(entry)
        except Exception as exc:
            return f"ERROR: DuckDuckGo search failed: {exc}"
        if not snippets:
            return "No search results found."
        return truncate("Search results:\n" + "\n".join(snippets))

    return Tool(
        name="search_internet",
        description=f"Run an internet search using {provider.title()} and return matching snippets.",
        schema='{"query": "open source llm agents"}',
        handler=run,
    )
