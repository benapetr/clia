from __future__ import annotations

import json
import os
import re
import signal
import sys
import textwrap
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from clia.approval import ToolApprovalManager
from clia.clients import ChatClient
from clia.commands import CommandOutcome, build_default_registry
from clia.tooling import ToolRegistry
from clia.utils import (
    get_truncation_limit,
    is_truncation_enabled,
    is_unsafe_enabled,
    set_truncation_enabled,
    set_unsafe_enabled,
)


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
        system_prompt_template: Optional[str] = None,
        debug_log_path: Optional[Path] = None,
        unsafe_default: bool = False,
    ) -> None:
        self.model = model
        self.provider = provider
        self.client = client
        self.tools = tools
        self.approval_mgr = approval_mgr
        self.options = options or {}
        self.system_prompt_template = system_prompt_template
        self.system_prompt = self._build_system_prompt()
        self._use_color = sys.stdout.isatty() if use_color is None else use_color
        self.session_dir = Path(session_dir) if session_dir else Path.cwd() / "sessions"
        self.conversation: List[Dict[str, Any]] = []
        self.debug_log_path = Path(debug_log_path) if debug_log_path else Path("/tmp/clia.log")
        self.debug_enabled = False
        self.slomo_seconds = 0.0
        self.unsafe_enabled = bool(unsafe_default)
        set_unsafe_enabled(self.unsafe_enabled)
        self.command_registry = build_default_registry()
        self.usage_totals = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
        self.cancel_requested = False
        self._sigint_registered = False
        self._original_sigint = None
        self._sigint_message_pending = False

    def _label(self, label: str, color: str) -> str:
        if not self._use_color:
            return label
        return f"{color}{label}{self.COLOR_RESET}"

    def _build_system_prompt(self) -> str:
        tool_descriptions = self.tools.describe_for_prompt()
        if self.system_prompt_template:
            return self._render_system_prompt(self.system_prompt_template, tool_descriptions)
        instructions = textwrap.dedent(
            f"""
            You are an autonomous CLI agent. You may use the following tools when necessary:\n{tool_descriptions}\n\n"
            "To call a tool respond with exactly:\n"
            "<tool name=\"{{tool_name}}\">\n"
            "{{JSON arguments}}\n"
            "</tool>\n\n"
            "Do not include additional commentary when calling a tool.\n"
            "IMPORTANT: Tools are always executed from same fixed working directory, that means cd (change directory) doesn't persist between tool calls. Use absolute paths where you can.\n"
            "When you receive a tool result it will be wrapped in <tool_result name=\"...\"> tags.\n"
            "When you call any tool, you are going to be given the result immediately and if necessary you can directly call another tool.\n"
            "If the output of tool results wasn't sufficient to get all information needed to provide high quality answer, you may call another tool.\n"
            "Keep in mind that you are not just a simple chatbot, you are autonomous agent tool, you can keep calling various tools as long as you need to achieve your objective.\n"
            "When no tool is needed, respond directly to the user.\n"
            "Continue the conversation after achieving the objective or if clarification or more information from user is needed.\n"
            """
        ).strip()
        return instructions

    def _render_system_prompt(self, template: str, tool_descriptions: str) -> str:
        replacements = {
            "{{tools}}": tool_descriptions,
            "{tools}": tool_descriptions,
            "{tool_descriptions}": tool_descriptions,
        }
        result = template
        for placeholder, value in replacements.items():
            result = result.replace(placeholder, value)
        return result.strip()

    def _reset_usage_totals(self) -> None:
        self.usage_totals = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }

    def _register_usage(self, usage: Dict[str, Any]) -> None:
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            if key in usage and usage[key] is not None:
                try:
                    value = int(usage.get(key, 0) or 0)
                except (TypeError, ValueError):
                    continue
                self.usage_totals[key] = self.usage_totals.get(key, 0) + value

    def _recalculate_usage_totals(self) -> None:
        self._reset_usage_totals()
        for message in self.conversation:
            usage = message.get("usage") if isinstance(message, dict) else None
            if isinstance(usage, dict):
                self._register_usage(usage)

    def start(self, initial_message: Optional[str] = None) -> None:
        self._install_signal_handler()
        try:
            self.conversation = [{"role": "system", "content": self.system_prompt}]
            self._reset_usage_totals()
            self._debug_record("system_prompt", {"content": self.system_prompt})
            if initial_message:
                self.conversation.append({"role": "user", "content": initial_message})
                self._debug_record_message("user", initial_message)
                self._agent_turn()
            while True:
                try:
                    if self._sigint_message_pending:
                        print("Interrupt requested. Waiting for current action to complete...")
                        self._sigint_message_pending = False
                    user_label = self._label("you>", self.COLOR_USER)
                    user_input = input(f"{user_label} ")
                except (EOFError, KeyboardInterrupt):
                    print("\nExiting.")
                    return
                if not user_input.strip():
                    continue
                stripped = user_input.strip()
                if stripped.startswith(self.command_registry.prefix):
                    self._debug_record("command", {"command": stripped})
                    outcome = self.command_registry.dispatch(stripped, self)
                    if outcome == CommandOutcome.EXIT:
                        print("Bye.")
                        return
                    continue
                if stripped.lower() in {"exit", "quit"}:
                    print("Bye.")
                    return
                self.conversation.append({"role": "user", "content": user_input})
                self._debug_record_message("user", user_input)
                self._agent_turn()
        finally:
            self._restore_signal_handler()

    def _agent_turn(self) -> None:
        while True:
            if self.slomo_seconds > 0:
                time.sleep(self.slomo_seconds)
            if self._sigint_message_pending:
                print("Interrupt requested. Waiting for current action to complete...")
                self._sigint_message_pending = False
            result = self._stream_response(self.conversation)
            if result is None:
                return
            assistant_reply, usage, streamed_tool_calls = result
            if streamed_tool_calls and not assistant_reply:
                assistant_reply = "\n".join(
                    self._format_tool_invocation(name, args)
                    for name, args in streamed_tool_calls
                )
            if not assistant_reply:
                print("[warning] Model returned an empty response; retry or check logs.")
                self._debug_record("model_empty", {})
                assistant_reply = ""
            assistant_message: Dict[str, Any] = {"role": "assistant", "content": assistant_reply}
            if usage:
                assistant_message["usage"] = usage
                self._register_usage(usage)
            self.conversation.append(assistant_message)
            self._debug_record_message("assistant", assistant_reply)
            if self.cancel_requested:
                if not self._handle_interrupt_prompt():
                    self.conversation.pop()
                    return
            tool_calls = self._parse_tool_calls(assistant_reply)
            if not tool_calls:
                break
            self._debug_record('tool_calls', {'count': len(tool_calls)})
            for tool_name, tool_args in tool_calls:
                print(f"\n[tool call] {tool_name} {tool_args}")
                self._debug_record("tool_call", {"name": tool_name, "args": tool_args})
                allowed, denial_message = self._approve_tool_run(tool_name, tool_args)
                if not allowed:
                    print("[tool skipped] execution denied by user")
                    denial = denial_message or "Tool execution denied by user."
                    wrapped_result = self._format_tool_result(tool_name, denial)
                    self.conversation.append({"role": "user", "content": wrapped_result})
                    self._debug_record("tool_denied", {"name": tool_name})
                    continue
                tool_result = self.tools.execute(tool_name, tool_args)
                self._display_tool_result(tool_name, tool_result)
                self._debug_record("tool_result", {"name": tool_name, "result": tool_result})
                wrapped_result = self._format_tool_result(tool_name, tool_result)
                self.conversation.append({"role": "user", "content": wrapped_result})
                self._debug_record_message("tool_result", wrapped_result)
            continue

    def _stream_response(
        self, conversation: List[Dict[str, Any]]
    ) -> Optional[Tuple[str, Optional[Dict[str, int]], List[Tuple[str, Dict[str, Any]]]]]:
        agent_label = self._label("agent>", self.COLOR_AGENT)
        print(f"{agent_label} ", end="", flush=True)
        chunks: List[str] = []
        buffer = ""
        in_think = False
        usage_info: Optional[Dict[str, int]] = None
        self._debug_record(
            "model_request",
            {
                "model": self.model,
                "options": self.options,
                "messages": [dict(message) for message in conversation],
            },
        )
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
            self._debug_record("model_error", {"error": str(exc)})
            return None
        print()
        getter = getattr(self.client, "get_last_usage", None)
        latest_usage = getter() if callable(getter) else getattr(self.client, "last_usage", None)
        if isinstance(latest_usage, dict):
            usage_info = {}
            for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                if key in latest_usage:
                    try:
                        usage_info[key] = int(latest_usage[key])
                    except (TypeError, ValueError):
                        continue
            if not usage_info:
                usage_info = None
        reply = "".join(chunks).strip()
        payload_getter = getattr(self.client, "get_last_payload", None)
        raw_payload = payload_getter() if callable(payload_getter) else getattr(self.client, "last_payload", None)
        streamed_tool_calls = self._extract_stream_tool_calls(raw_payload)
        self._debug_record(
            "model_response",
            {
                "reply": reply,
                "chunks": chunks,
                "usage": usage_info,
                "raw": raw_payload,
                "tool_calls": streamed_tool_calls,
            },
        )
        if not reply and not streamed_tool_calls:
            print("[error] Model returned empty response; raw payload logged (see debug log).")
            return None
        return reply, usage_info, streamed_tool_calls

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


    def _extract_stream_tool_calls(
        self, payload: Optional[Dict[str, Any]]
    ) -> List[Tuple[str, Dict[str, Any]]]:
        calls: List[Tuple[str, Dict[str, Any]]] = []
        if not isinstance(payload, dict):
            return calls
        choices = payload.get("choices") or []
        for choice in choices:
            delta = choice.get("delta") or {}
            tool_section = delta.get("tool_calls") or choice.get("tool_calls") or []
            for call in tool_section:
                function = call.get("function") or {}
                name = function.get("name")
                arguments = function.get("arguments")
                if not name or arguments is None:
                    continue
                if isinstance(arguments, str):
                    try:
                        parsed_args = json.loads(arguments)
                    except json.JSONDecodeError:
                        parsed_args = {"raw": arguments}
                elif isinstance(arguments, dict):
                    parsed_args = arguments
                else:
                    parsed_args = {"value": arguments}
                calls.append((name, parsed_args))
        return calls

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

    def _display_tool_result(self, tool_name: str, output: str) -> None:
        if tool_name == "run_shell" and output:
            first_line, *rest = output.splitlines()
            print("[tool result]")
            print(first_line)
            if rest:
                print("(output streamed above; remaining lines delivered to the model)")
            print()
            return
        print(f"[tool result]\n{output}\n")

    def _approve_tool_run(self, name: str, args: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        if self.approval_mgr.is_approved(name):
            return True, None
        decision = self._prompt_tool_consent(name, args)
        if decision == "n":
            reason = input(
                "Provide optional reason for the model (press Enter to skip): "
            ).strip()
            message = "Tool execution denied by user."
            if reason:
                message += f" Reason: {reason}"
            return False, message
        if decision == "a":
            self.approval_mgr.approve_always(name)
        return True, None

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
        self._debug_record(
            "session_saved",
            {"path": str(path), "messages": self._conversation_snapshot()},
        )

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
        self._recalculate_usage_totals()
        print(f"Session loaded from {path}. Conversation length: {len(self.conversation)} messages.")
        self._debug_record(
            "session_loaded",
            {"path": str(path), "messages": self._conversation_snapshot()},
        )

    def session_info(self) -> None:
        message_count = len(self.conversation)
        prompt_tokens = self.usage_totals.get("prompt_tokens", 0)
        completion_tokens = self.usage_totals.get("completion_tokens", 0)
        total_tokens = self.usage_totals.get("total_tokens", 0)
        print(f"Provider: {self.provider}")
        print(f"Model: {self.model}")
        print(f"Messages in session: {message_count}")
        if total_tokens:
            print(f"Prompt tokens: {prompt_tokens}")
            print(f"Completion tokens: {completion_tokens}")
            print(f"Total tokens: {total_tokens}")
        else:
            approx_tokens = self.estimate_tokens()
            print(f"Approximate tokens: {approx_tokens}")
        if is_truncation_enabled():
            print(f"Truncation: on (limit: {get_truncation_limit()} chars)")
        else:
            print("Truncation: off")
        print(
            f"Debug: {'on' if self.debug_enabled else 'off'} (log file: {self.debug_log_path})"
        )
        print(f"Unsafe mode: {'on' if self.unsafe_enabled else 'off'}")

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
        self._debug_record("session_removed", {"path": str(path)})

    def show_tail(self, count: int) -> None:
        relevant = self.conversation[-count:]
        if not relevant:
            print("Conversation is empty.")
            return
        for message in relevant:
            role = message.get("role", "unknown").upper()
            content = message.get("content", "")
            print(f"[{role}] {content}")

    def debug_run_tool(self, name: str, args_json: str) -> None:
        if not name:
            print("Usage: /debug_tool <tool_name> <json_args>")
            return
        try:
            parsed_args = json.loads(args_json) if args_json else {}
        except json.JSONDecodeError as exc:
            print(f"Invalid JSON: {exc}. Example: {{\"query\": \"example\"}}")
            return
        if not isinstance(parsed_args, dict):
            print("Tool arguments must be a JSON object.")
            return
        result = self.tools.execute(name, parsed_args)
        print(f"[tool {name}]")
        print(result)
        self._debug_record("debug_tool", {"name": name, "args": parsed_args, "result": result})

    def set_truncation(self, enabled: bool) -> None:
        set_truncation_enabled(enabled)
        state = "enabled" if enabled else "disabled"
        print(f"Tool output truncation {state}.")
        self._debug_record("truncate", {"enabled": enabled})

    def set_debug(self, enabled: bool) -> None:
        previous = self.debug_enabled
        self.debug_enabled = enabled
        state = "enabled" if enabled else "disabled"
        print(f"Debug logging {state}. Log file: {self.debug_log_path}")
        self._debug_record(
            "debug_state",
            {"enabled": enabled, "log_file": str(self.debug_log_path)},
            force=True,
        )
        if enabled and not previous:
            self._debug_dump_conversation()

    def print_debug_status(self) -> None:
        state = "on" if self.debug_enabled else "off"
        print(f"Debug logging is {state}. Log file: {self.debug_log_path}")

    def set_slomo(self, seconds: float) -> None:
        self.slomo_seconds = max(0.0, seconds)
        if self.slomo_seconds:
            print(f"SloMo delay set to {self.slomo_seconds} seconds between model calls.")
        else:
            print("SloMo disabled.")
        self._debug_record("slomo", {"seconds": self.slomo_seconds})

    def show_slomo(self) -> None:
        if self.slomo_seconds:
            print(f"SloMo delay is {self.slomo_seconds} seconds between model calls.")
        else:
            print("SloMo is disabled.")

    def set_unsafe(self, enabled: bool) -> None:
        self.unsafe_enabled = bool(enabled)
        set_unsafe_enabled(self.unsafe_enabled)
        print(f"Unsafe mode {'enabled' if self.unsafe_enabled else 'disabled'}.")
        self._debug_record("unsafe", {"enabled": self.unsafe_enabled})

    def show_unsafe(self) -> None:
        print(f"Unsafe mode is {'on' if self.unsafe_enabled else 'off'}.")

    def _install_signal_handler(self) -> None:
        if self._sigint_registered:
            return
        self._original_sigint = signal.getsignal(signal.SIGINT)
        signal.signal(signal.SIGINT, self._handle_sigint)
        self._sigint_registered = True

    def _restore_signal_handler(self) -> None:
        if not self._sigint_registered:
            return
        if self._original_sigint is not None:
            signal.signal(signal.SIGINT, self._original_sigint)
        self._sigint_registered = False

    def _handle_sigint(self, signum, frame) -> None:
        if self.cancel_requested:
            if self._original_sigint is not None:
                signal.signal(signal.SIGINT, self._original_sigint)
            raise KeyboardInterrupt
        self.cancel_requested = True
        self._sigint_message_pending = True
        print("\nCtrl+C received. Will prompt after the current action.")

    def dump_context(self, target_path: str | None = None) -> None:
        snapshot = self._conversation_snapshot()
        if not target_path:
            print(json.dumps(snapshot, ensure_ascii=False, indent=2))
            return
        path = Path(target_path).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as exc:
            print(f"Failed to write context dump: {exc}")
            return
        print(f"Context dumped to {path}")

    @staticmethod
    def _sanitize_session_name(name: str) -> str:
        sanitized = re.sub(r"[^a-zA-Z0-9_\-]", "_", name.strip())
        return sanitized.strip("_")

    def _debug_record(self, event: str, data: Dict[str, Any], *, force: bool = False) -> None:
        if not (self.debug_enabled or force):
            return
        entry = {
            "event": event,
            "data": data,
        }
        try:
            self.debug_log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.debug_log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, ensure_ascii=False))
                handle.write("\n")
        except OSError as exc:
            print(f"[warning] Failed to write debug log: {exc}")
            self.debug_enabled = False

    def _conversation_snapshot(self) -> List[Dict[str, Any]]:
        snapshot: List[Dict[str, Any]] = []
        for message in self.conversation:
            if isinstance(message, dict):
                snapshot.append(dict(message))
        return snapshot

    def _debug_dump_conversation(self) -> None:
        self._debug_record("conversation_snapshot", {"messages": self._conversation_snapshot()}, force=True)

    def _debug_record_message(self, role: str, content: str) -> None:
        self._debug_record("message", {"role": role, "content": content})

    def _handle_interrupt_prompt(self) -> bool:
        while True:
            choice = input("Interrupt detected. Continue? [c]ontinue/[a]bort: ").strip().lower()
            if choice in {"", "c", "continue", "y", "yes"}:
                self.cancel_requested = False
                return True
            if choice in {"a", "abort", "n", "no"}:
                self.cancel_requested = False
                print("Interrupt acknowledged. Returning to prompt.")
                return False
            print("Please respond with 'c' to continue or 'a' to abort.")
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

    def _parse_tool_calls(self, message: str) -> List[Tuple[str, Dict[str, Any]]]:
        calls: List[Tuple[str, Dict[str, Any]]] = []
        for match in self.TOOL_CALL_PATTERN.finditer(message):
            name = match.group("name")
            raw_body = match.group("body")
            try:
                args = json.loads(raw_body)
            except json.JSONDecodeError as exc:
                args = {"error": f"Invalid JSON arguments: {exc}"}
            calls.append((name, args))
        return calls

    @staticmethod
    def _format_tool_result(name: str, result: str) -> str:
        return f"<tool_result name=\"{name}\">\n{result}\n</tool_result>"

    def _format_tool_invocation(self, name: str, args: Dict[str, Any]) -> str:
        try:
            payload = json.dumps(args, ensure_ascii=False)
        except TypeError:
            payload = str(args)
        return f"<tool name=\"{name}\">\n{payload}\n</tool>"
