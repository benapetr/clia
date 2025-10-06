from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Optional

import requests


class ChatClient:
    def __init__(self) -> None:
        self.last_usage: Optional[Dict[str, int]] = None
        self.last_payload: Optional[Dict[str, Any]] = None

    def reset_usage(self) -> None:
        self.last_usage = None
        self.last_payload = None

    def set_last_payload(self, payload: Dict[str, Any]) -> None:
        self.last_payload = payload

    def get_last_payload(self) -> Optional[Dict[str, Any]]:
        return self.last_payload

    def chat_stream(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        options: Optional[Dict[str, Any]] = None,
    ) -> Iterable[str]:
        raise NotImplementedError

    def get_last_usage(self) -> Optional[Dict[str, int]]:
        return self.last_usage


class OllamaClient(ChatClient):
    def __init__(self, base_url: str, timeout: int = 120) -> None:
        super().__init__()
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def chat_stream(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        options: Optional[Dict[str, Any]] = None,
    ) -> Iterable[str]:
        self.reset_usage()
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
        in_thinking = False
        for line in response.iter_lines():
            if not line:
                continue
            data = json.loads(line)
            if data.get("error"):
                raise RuntimeError(data["error"])
            self.set_last_payload(data)
            message = data.get("message") or {}
            content = message.get("content", "")
            thinking = message.get("thinking", "")
            tool_calls = message.get("tool_calls", [])
            
            # Handle thinking tokens
            if thinking:
                if not in_thinking:
                    yield "<think>"
                    in_thinking = True
                yield thinking
            elif in_thinking:
                # We have content but no thinking, close the thinking block
                yield "</think>\n"
                in_thinking = False
            
            # Handle tool calls - convert to text format so they're visible and stored
            if tool_calls:
                for call in tool_calls:
                    function = call.get("function") or {}
                    name = function.get("name")
                    arguments = function.get("arguments")
                    if name and arguments is not None:
                        # Format arguments as JSON string if needed
                        if isinstance(arguments, dict):
                            args_str = json.dumps(arguments, ensure_ascii=False)
                        elif isinstance(arguments, str):
                            # Might already be JSON string, try to parse and reformat
                            try:
                                parsed = json.loads(arguments)
                                args_str = json.dumps(parsed, ensure_ascii=False)
                            except json.JSONDecodeError:
                                args_str = arguments
                        else:
                            args_str = json.dumps({"value": arguments}, ensure_ascii=False)
                        
                        yield f"<tool name=\"{name}\">\n{args_str}\n</tool>\n"
            
            if content:
                yield content
            if data.get("done", False):
                # Close thinking block if still open
                if in_thinking:
                    yield "</think>\n"
                    in_thinking = False
                usage = _parse_ollama_usage(data)
                if usage:
                    self.last_usage = usage
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
            self.set_last_payload(data)
            chunk = data.get("response")
            if chunk:
                yield chunk
            if data.get("done", False):
                usage = _parse_ollama_usage(data)
                if usage:
                    self.last_usage = usage
                break


class OpenAIClient(ChatClient):
    def __init__(self, base_url: str, api_key: str, timeout: int = 120) -> None:
        if not api_key:
            raise ValueError("OpenAI API key is required")
        super().__init__()
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def chat_stream(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        options: Optional[Dict[str, Any]] = None,
    ) -> Iterable[str]:
        self.reset_usage()
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
        yield from _parse_sse_stream(response, self)


class MistralClient(ChatClient):
    def __init__(self, base_url: str, api_key: str, timeout: int = 120) -> None:
        if not api_key:
            raise ValueError("Mistral API key is required")
        super().__init__()
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def chat_stream(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        options: Optional[Dict[str, Any]] = None,
    ) -> Iterable[str]:
        self.reset_usage()
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
        yield from _parse_sse_stream(response, self)


def _parse_sse_stream(response: Any, client: ChatClient) -> Iterable[str]:
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
        error_payload = data.get("error")
        if error_payload:
            client.set_last_payload({"error": error_payload})
            if isinstance(error_payload, dict) and "message" in error_payload:
                raise RuntimeError(error_payload["message"])
            raise RuntimeError(str(error_payload))
        client.set_last_payload(data)
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


def _parse_ollama_usage(data: Dict[str, Any]) -> Optional[Dict[str, int]]:
    prompt_tokens = int(data.get("prompt_eval_count", 0) or 0)
    completion_tokens = int(data.get("eval_count", 0) or 0)
    total_tokens = prompt_tokens + completion_tokens
    if total_tokens == 0:
        return None
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }


def _extract_completions_usage(payload: Optional[Dict[str, Any]]) -> Optional[Dict[str, int]]:
    if not isinstance(payload, dict):
        return None
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return None
    result: Dict[str, int] = {}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        value = usage.get(key)
        if value is None:
            continue
        try:
            result[key] = int(value)
        except (TypeError, ValueError):
            continue
    return result or None
