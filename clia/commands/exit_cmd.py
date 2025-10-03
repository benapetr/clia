from __future__ import annotations

from clia.commands import Command, CommandOutcome, CommandRegistry

if False:  # pragma: no cover - type checking aid
    from clia.cli import AgentCLI


class ExitCommand(Command):
    name = "exit"
    description = "Exit the program"
    usage = "/exit"

    def execute(self, agent: "AgentCLI", argument: str) -> CommandOutcome:
        return CommandOutcome.EXIT


def register(registry: CommandRegistry) -> None:
    registry.register(ExitCommand())
