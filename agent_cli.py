#!/usr/bin/env python3
"""Interactive CLI agent powered by a local Ollama model."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from clia.approval import ToolApprovalManager
from clia.cli import AgentCLI
from clia.ollama import OllamaClient
from clia.tools import build_tools


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Agentic CLI powered by a local Ollama model.")
    parser.add_argument("prompt", nargs="*", help="Optional initial message to send to the agent.")
    parser.add_argument("--model", default="llama3", help="Ollama model name (default: llama3).")
    parser.add_argument("--base-url", default="http://localhost:11434", help="Base URL for Ollama (default: http://localhost:11434).")
    parser.add_argument("--temperature", type=float, default=0.7, help="Sampling temperature passed to Ollama.")
    parser.add_argument(
        "--shell-timeout",
        type=int,
        default=60,
        help="Timeout in seconds for the run_shell tool (default: 60).",
    )
    parser.add_argument(
        "--ollama-timeout",
        type=int,
        default=120,
        help="Request timeout in seconds for Ollama responses (default: 120).",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable ANSI colors in CLI prompts (auto-detected by default).",
    )
    parser.add_argument(
        "--config-dir",
        help="Directory used to persist agent configuration (default: ~/.config/clia).",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    tools = build_tools(shell_timeout=args.shell_timeout)
    config_dir = Path(args.config_dir).expanduser() if args.config_dir else Path.home() / ".config" / "clia"
    approval_mgr = ToolApprovalManager(config_dir)
    client = OllamaClient(args.base_url, timeout=args.ollama_timeout)
    agent = AgentCLI(
        model=args.model,
        client=client,
        tools=tools,
        approval_mgr=approval_mgr,
        options={"temperature": args.temperature},
        use_color=False if args.no_color else None,
    )
    initial_message = " ".join(args.prompt).strip() if args.prompt else None
    agent.start(initial_message if initial_message else None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
