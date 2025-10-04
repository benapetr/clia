from __future__ import annotations

from enum import Enum, auto
from typing import Dict, Iterable, List, Optional, Protocol, TYPE_CHECKING

COMMAND_PREFIX = "/"

if TYPE_CHECKING:  # pragma: no cover - for type hints only
    from clia.cli import AgentCLI


class CommandOutcome(Enum):
    CONTINUE = auto()
    EXIT = auto()


class Command(Protocol):
    name: str
    description: str
    usage: str

    def execute(self, agent: "AgentCLI", argument: str) -> CommandOutcome:
        ...


class CommandRegistry:
    def __init__(self, prefix: str = COMMAND_PREFIX) -> None:
        self.prefix = prefix
        self._commands: Dict[str, Command] = {}

    def register(self, command: Command) -> None:
        key = command.name.lower()
        if key in self._commands:
            raise ValueError(f"Command '{command.name}' already registered")
        self._commands[key] = command

    def dispatch(self, raw: str, agent: "AgentCLI") -> CommandOutcome:
        if not raw.startswith(self.prefix):
            return CommandOutcome.CONTINUE
        stripped = raw[len(self.prefix) :]
        if not stripped:
            print("Unknown command - see /help")
            return CommandOutcome.CONTINUE
        parts = stripped.split(maxsplit=1)
        name = parts[0].lower()
        argument = parts[1].strip() if len(parts) > 1 else ""
        command = self._commands.get(name)
        if not command:
            print("Unknown command - see /help")
            return CommandOutcome.CONTINUE
        try:
            return command.execute(agent, argument)
        except Exception as exc:  # pragma: no cover - defensive
            print(f"Command '{command.name}' failed: {exc}")
            return CommandOutcome.CONTINUE

    def list_commands(self) -> List[Command]:
        return sorted(self._commands.values(), key=lambda cmd: cmd.name)


def build_default_registry(prefix: str = COMMAND_PREFIX) -> CommandRegistry:
    registry = CommandRegistry(prefix)
    from clia.commands import (
        exit_cmd,
        help_cmd,
        info_cmd,
        list_cmd,
        load_cmd,
        remove_cmd,
        save_cmd,
        tail_cmd,
        debug_cmd,
        debug_tool_cmd,
        truncate_cmd,
    )

    exit_cmd.register(registry)
    help_cmd.register(registry)
    info_cmd.register(registry)
    list_cmd.register(registry)
    load_cmd.register(registry)
    remove_cmd.register(registry)
    save_cmd.register(registry)
    tail_cmd.register(registry)
    debug_cmd.register(registry)
    debug_tool_cmd.register(registry)
    truncate_cmd.register(registry)
    return registry
