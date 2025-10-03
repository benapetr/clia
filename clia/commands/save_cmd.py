from __future__ import annotations

from clia.commands import Command, CommandOutcome, CommandRegistry

if False:  # pragma: no cover - type checking aid
    from clia.cli import AgentCLI


class SaveCommand(Command):
    name = "save"
    description = "Save the current session"
    usage = "/save <name>"

    def execute(self, agent: "AgentCLI", argument: str) -> CommandOutcome:
        if not argument:
            print(f"Usage: {self.usage}")
            return CommandOutcome.CONTINUE
        agent.save_session(argument)
        return CommandOutcome.CONTINUE


def register(registry: CommandRegistry) -> None:
    registry.register(SaveCommand())
