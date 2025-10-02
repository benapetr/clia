from __future__ import annotations

from pathlib import Path
from typing import Set


class ToolApprovalManager:
    def __init__(self, config_dir: Path) -> None:
        self.config_dir = config_dir
        self.allowed_file = self.config_dir / "allowed_tools"
        self.approved: Set[str] = set()
        self._load()

    def _load(self) -> None:
        try:
            with self.allowed_file.open("r", encoding="utf-8") as handle:
                for line in handle:
                    name = line.strip()
                    if name:
                        self.approved.add(name)
        except FileNotFoundError:
            return
        except OSError as exc:
            print(f"[warning] Failed to read allowed tools file: {exc}")

    def is_approved(self, name: str) -> bool:
        return name in self.approved

    def approve_always(self, name: str) -> None:
        if name in self.approved:
            return
        self.approved.add(name)
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            with self.allowed_file.open("a", encoding="utf-8") as handle:
                handle.write(f"{name}\n")
        except OSError as exc:
            print(f"[warning] Failed to persist tool approval: {exc}")
