from __future__ import annotations

from clia.tooling import ToolRegistry
from clia.tools.read_url import create_tool as create_read_url_tool
from clia.tools.run_shell import create_tool as create_shell_tool
from clia.tools.search_internet import create_tool as create_search_internet_tool


def build_tools(shell_timeout: int = 60) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(create_shell_tool(shell_timeout=shell_timeout))
    registry.register(create_read_url_tool())
    registry.register(create_search_internet_tool())
    return registry
