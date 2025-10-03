from __future__ import annotations

from clia.commands import Command, CommandOutcome, CommandRegistry

if False:  # pragma: no cover - type checking aid
    from clia.cli import AgentCLI


class InfoCommand(Command):
    name = "info"
    description = "Display model and session statistics"
    usage = "/info"

    def execute(self, agent: "AgentCLI", argument: str) -> CommandOutcome:
        agent.session_info()
        return CommandOutcome.CONTINUE


def register(registry: CommandRegistry) -> None:
    registry.register(InfoCommand())
