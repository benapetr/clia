from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Optional

try:
    import requests
except ImportError:  # pragma: no cover - keep behavior aligned with other modules
    requests = None  # type: ignore


class ChatClient:
    def chat_stream(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        options: Optional[Dict[str, Any]] = None,
    ) -> Iterable[str]:
        raise NotImplementedError


class OllamaClient(ChatClient):
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
        if response.status_code == 404:
            # Older Ollama versions or missing chat endpoint – attempt fallback.
            fallback_error = _extract_error(response)
            if fallback_error and "model" in fallback_error.lower() and "not found" in fallback_error.lower():
                raise RuntimeError(fallback_error)
            yield from self._chat_via_generate(model, messages, options)
            return
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

    def _chat_via_generate(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        options: Optional[Dict[str, Any]],
    ) -> Iterable[str]:
        prompt = _messages_to_prompt(messages)
        url = f"{self.base_url}/api/generate"
        payload: Dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "stream": True,
        }
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
            chunk = data.get("response")
            if chunk:
                yield chunk
            if data.get("done", False):
                break


class OpenAIClient(ChatClient):
    def __init__(self, base_url: str, api_key: str, timeout: int = 120) -> None:
        if not requests:
            raise RuntimeError("The 'requests' package is required to use OpenAIClient")
        if not api_key:
            raise ValueError("OpenAI API key is required")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def chat_stream(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        options: Optional[Dict[str, Any]] = None,
    ) -> Iterable[str]:
        url = f"{self.base_url}/chat/completions"
        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": True,
        }
        if options:
            payload.update({k: v for k, v in options.items() if v is not None})
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            stream=True,
            timeout=self.timeout,
        )
        response.raise_for_status()
        yield from _parse_sse_stream(response)


class MistralClient(ChatClient):
    def __init__(self, base_url: str, api_key: str, timeout: int = 120) -> None:
        if not requests:
            raise RuntimeError("The 'requests' package is required to use MistralClient")
        if not api_key:
            raise ValueError("Mistral API key is required")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def chat_stream(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        options: Optional[Dict[str, Any]] = None,
    ) -> Iterable[str]:
        url = f"{self.base_url}/chat/completions"
        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": True,
        }
        if options:
            payload.update({k: v for k, v in options.items() if v is not None})
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            stream=True,
            timeout=self.timeout,
        )
        response.raise_for_status()
        yield from _parse_sse_stream(response)


def _parse_sse_stream(response: Any) -> Iterable[str]:
    for raw_line in response.iter_lines(decode_unicode=True):
        if not raw_line:
            continue
        line = raw_line
        if line.startswith("data: "):
            line = line[len("data: ") :]
        if line == "[DONE]":
            break
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        choices = data.get("choices") or []
        for choice in choices:
            delta = choice.get("delta") or {}
            content = delta.get("content")
            if content:
                yield content


def create_client(
    provider: str,
    endpoint: str,
    api_key: Optional[str],
    timeout: int,
) -> ChatClient:
    provider_normalized = provider.lower()
    if provider_normalized == "ollama":
        return OllamaClient(endpoint, timeout=timeout)
    if provider_normalized == "openai":
        if api_key is None:
            raise ValueError("OpenAI provider requires an API key")
        return OpenAIClient(endpoint, api_key=api_key, timeout=timeout)
    if provider_normalized == "mistral":
        if api_key is None:
            raise ValueError("Mistral provider requires an API key")
        return MistralClient(endpoint, api_key=api_key, timeout=timeout)
    raise ValueError(f"Unsupported provider '{provider}'")


def _extract_error(response: Any) -> str:
    try:
        data = response.json()
        if isinstance(data, dict):
            error = data.get("error")
            if isinstance(error, str):
                return error
    except ValueError:
        pass
    try:
        text = response.text
        if text:
            return text
    except Exception:  # pragma: no cover - extremely defensive
        return ""
    return ""


def _messages_to_prompt(messages: List[Dict[str, Any]]) -> str:
    parts: List[str] = []
    for message in messages:
        role = message.get("role", "")
        content = message.get("content", "")
        if not content:
            continue
        if role == "system":
            parts.append(f"System: {content}")
        elif role == "assistant":
            parts.append(f"Assistant: {content}")
        else:
            parts.append(f"User: {content}")
    parts.append("Assistant:")
    return "\n\n".join(parts)
