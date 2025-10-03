#!/usr/bin/env python3
"""Interactive CLI agent that supports Ollama, OpenAI, and Mistral backends."""

from __future__ import annotations

import argparse
from configparser import ConfigParser
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from clia.approval import ToolApprovalManager
from clia.cli import AgentCLI
from clia.clients import create_client
from clia.tools import build_tools
from clia.tools.search_internet import SearchConfig

DEFAULT_ENDPOINTS: Dict[str, str] = {
    "ollama": "http://localhost:11434",
    "openai": "https://api.openai.com/v1",
    "mistral": "https://api.mistral.ai/v1",
}
DEFAULT_MODEL = "qwen3:14b"
DEFAULT_TEMPERATURE = 0.7
DEFAULT_TIMEOUT = 120


@dataclass
class ClientSettings:
    provider: str
    model: str
    endpoint: str
    api_key: Optional[str]
    temperature: float
    timeout: int

def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Agentic CLI that can call Ollama, OpenAI, or Mistral.")
    parser.add_argument("prompt", nargs="*", help="Optional initial message to send to the agent.")
    parser.add_argument("--provider", choices=["ollama", "openai", "mistral"], help="Backend provider to use.")
    parser.add_argument("--model", help="Model name to use with the selected provider.")
    parser.add_argument("--base-url", dest="endpoint", help="Endpoint URL for the provider (default depends on provider).")
    parser.add_argument("--endpoint", dest="endpoint", help="Alias for --base-url.")
    parser.add_argument("--api-key", help="API key for OpenAI or Mistral providers.")
    parser.add_argument("--temperature", type=float, help="Sampling temperature passed to the model.")
    parser.add_argument(
        "--shell-timeout",
        type=int,
        default=60,
        help="Timeout in seconds for the run_shell tool (default: 60).",
    )
    parser.add_argument(
        "--request-timeout",
        type=int,
        help="Request timeout in seconds for model responses.",
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
    config_dir = Path(args.config_dir).expanduser() if args.config_dir else Path.home() / ".config" / "clia"
    config = ConfigParser()
    config_path = config_dir / "config.ini"
    config.read(config_path)
    save_dir = resolve_save_dir(config_dir, config)
    search_config = resolve_search_config(config)
    tools = build_tools(shell_timeout=args.shell_timeout, search_config=search_config)
    approval_mgr = ToolApprovalManager(config_dir)
    system_prompt_template = load_system_prompt_template(config_dir, config)
    settings = resolve_client_settings(args, config)
    client = create_client(
        provider=settings.provider,
        endpoint=settings.endpoint,
        api_key=settings.api_key,
        timeout=settings.timeout,
    )
    agent = AgentCLI(
        model=settings.model,
        provider=settings.provider,
        client=client,
        tools=tools,
        approval_mgr=approval_mgr,
        options={"temperature": settings.temperature},
        use_color=False if args.no_color else None,
        session_dir=save_dir,
        system_prompt_template=system_prompt_template,
    )
    initial_message = " ".join(args.prompt).strip() if args.prompt else None
    agent.start(initial_message if initial_message else None)
    return 0


def resolve_client_settings(args: argparse.Namespace, config: ConfigParser) -> ClientSettings:
    section = config["model"] if config.has_section("model") else None

    provider = (args.provider or (section.get("provider") if section else None) or "ollama").lower()
    if provider not in {"ollama", "openai", "mistral"}:
        raise ValueError(f"Unsupported provider '{provider}' in configuration")

    def _get_value(key: str, fallback: Optional[str] = None) -> Optional[str]:
        if section and key in section:
            return section.get(key)
        return fallback

    def _get_float(key: str, fallback: float) -> float:
        raw = _get_value(key)
        if raw is None:
            return fallback
        try:
            return float(raw)
        except ValueError:
            print(f"[warning] Invalid float for '{key}' in config.ini; using default {fallback}")
            return fallback

    def _get_int(key: str, fallback: int) -> int:
        raw = _get_value(key)
        if raw is None:
            return fallback
        try:
            return int(raw)
        except ValueError:
            print(f"[warning] Invalid integer for '{key}' in config.ini; using default {fallback}")
            return fallback

    model_name = args.model or _get_value("model") or _get_value("name") or DEFAULT_MODEL
    endpoint = args.endpoint or _get_value("endpoint") or _get_value("base_url") or DEFAULT_ENDPOINTS[provider]
    api_key = args.api_key or _get_value("api_key") or _get_value("token")
    temperature = args.temperature if args.temperature is not None else _get_float("temperature", DEFAULT_TEMPERATURE)
    timeout = args.request_timeout if args.request_timeout is not None else _get_int("timeout", DEFAULT_TIMEOUT)

    return ClientSettings(
        provider=provider,
        model=model_name,
        endpoint=endpoint,
        api_key=api_key,
        temperature=temperature,
        timeout=timeout,
    )


def resolve_search_config(config: ConfigParser) -> SearchConfig:
    section = config["search"] if config.has_section("search") else None
    provider = (section.get("provider") if section else None) or "duckduckgo"
    provider = provider.lower()
    if provider not in {"duckduckgo", "google"}:
        print(f"[warning] Unsupported search provider '{provider}' in config.ini; falling back to DuckDuckGo")
        provider = "duckduckgo"
    google_api_key = section.get("api_key") if section else None
    google_engine_id = (
        section.get("engine_id") if section else None
    ) or (section.get("cx") if section else None)
    return SearchConfig(
        provider=provider,
        google_api_key=google_api_key,
        google_engine_id=google_engine_id,
    )


def resolve_save_dir(config_dir: Path, config: ConfigParser) -> Path:
    section = config["storage"] if config.has_section("storage") else None
    configured = section.get("sessions_dir") if section and "sessions_dir" in section else None
    if configured:
        path = Path(configured).expanduser()
        return path
    return config_dir / "sessions"


def load_system_prompt_template(config_dir: Path, config: ConfigParser) -> Optional[str]:
    section: Optional[ConfigParser] = None
    if config.has_section("model") and "system_prompt" in config["model"]:
        section = config["model"]
    elif config.has_section("prompts") and "system_prompt" in config["prompts"]:
        section = config["prompts"]
    if not section:
        return None
    value = section.get("system_prompt", "").strip()
    if not value:
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = config_dir / path
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"[warning] Failed to read system prompt template '{path}': {exc}")
        return None


if __name__ == "__main__":
    sys.exit(main())
