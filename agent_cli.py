#!/usr/bin/env python3
"""Interactive CLI agent powered by a local Ollama model."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from html import unescape
from typing import Any, Callable, Dict, Iterable, List, Optional

try:
    import requests
except ImportError:  # pragma: no cover - requests should be available but we fail gracefully
    requests = None  # type: ignore


@dataclass
class Tool:
    name: str
    description: str
    schema: str
    handler: Callable[[Dict[str, Any]], str]

    def run(self, args: Dict[str, Any]) -> str:
        return self.handler(args)


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' already registered")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def describe_for_prompt(self) -> str:
        lines = []
        for tool in self._tools.values():
            lines.append(f"- {tool.name}: {tool.description}\n  args schema: {tool.schema}")
        return "\n".join(lines)

    def execute(self, name: str, args: Dict[str, Any]) -> str:
        tool = self.get(name)
        if not tool:
            return f"ERROR: unknown tool '{name}'"
        try:
            return tool.run(args)
        except Exception as exc:  # pragma: no cover - defensive
            return f"ERROR while running '{name}': {exc}"


class OllamaClient:
    def __init__(self, base_url: str, timeout: int = 120) -> None:
        if not requests:
            raise RuntimeError("The 'requests' package is required to use OllamaClient")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def chat_stream(self, model: str, messages: List[Dict[str, Any]], options: Optional[Dict[str, Any]] = None) -> Iterable[str]:
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


class AgentCLI:
    TOOL_CALL_PATTERN = re.compile(r"<tool name=\"(?P<name>[a-zA-Z0-9_\-]+)\">\s*(?P<body>\{.*?\})\s*</tool>", re.DOTALL)
    COLOR_RESET = "\033[0m"
    COLOR_AGENT = "\033[36m"  # cyan
    COLOR_USER = "\033[33m"  # yellow

    def __init__(
        self,
        model: str,
        client: OllamaClient,
        tools: ToolRegistry,
        options: Optional[Dict[str, Any]] = None,
        use_color: Optional[bool] = None,
    ) -> None:
        self.model = model
        self.client = client
        self.tools = tools
        self.options = options or {}
        self.system_prompt = self._build_system_prompt()
        self._use_color = sys.stdout.isatty() if use_color is None else use_color

    def _label(self, label: str, color: str) -> str:
        if not self._use_color:
            return label
        return f"{color}{label}{self.COLOR_RESET}"

    def _build_system_prompt(self) -> str:
        tool_descriptions = self.tools.describe_for_prompt()
        instructions = textwrap.dedent(
            f"""
            You are an autonomous CLI agent. You may use the following tools when necessary:\n{tool_descriptions}\n\n"
            "To call a tool respond with exactly:\n"
            "<tool name=\"{{tool_name}}\">\n"
            "{{JSON arguments}}\n"
            "</tool>\n\n"
            "Do not include additional commentary when calling a tool.\n"
            "When you receive a tool result it will be wrapped in <tool_result name=\"...\"> tags.\n"
            "Continue the conversation after processing the tool result.\n"
            "When no tool is needed, respond directly to the user.\n"
            "If you need more information from the user, ask for it explicitly.\n"
            """
        ).strip()
        return instructions

    def start(self, initial_message: Optional[str] = None) -> None:
        conversation: List[Dict[str, Any]] = [{"role": "system", "content": self.system_prompt}]
        if initial_message:
            conversation.append({"role": "user", "content": initial_message})
            self._agent_turn(conversation)
        while True:
            try:
                user_label = self._label("you>", self.COLOR_USER)
                user_input = input(f"{user_label} ")
            except (EOFError, KeyboardInterrupt):
                print("\nExiting.")
                return
            if not user_input.strip():
                continue
            if user_input.strip().lower() in {"exit", "quit"}:
                print("Bye.")
                return
            conversation.append({"role": "user", "content": user_input})
            self._agent_turn(conversation)

    def _agent_turn(self, conversation: List[Dict[str, Any]]) -> None:
        while True:
            assistant_reply = self._stream_response(conversation)
            if assistant_reply is None:
                return
            conversation.append({"role": "assistant", "content": assistant_reply})
            tool_call = self._parse_tool_call(assistant_reply)
            if not tool_call:
                break
            tool_name, tool_args = tool_call
            print(f"\n[tool call] {tool_name} {tool_args}")
            tool_result = self.tools.execute(tool_name, tool_args)
            print(f"[tool result]\n{tool_result}\n")
            wrapped_result = self._format_tool_result(tool_name, tool_result)
            conversation.append({"role": "user", "content": wrapped_result})

    def _stream_response(self, conversation: List[Dict[str, Any]]) -> Optional[str]:
        agent_label = self._label("agent>", self.COLOR_AGENT)
        print(f"{agent_label} ", end="", flush=True)
        chunks: List[str] = []
        try:
            for delta in self.client.chat_stream(self.model, conversation, self.options):
                print(delta, end="", flush=True)
                chunks.append(delta)
        except Exception as exc:
            print(f"\n[error] {exc}")
            return None
        print()
        return "".join(chunks).strip()

    def _parse_tool_call(self, message: str) -> Optional[tuple[str, Dict[str, Any]]]:
        match = self.TOOL_CALL_PATTERN.search(message)
        if not match:
            return None
        name = match.group("name")
        raw_body = match.group("body")
        try:
            args = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            return name, {"error": f"Invalid JSON arguments: {exc}"}
        return name, args

    @staticmethod
    def _format_tool_result(name: str, result: str) -> str:
        return f"<tool_result name=\"{name}\">\n{result}\n</tool_result>"


def _strip_html(html_text: str) -> str:
    text = re.sub(r"<script.*?</script>", "", html_text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _truncate(text: str, limit: int = 4000) -> str:
    if len(text) <= limit:
        return text
    return f"{text[:limit]}\n...[truncated {len(text) - limit} characters]"


def _create_shell_tool(shell_timeout: int = 60) -> Tool:
    def run(args: Dict[str, Any]) -> str:
        command = args.get("command")
        if not command:
            return "ERROR: 'command' argument is required"
        try:
            completed = subprocess.run(
                command,
                shell=True,
                check=False,
                capture_output=True,
                text=True,
                timeout=shell_timeout,
            )
        except subprocess.TimeoutExpired:
            return "ERROR: command timed out"
        output = completed.stdout if completed.stdout else ""
        error = completed.stderr if completed.stderr else ""
        status = f"exit code {completed.returncode}"
        if error:
            output = f"{output}\n[stderr]\n{error}" if output else f"[stderr]\n{error}"
        return _truncate(f"{status}\n{output}".strip())

    return Tool(
        name="run_shell",
        description=f"Execute a shell command inside the current workspace (timeout {shell_timeout}s).",
        schema='{"command": "<shell command string>"}',
        handler=run,
    )


def _create_read_url_tool() -> Tool:
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
            text = _strip_html(text)
        else:
            text = text.strip()
        return _truncate(text)

    return Tool(
        name="read_url",
        description="Fetch the text content of a webpage and return a trimmed plain-text summary.",
        schema='{"url": "https://example.com"}',
        handler=run,
    )


def build_tools(shell_timeout: int = 60) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(_create_shell_tool(shell_timeout=shell_timeout))
    registry.register(_create_read_url_tool())
    return registry


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Agentic CLI powered by a local Ollama model.")
    parser.add_argument("prompt", nargs="*", help="Optional initial message to send to the agent.")
    parser.add_argument("--model", default="qwen3:14b", help="Ollama model name (default: qwen3:14b).")
    parser.add_argument("--base-url", default="http://localhost:11434", help="Base URL for Ollama (default: http://localhost:11434).")
    parser.add_argument("--temperature", type=float, default=0.7, help="Sampling temperature passed to Ollama.")
    parser.add_argument(
        "--shell-timeout",
        type=int,
        default=60,
        help="Timeout in seconds for the run_shell tool (default: 60).",
    )
    parser.add_argument(
        "--ollama-timeout",
        type=int,
        default=120,
        help="Request timeout in seconds for Ollama responses (default: 120).",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable ANSI colors in CLI prompts (auto-detected by default).",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    tools = build_tools(shell_timeout=args.shell_timeout)
    client = OllamaClient(args.base_url, timeout=args.ollama_timeout)
    agent = AgentCLI(
        model=args.model,
        client=client,
        tools=tools,
        options={"temperature": args.temperature},
        use_color=False if args.no_color else None,
    )
    initial_message = " ".join(args.prompt).strip() if args.prompt else None
    agent.start(initial_message if initial_message else None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
