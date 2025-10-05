from __future__ import annotations

from clia.commands import Command, CommandOutcome, CommandRegistry

if False:  # pragma: no cover - type checking aid
    from clia.cli import AgentCLI


class SloMoCommand(Command):
    name = "slomo"
    description = "Set or display delay between model calls"
    usage = "/slomo [seconds]"

    def execute(self, agent: "AgentCLI", argument: str) -> CommandOutcome:
        arg = argument.strip()
        if not arg:
            agent.show_slomo()
            return CommandOutcome.CONTINUE
        try:
            seconds = float(arg)
            if seconds < 0:
                raise ValueError
        except ValueError:
            print(f"Usage: {self.usage}")
            return CommandOutcome.CONTINUE
        agent.set_slomo(seconds)
        return CommandOutcome.CONTINUE


def register(registry: CommandRegistry) -> None:
    registry.register(SloMoCommand())
