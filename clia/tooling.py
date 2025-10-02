from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional


@dataclass
class Tool:
    name: str
    description: str
    schema: str
    handler: Callable[[Dict[str, Any]], str]

    def run(self, args: Dict[str, Any]) -> str:
        return self.handler(args)


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' already registered")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def describe_for_prompt(self) -> str:
        lines = []
        for tool in self._tools.values():
            lines.append(f"- {tool.name}: {tool.description}\n  args schema: {tool.schema}")
        return "\n".join(lines)

    def execute(self, name: str, args: Dict[str, Any]) -> str:
        tool = self.get(name)
        if not tool:
            return f"ERROR: unknown tool '{name}'"
        try:
            return tool.run(args)
        except Exception as exc:  # pragma: no cover - defensive
            return f"ERROR while running '{name}': {exc}"
