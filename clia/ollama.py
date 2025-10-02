from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Optional

try:
    import requests
except ImportError:  # pragma: no cover - gracefully handle missing dependency
    requests = None  # type: ignore


class OllamaClient:
    def __init__(self, base_url: str, timeout: int = 120) -> None:
        if not requests:
            raise RuntimeError("The 'requests' package is required to use OllamaClient")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def chat_stream(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        options: Optional[Dict[str, Any]] = None,
    ) -> Iterable[str]:
        url = f"{self.base_url}/api/chat"
        payload: Dict[str, Any] = {"model": model, "messages": messages, "stream": True}
        if options:
            payload["options"] = options
        response = requests.post(url, json=payload, stream=True, timeout=self.timeout)
        response.raise_for_status()
        for line in response.iter_lines():
            if not line:
                continue
            data = json.loads(line)
            if data.get("error"):
                raise RuntimeError(data["error"])
            message = data.get("message") or {}
            content = message.get("content", "")
            if content:
                yield content
            if data.get("done", False):
                break
