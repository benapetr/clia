from __future__ import annotations

import json

from clia.commands import Command, CommandOutcome, CommandRegistry

if False:  # pragma: no cover - type checking aid
    from clia.cli import AgentCLI


class DebugToolCommand(Command):
    name = "debug_tool"
    description = "Run a tool manually with JSON arguments"
    usage = "/debug_tool <tool_name> <json_args>"

    def execute(self, agent: "AgentCLI", argument: str) -> CommandOutcome:
        stripped = argument.strip()
        if not stripped:
            print(f"Usage: {self.usage}")
            return CommandOutcome.CONTINUE
        parts = stripped.split(maxsplit=1)
        tool_name = parts[0]
        json_args = parts[1] if len(parts) > 1 else "{}"
        agent.debug_run_tool(tool_name, json_args)
        return CommandOutcome.CONTINUE


def register(registry: CommandRegistry) -> None:
    registry.register(DebugToolCommand())
