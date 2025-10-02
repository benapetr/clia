# Ollama Agent CLI

An interactive command-line interface that lets a local Ollama model act as a tool-using agent. The assistant can stream responses in real time and invoke registered tools—such as running shell commands or fetching webpage text—to complete tasks autonomously.

## Requirements

- Python 3.9+
- `requests` Python package
- Local Ollama server running on `http://localhost:11434`

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install requests
```

## Usage

Start the agent with the default model (`llama3`):

```bash
python3 agent_cli.py
```

You can provide an initial message and override model settings:

```bash
python3 agent_cli.py "help me summarize this repo" --model llama3.1 --temperature 0.2
```

Use `--shell-timeout` to adjust how long the `run_shell` tool may run (in seconds):

```bash
python3 agent_cli.py --shell-timeout 120
```

Use `--ollama-timeout` to set the request timeout for streaming responses from Ollama:

```bash
python3 agent_cli.py --ollama-timeout 300
```

Disable colored prompts if your terminal does not support ANSI escape codes:

```bash
python3 agent_cli.py --no-color
```

Override the configuration directory (default is `~/.config/clia`):

```bash
python3 agent_cli.py --config-dir ./tmp/config
```

While the program is running:

- Type your prompts after the `you>` prompt (shown in yellow when the terminal supports color, or plain if `--no-color` is used).
- Enter `exit` or press `Ctrl+D` to quit.
- When the model decides to use a tool, the CLI displays the call and its result before continuing the chat; agent output is prefixed with a cyan `agent>` label (plain when `--no-color` is active).
- For models that emit `<think>...</think>` meta tags, the content inside the tags is rendered in light gray to distinguish reasoning from the final answer (colorized output only).

## Tool Approval Workflow

- On startup, the agent reads a list of auto-approved tools from `allowed_tools` inside the configuration directory (default `~/.config/clia/allowed_tools`).
- When the model requests a tool that is not on the approved list, the CLI prompts you to allow it once (`y`), deny it (`n`), or always allow it (`a`).
- Choosing `a` adds the tool to the in-memory allowlist and appends it to `allowed_tools`, creating the file if necessary.

## Tooling

Two tools are registered by default:

| Tool       | Description                                                        | Arguments                               |
|------------|--------------------------------------------------------------------|-----------------------------------------|
| `run_shell` | Execute shell commands inside the project workspace (timeout configurable via `--shell-timeout`). | `{ "command": "<shell command string>" }` |
| `read_url` | Fetch webpage text with HTML stripped, capped at 4,000 characters. | `{ "url": "https://example.com" }`        |
| `search_internet` | Query DuckDuckGo for quick search snippets.                         | `{ "query": "open source llm agents" }`    |

You can add more tools by extending `build_tools()` in `agent_cli.py`.

## Development

Check that the script compiles:

```bash
python3 -m compileall agent_cli.py
```

Consider adding automated tests or linting as the project grows.
