from __future__ import annotations

from clia.commands import Command, CommandOutcome, CommandRegistry

if False:  # pragma: no cover - type checking aid
    from clia.cli import AgentCLI


class HelpCommand(Command):
    name = "help"
    description = "Show available commands"
    usage = "/help"

    def __init__(self, registry: CommandRegistry) -> None:
        self._registry = registry

    def execute(self, agent: "AgentCLI", argument: str) -> CommandOutcome:
        print("Available commands:")
        for cmd in self._registry.list_commands():
            print(f"  {cmd.usage:<12} {cmd.description}")
        return CommandOutcome.CONTINUE


def register(registry: CommandRegistry) -> None:
    registry.register(HelpCommand(registry))
