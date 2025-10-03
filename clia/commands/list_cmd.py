from __future__ import annotations

from clia.commands import Command, CommandOutcome, CommandRegistry

if False:  # pragma: no cover - type checking aid
    from clia.cli import AgentCLI


class ListCommand(Command):
    name = "ls"
    description = "List saved sessions"
    usage = "/ls"

    def execute(self, agent: "AgentCLI", argument: str) -> CommandOutcome:
        agent.list_sessions()
        return CommandOutcome.CONTINUE


def register(registry: CommandRegistry) -> None:
    registry.register(ListCommand())
