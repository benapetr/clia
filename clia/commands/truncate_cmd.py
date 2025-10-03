from __future__ import annotations

from clia.commands import Command, CommandOutcome, CommandRegistry

if False:  # pragma: no cover - type checking aid
    from clia.cli import AgentCLI


class TruncateCommand(Command):
    name = "truncate"
    description = "Enable or disable tool output truncation"
    usage = "/truncate on|off"

    def execute(self, agent: "AgentCLI", argument: str) -> CommandOutcome:
        arg = argument.strip().lower()
        if arg == "on":
            agent.set_truncation(True)
        elif arg == "off":
            agent.set_truncation(False)
        else:
            print(f"Usage: {self.usage}")
        return CommandOutcome.CONTINUE


def register(registry: CommandRegistry) -> None:
    registry.register(TruncateCommand())
