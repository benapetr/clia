from __future__ import annotations

from clia.commands import Command, CommandOutcome, CommandRegistry

if False:  # pragma: no cover - type checking aid
    from clia.cli import AgentCLI


class TailCommand(Command):
    name = "tail"
    description = "Show the last N conversation messages"
    usage = "/tail [N]"

    def execute(self, agent: "AgentCLI", argument: str) -> CommandOutcome:
        count = 5
        if argument:
            try:
                count = max(1, int(argument.strip()))
            except ValueError:
                print("Usage: /tail [N]")
                return CommandOutcome.CONTINUE
        agent.show_tail(count)
        return CommandOutcome.CONTINUE


def register(registry: CommandRegistry) -> None:
    registry.register(TailCommand())
