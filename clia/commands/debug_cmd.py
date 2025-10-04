from __future__ import annotations

from clia.commands import Command, CommandOutcome, CommandRegistry

if False:  # pragma: no cover - type checking aid
    from clia.cli import AgentCLI


class DebugCommand(Command):
    name = "debug"
    description = "Toggle or display debug logging"
    usage = "/debug [on|off]"

    def execute(self, agent: "AgentCLI", argument: str) -> CommandOutcome:
        arg = argument.strip().lower()
        if not arg:
            agent.print_debug_status()
        elif arg == "on":
            agent.set_debug(True)
        elif arg == "off":
            agent.set_debug(False)
        else:
            print(f"Usage: {self.usage}")
        return CommandOutcome.CONTINUE


def register(registry: CommandRegistry) -> None:
    registry.register(DebugCommand())
