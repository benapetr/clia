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

While the program is running:

- Type your prompts after the `you>` prompt.
- Enter `exit` or press `Ctrl+D` to quit.
- When the model decides to use a tool, the CLI displays the call and its result before continuing the chat.

## Tooling

Two tools are registered by default:

| Tool       | Description                                                        | Arguments                               |
|------------|--------------------------------------------------------------------|-----------------------------------------|
| `run_shell` | Execute shell commands inside the project workspace (timeout configurable via `--shell-timeout`). | `{ "command": "<shell command string>" }` |
| `read_url` | Fetch webpage text with HTML stripped, capped at 4,000 characters. | `{ "url": "https://example.com" }`        |

You can add more tools by extending `build_tools()` in `agent_cli.py`.

## Development

Check that the script compiles:

```bash
python3 -m compileall agent_cli.py
```

Consider adding automated tests or linting as the project grows.
