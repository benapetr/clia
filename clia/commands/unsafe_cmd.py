from __future__ import annotations

from clia.commands import Command, CommandOutcome, CommandRegistry

if False:  # pragma: no cover - type checking aid
    from clia.cli import AgentCLI


class UnsafeCommand(Command):
    name = "unsafe"
    description = "Enable or disable workspace safety checks"
    usage = "/unsafe [on|off]"

    def execute(self, agent: "AgentCLI", argument: str) -> CommandOutcome:
        arg = argument.strip().lower()
        if not arg:
            agent.show_unsafe()
            return CommandOutcome.CONTINUE
        if arg in {"on", "true", "1"}:
            agent.set_unsafe(True)
        elif arg in {"off", "false", "0"}:
            agent.set_unsafe(False)
        else:
            print(f"Usage: {self.usage}")
        return CommandOutcome.CONTINUE


def register(registry: CommandRegistry) -> None:
    registry.register(UnsafeCommand())
