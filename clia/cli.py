from __future__ import annotations

import json
import re
import sys
import textwrap
from typing import Any, Dict, Iterable, List, Optional, Tuple

from clia.approval import ToolApprovalManager
from clia.ollama import OllamaClient
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
        client: OllamaClient,
        tools: ToolRegistry,
        approval_mgr: ToolApprovalManager,
        options: Optional[Dict[str, Any]] = None,
        use_color: Optional[bool] = None,
    ) -> None:
        self.model = model
        self.client = client
        self.tools = tools
        self.approval_mgr = approval_mgr
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
            if not self._approve_tool_run(tool_name, tool_args):
                print("[tool skipped] execution denied by user")
                denial = "Tool execution denied by user."
                wrapped_result = self._format_tool_result(tool_name, denial)
                conversation.append({"role": "user", "content": wrapped_result})
                continue
            tool_result = self.tools.execute(tool_name, tool_args)
            print(f"[tool result]\n{tool_result}\n")
            wrapped_result = self._format_tool_result(tool_name, tool_result)
            conversation.append({"role": "user", "content": wrapped_result})

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
