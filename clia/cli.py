from __future__ import annotations

import json
import os
import re
import sys
import textwrap
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from clia.approval import ToolApprovalManager
from clia.clients import ChatClient
from clia.commands import CommandOutcome, build_default_registry
from clia.tooling import ToolRegistry


class AgentCLI:
    TOOL_CALL_PATTERN = re.compile(r"<tool name=\"(?P<name>[a-zA-Z0-9_\-]+)\">\s*(?P<body>\{.*?\})\s*</tool>", re.DOTALL)
    COLOR_RESET = "\033[0m"
    COLOR_AGENT = "\033[36m"  # cyan
    COLOR_USER = "\033[33m"  # yellow
    COLOR_THINK = "\033[90m"  # light gray

    def __init__(
        self,
        model: str,
        provider: str,
        client: ChatClient,
        tools: ToolRegistry,
        approval_mgr: ToolApprovalManager,
        options: Optional[Dict[str, Any]] = None,
        use_color: Optional[bool] = None,
        session_dir: Optional[Path] = None,
    ) -> None:
        self.model = model
        self.provider = provider
        self.client = client
        self.tools = tools
        self.approval_mgr = approval_mgr
        self.options = options or {}
        self.system_prompt = self._build_system_prompt()
        self._use_color = sys.stdout.isatty() if use_color is None else use_color
        self.session_dir = Path(session_dir) if session_dir else Path.cwd() / "sessions"
        self.conversation: List[Dict[str, Any]] = []
        self.command_registry = build_default_registry()

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
        self.conversation = [{"role": "system", "content": self.system_prompt}]
        if initial_message:
            self.conversation.append({"role": "user", "content": initial_message})
            self._agent_turn()
        while True:
            try:
                user_label = self._label("you>", self.COLOR_USER)
                user_input = input(f"{user_label} ")
            except (EOFError, KeyboardInterrupt):
                print("\nExiting.")
                return
            if not user_input.strip():
                continue
            stripped = user_input.strip()
            if stripped.startswith(self.command_registry.prefix):
                outcome = self.command_registry.dispatch(stripped, self)
                if outcome == CommandOutcome.EXIT:
                    print("Bye.")
                    return
                continue
            if stripped.lower() in {"exit", "quit"}:
                print("Bye.")
                return
            self.conversation.append({"role": "user", "content": user_input})
            self._agent_turn()

    def _agent_turn(self) -> None:
        while True:
            assistant_reply = self._stream_response(self.conversation)
            if assistant_reply is None:
                return
            self.conversation.append({"role": "assistant", "content": assistant_reply})
            tool_call = self._parse_tool_call(assistant_reply)
            if not tool_call:
                break
            tool_name, tool_args = tool_call
            print(f"\n[tool call] {tool_name} {tool_args}")
            if not self._approve_tool_run(tool_name, tool_args):
                print("[tool skipped] execution denied by user")
                denial = "Tool execution denied by user."
                wrapped_result = self._format_tool_result(tool_name, denial)
                self.conversation.append({"role": "user", "content": wrapped_result})
                continue
            tool_result = self.tools.execute(tool_name, tool_args)
            print(f"[tool result]\n{tool_result}\n")
            wrapped_result = self._format_tool_result(tool_name, tool_result)
            self.conversation.append({"role": "user", "content": wrapped_result})

    def _stream_response(self, conversation: List[Dict[str, Any]]) -> Optional[str]:
        agent_label = self._label("agent>", self.COLOR_AGENT)
        print(f"{agent_label} ", end="", flush=True)
        chunks: List[str] = []
        buffer = ""
        in_think = False
        try:
            for delta in self.client.chat_stream(self.model, conversation, self.options):
                to_print, buffer, in_think = self._render_think_chunk(delta, buffer, in_think)
                if to_print:
                    print(to_print, end="", flush=True)
                chunks.append(delta)
            tail, buffer, in_think = self._render_think_chunk("", buffer, in_think, finalize=True)
            if tail:
                print(tail, end="", flush=True)
        except Exception as exc:
            print(f"\n[error] {exc}")
            return None
        print()
        return "".join(chunks).strip()

    def _render_think_chunk(
        self,
        chunk: str,
        buffer: str,
        in_think: bool,
        finalize: bool = False,
    ) -> Tuple[str, str, bool]:
        if not self._use_color:
            return chunk, "", False

        buffer += chunk
        output_parts: List[str] = []
        open_tag = "<think>"
        close_tag = "</think>"

        while buffer:
            if not in_think:
                idx = buffer.find(open_tag)
                if idx == -1:
                    if finalize:
                        output_parts.append(buffer)
                        buffer = ""
                    else:
                        keep = self._partial_tag_suffix(buffer, open_tag)
                        flush_len = len(buffer) - keep
                        if flush_len:
                            output_parts.append(buffer[:flush_len])
                            buffer = buffer[flush_len:]
                        else:
                            break
                    continue
                if idx:
                    output_parts.append(buffer[:idx])
                output_parts.append(self._color_think(open_tag))
                buffer = buffer[idx + len(open_tag) :]
                in_think = True
            else:
                idx = buffer.find(close_tag)
                if idx == -1:
                    if finalize:
                        if buffer:
                            output_parts.append(self._color_think(buffer))
                            buffer = ""
                        break
                    keep = self._partial_tag_suffix(buffer, close_tag)
                    flush_len = len(buffer) - keep
                    if flush_len:
                        segment = buffer[:flush_len]
                        output_parts.append(self._color_think(segment))
                        buffer = buffer[flush_len:]
                    else:
                        break
                    continue
                if idx:
                    output_parts.append(self._color_think(buffer[:idx]))
                output_parts.append(self._color_think(close_tag))
                buffer = buffer[idx + len(close_tag) :]
                in_think = False

        return "".join(output_parts), buffer, in_think

    def _partial_tag_suffix(self, text: str, tag: str) -> int:
        max_check = min(len(text), len(tag) - 1)
        for size in range(max_check, 0, -1):
            if text.endswith(tag[:size]):
                return size
        return 0

    def _color_think(self, text: str) -> str:
        if not text:
            return text
        return f"{self.COLOR_THINK}{text}{self.COLOR_RESET}"

    def _approve_tool_run(self, name: str, args: Dict[str, Any]) -> bool:
        if self.approval_mgr.is_approved(name):
            return True
        decision = self._prompt_tool_consent(name, args)
        if decision == "n":
            return False
        if decision == "a":
            self.approval_mgr.approve_always(name)
        return True

    def save_session(self, raw_name: str) -> None:
        path = self._resolve_save_path(raw_name)
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"conversation": self.conversation}
        try:
            with path.open("w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
        except OSError as exc:
            print(f"Failed to save session: {exc}")
            return
        print(f"Session saved to {path}")

    def load_session(self, raw_name: str) -> None:
        path = self._resolve_load_path(raw_name)
        if path is None:
            return
        try:
            with path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"Failed to load session: {exc}")
            return
        conversation = data.get("conversation")
        if not isinstance(conversation, list):
            print("Invalid session file format.")
            return
        # Ensure current system prompt is applied
        if conversation and conversation[0].get("role") == "system":
            conversation[0]["content"] = self.system_prompt
        else:
            conversation.insert(0, {"role": "system", "content": self.system_prompt})
        self.conversation = conversation
        print(f"Session loaded from {path}. Conversation length: {len(self.conversation)} messages.")

    def session_info(self) -> None:
        message_count = len(self.conversation)
        approx_tokens = self.estimate_tokens()
        print(f"Provider: {self.provider}")
        print(f"Model: {self.model}")
        print(f"Messages in session: {message_count}")
        print(f"Approximate tokens: {approx_tokens}")

    def estimate_tokens(self) -> int:
        total_words = 0
        for message in self.conversation:
            content = message.get("content")
            if not content:
                continue
            total_words += len(content.split())
        return total_words

    def list_sessions(self) -> None:
        directory = self.session_dir
        if not directory.exists():
            print(f"Save directory '{directory}' does not exist.")
            return
        entries = sorted(directory.glob("*.json"))
        if not entries:
            print("No saved sessions found.")
            return
        print(f"Saved sessions in {directory}:")
        for entry in entries:
            size = entry.stat().st_size
            print(f"  {entry.name}  ({size} bytes)")

    def remove_session(self, raw_name: str) -> None:
        path = self._resolve_load_path(raw_name)
        if path is None:
            return
        try:
            path.unlink()
        except OSError as exc:
            print(f"Failed to remove session: {exc}")
            return
        print(f"Removed session file {path}")

    def show_tail(self, count: int) -> None:
        relevant = self.conversation[-count:]
        if not relevant:
            print("Conversation is empty.")
            return
        for message in relevant:
            role = message.get("role", "unknown").upper()
            content = message.get("content", "")
            print(f"[{role}] {content}")

    @staticmethod
    def _sanitize_session_name(name: str) -> str:
        sanitized = re.sub(r"[^a-zA-Z0-9_\-]", "_", name.strip())
        return sanitized.strip("_")

    def _resolve_save_path(self, raw_name: str) -> Optional[Path]:
        raw_name = raw_name.strip()
        if not raw_name:
            print("Usage: /save <name or path>")
            return None
        if os.path.isabs(raw_name) or raw_name.endswith(".json") or any(sep in raw_name for sep in ("/", "\\")):
            path = Path(raw_name).expanduser()
            if path.is_dir():
                print("Cannot save to a directory. Provide a file path.")
                return None
            if path.suffix != ".json":
                path = path.with_suffix(".json")
            return path
        name = self._sanitize_session_name(raw_name)
        if not name:
            print("Invalid session name. Use letters, numbers, hyphen, or underscore.")
            return None
        return self.session_dir / f"{name}.json"

    def _resolve_load_path(self, raw_name: str) -> Optional[Path]:
        raw_name = raw_name.strip()
        if not raw_name:
            print("Usage: /load <name or path>")
            return None
        candidate = Path(raw_name).expanduser()
        if candidate.exists() and candidate.is_file():
            return candidate
        if os.path.isabs(raw_name) or any(sep in raw_name for sep in ("/", "\\")):
            if candidate.exists():
                if candidate.is_dir():
                    print("Path points to a directory, not a file.")
                    return None
                return candidate
            print(f"Session file '{candidate}' not found.")
            return None
        name = self._sanitize_session_name(raw_name)
        if not name:
            print("Invalid session name. Use letters, numbers, hyphen, or underscore.")
            return None
        path = self.session_dir / f"{name}.json"
        if not path.exists():
            print(f"Session '{name}' not found at {path}")
            return None
        return path

    def _prompt_tool_consent(self, name: str, args: Dict[str, Any]) -> str:
        pretty_args = json.dumps(args, indent=2, sort_keys=True)
        print("Requested tool execution:")
        print(f"  name: {name}")
        print("  args:")
        for line in pretty_args.splitlines():
            print(f"    {line}")
        while True:
            response = input("Allow this tool? [y]es/[n]o/[a]lways: ").strip().lower()
            if response in {"y", "n", "a"}:
                return response
            print("Please respond with 'y', 'n', or 'a'.")

    def _parse_tool_call(self, message: str) -> Optional[Tuple[str, Dict[str, Any]]]:
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
