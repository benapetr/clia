from __future__ import annotations

import subprocess
from typing import Any, Dict

from clia.tooling import Tool
from clia.utils import truncate


def create_tool(shell_timeout: int = 60) -> Tool:
    def run(args: Dict[str, Any]) -> str:
        command = args.get("command")
        if not command:
            return "ERROR: 'command' argument is required"
        try:
            completed = subprocess.run(
                command,
                shell=True,
                check=False,
                capture_output=True,
                text=True,
                timeout=shell_timeout,
            )
        except subprocess.TimeoutExpired:
            return "ERROR: command timed out"
        output = completed.stdout if completed.stdout else ""
        error = completed.stderr if completed.stderr else ""
        status = f"exit code {completed.returncode}"
        if error:
            output = f"{output}\n[stderr]\n{error}" if output else f"[stderr]\n{error}"
        return truncate(f"{status}\n{output}".strip())

    return Tool(
        name="run_shell",
        description=f"Execute a shell command inside the current workspace (timeout {shell_timeout}s).",
        schema='{"command": "<shell command string>"}',
        handler=run,
    )
