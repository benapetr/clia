from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from clia.tooling import Tool
from clia.utils import truncate

WORKSPACE_ROOT = Path.cwd().resolve()


def create_tool() -> Tool:
    def run(args: Dict[str, Any]) -> str:
        raw_path = args.get("path")
        if not raw_path:
            return "ERROR: 'path' argument is required"
        target = _resolve_path(raw_path)
        if target is None:
            return "ERROR: path escapes the workspace"
        if not target.exists():
            return "ERROR: file not found"
        if target.is_dir():
            return "ERROR: path points to a directory"

        start_line = args.get("start_line")
        max_lines = args.get("max_lines")
        try:
            start_idx = max(1, int(start_line)) if start_line is not None else 1
        except (TypeError, ValueError):
            return "ERROR: 'start_line' must be an integer"
        try:
            max_count: Optional[int] = int(max_lines) if max_lines is not None else None
            if max_count is not None and max_count <= 0:
                return "ERROR: 'max_lines' must be positive"
        except (TypeError, ValueError):
            return "ERROR: 'max_lines' must be an integer"

        try:
            if start_idx == 1 and max_count is None:
                content = target.read_text(encoding="utf-8")
                return truncate(content)
            lines = target.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            return f"ERROR: failed to read file: {exc}"
        start_zero = max(0, start_idx - 1)
        end_idx = start_zero + max_count if max_count is not None else len(lines)
        selected = lines[start_zero:end_idx]
        header = f"{target} (lines {start_idx}-{start_idx + len(selected) - 1 if selected else start_idx - 1})"
        body = "\n".join(selected)
        output = header if not body else header + "\n" + body
        return truncate(output)

    return Tool(
        name="file_read",
        description="Read files entirely or a specific range of lines.",
        schema='{"path": "README.md", "start_line": 1, "max_lines": 20}',
        handler=run,
    )


def _resolve_path(raw_path: str) -> Optional[Path]:
    try:
        candidate = Path(raw_path).expanduser()
    except Exception:
        return None
    if not candidate.is_absolute():
        candidate = WORKSPACE_ROOT / candidate
    try:
        resolved = candidate.resolve()
    except OSError:
        return None
    try:
        resolved.relative_to(WORKSPACE_ROOT)
    except ValueError:
        return None
    return resolved
