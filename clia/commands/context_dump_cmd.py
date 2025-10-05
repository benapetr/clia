from __future__ import annotations

from clia.commands import Command, CommandOutcome, CommandRegistry

if False:  # pragma: no cover - type checking aid
    from clia.cli import AgentCLI


class ContextDumpCommand(Command):
    name = "context_dump"
    description = "Export the current conversation context to stdout or a file"
    usage = "/context_dump [path]"

    def execute(self, agent: "AgentCLI", argument: str) -> CommandOutcome:
        target = argument.strip() or None
        agent.dump_context(target)
        return CommandOutcome.CONTINUE


def register(registry: CommandRegistry) -> None:
    registry.register(ContextDumpCommand())
