from __future__ import annotations

from typing import Optional

from clia.tooling import ToolRegistry
from clia.tools.read_url import create_tool as create_read_url_tool
from clia.tools.run_shell import create_tool as create_shell_tool
from clia.tools.search_internet import (
    SearchConfig,
    create_tool as create_search_internet_tool,
)
from clia.tools.bc_calc import create_tool as create_bc_tool


def build_tools(shell_timeout: int = 60, search_config: Optional[SearchConfig] = None) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(create_shell_tool(shell_timeout=shell_timeout))
    registry.register(create_read_url_tool())
    registry.register(create_search_internet_tool(search_config=search_config))
    registry.register(create_bc_tool())
    return registry
