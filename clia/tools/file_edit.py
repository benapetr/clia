from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

from clia.tooling import Tool
from clia.utils import truncate, is_unsafe_enabled

WORKSPACE_ROOT = Path.cwd().resolve()


def create_tool() -> Tool:
    def run(args: Dict[str, Any]) -> str:
        raw_path = args.get("path")
        mode = (args.get("mode") or "").lower()
        content = args.get("content")
        if not raw_path:
            return "ERROR: 'path' argument is required"
        if mode not in {"write", "append", "insert"}:
            return "ERROR: 'mode' must be one of: write, append, insert"
        if content is None:
            return "ERROR: 'content' argument is required"

        target = _resolve_path(raw_path)
        if target is None:
            return "ERROR: path escapes the workspace"

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return f"ERROR: failed to create parent directories: {exc}"

        try:
            if mode == "write":
                target.write_text(content, encoding="utf-8")
                return truncate(f"Wrote {len(content)} characters to {target}")
            if mode == "append":
                with target.open("a", encoding="utf-8") as handle:
                    handle.write(content)
                return truncate(f"Appended {len(content)} characters to {target}")
            # insert mode
            line = args.get("line")
            if line is None:
                return "ERROR: 'line' argument is required for insert mode"
            try:
                line_idx = int(line)
                if line_idx < 1:
                    raise ValueError
            except (TypeError, ValueError):
                return "ERROR: 'line' must be a positive integer"

            if target.exists():
                existing = target.read_text(encoding="utf-8").splitlines(keepends=True)
            else:
                existing = []
            insert_at = min(line_idx - 1, len(existing))
            insertion = content.splitlines(keepends=True)
            if not insertion:
                insertion = ["\n"]
            elif not content.endswith("\n"):
                insertion[-1] = insertion[-1] + "\n"
            new_lines = existing[:insert_at] + insertion + existing[insert_at:]
            target.write_text("".join(new_lines), encoding="utf-8")
            return truncate(f"Inserted {len(content)} characters at line {line_idx} in {target}")
        except OSError as exc:
            return f"ERROR: file operation failed: {exc}"

    return Tool(
        name="file_edit",
        description="Modify files by writing, appending, or inserting text.",
        schema='{"path": "docs/example.txt", "mode": "insert", "line": 1, "content": "Hello"}',
        handler=run,
    )


def _resolve_path(raw_path: str) -> Path | None:
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
    if is_unsafe_enabled():
        return resolved
    try:
        resolved.relative_to(WORKSPACE_ROOT)
    except ValueError:
        return None
    return resolved
