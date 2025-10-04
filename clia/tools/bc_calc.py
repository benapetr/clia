from __future__ import annotations

import subprocess
from typing import Any, Dict

from clia.tooling import Tool
from clia.utils import truncate


def create_tool() -> Tool:
    def run(args: Dict[str, Any]) -> str:
        expression = args.get("expression")
        if not expression:
            return "ERROR: 'expression' argument is required"
        try:
            completed = subprocess.run(
                ["bc", "-l"],
                input=expression,
                text=True,
                capture_output=True,
                timeout=5,
            )
        except FileNotFoundError:
            return "ERROR: 'bc' is not installed on this system"
        except subprocess.TimeoutExpired:
            return "ERROR: calculation timed out"
        output = completed.stdout.strip()
        error = completed.stderr.strip()
        if completed.returncode != 0:
            return f"ERROR: bc exited with code {completed.returncode}: {error or output}"
        result = output if output else "0"
        if error:
            result += "\n[stderr]\n" + error
        return truncate(result)

    return Tool(
        name="bc",
        description="Evaluate math expressions using the system 'bc' calculator (with -l precision).",
        schema='{"expression": "(2 + 2) * 3"}',
        handler=run,
    )
