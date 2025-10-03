# Ollama Agent CLI

An interactive command-line interface that lets an LLM act as a tool-using agent. The assistant can stream responses in real time and invoke registered tools—such as running shell commands or fetching webpage text—to complete tasks autonomously. By default the CLI targets a local Ollama instance, but it can also connect to OpenAI or Mistral endpoints.

## Requirements

- Python 3.9+
- `requests` Python package
- `ddgs` Python package (required for DuckDuckGo search; optional if using Google only)
- One of:
  - Local Ollama server running on `http://localhost:11434` (default)
  - OpenAI API access with a valid key
  - Mistral API access with a valid key

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install requests ddgs
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

Use `--request-timeout` to set the request timeout for streaming responses:

```bash
python3 agent_cli.py --request-timeout 300
```

Disable colored prompts if your terminal does not support ANSI escape codes:

```bash
python3 agent_cli.py --no-color
```

Override the configuration directory (default is `~/.config/clia`):

```bash
python3 agent_cli.py --config-dir ./tmp/config
```

Switch providers from the command line:

```bash
python3 agent_cli.py --provider openai --model gpt-4o-mini --api-key "$OPENAI_API_KEY"
```

## Configuration

When present, `~/.config/clia/config.ini` (override with `--config-dir`) supplies defaults:

```ini
[model]
provider = ollama           # or openai / mistral
model = llama3
endpoint = http://localhost:11434
api_key =                   # required for openai/mistral
temperature = 0.7
timeout = 120

[search]
provider = duckduckgo       # or google
api_key =                   # required when provider = google
engine_id =                 # Google Programmable Search Engine ID (cx)

[storage]
sessions_dir = ~/.config/clia/sessions
```

CLI flags always take precedence over values loaded from `config.ini`. The endpoint should be the base URL for the provider (e.g., `https://api.openai.com/v1`).

When `search.provider = google`, populate both `api_key` and `engine_id` with credentials for a Google Programmable Search Engine (Custom Search JSON API). DuckDuckGo requires no additional configuration.
Set `storage.sessions_dir` to change where session files are stored; paths are expanded with `~` and may be absolute.
DuckDuckGo searches depend on the optional `ddgs` package; install it alongside `requests` when using the default provider.

## Project Structure

```
agent_cli.py        # CLI entrypoint and argument parsing
clia/
  cli.py            # Conversation loop, streaming, and tool orchestration
  clients.py        # HTTP clients for Ollama, OpenAI, and Mistral
  commands/         # Slash-command framework and default command handlers
  ollama.py         # Compatibility shim re-exporting the Ollama client
  approval.py       # Tool approval persistence and prompts
  tooling.py        # Tool dataclass and registry implementation
  utils.py          # Shared helpers (HTML stripping, truncation)
  tools/
    run_shell.py    # Shell command execution tool
    read_url.py     # URL fetch/strip tool
    search_internet.py  # Configurable internet search tool
```

While the program is running:

- Type your prompts after the `you>` prompt (shown in yellow when the terminal supports color, or plain if `--no-color` is used).
- Enter `exit` or press `Ctrl+D` to quit.
- When the model decides to use a tool, the CLI displays the call and its result before continuing the chat; agent output is prefixed with a cyan `agent>` label (plain when `--no-color` is active).
- For models that emit `<think>...</think>` meta tags, the content inside the tags is rendered in light gray to distinguish reasoning from the final answer (colorized output only).
- System commands start with `/` and are handled locally:
  - `/help` – list available commands
  - `/info` – show provider/model and an approximate session token count
  - `/save <name|path>` – save the current dialogue to the configured sessions directory or a specific path
  - `/load <name|path>` – restore a saved dialogue from the configured directory or an explicit path
  - `/ls` – list saved session files in the configured directory
  - `/rm <name|path>` – delete a saved session file
  - `/tail [N]` – print the last `N` conversation messages (default 5)
  - `/truncate on|off` – enable or disable tool output truncation globally
  - `/exit` – exit immediately

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
| `search_internet` | Query the configured search provider (DuckDuckGo or Google PSE).    | `{ "query": "open source llm agents" }`    |

You can add more tools by extending `clia/tools/__init__.py`.

## Development

Check that the script compiles:

```bash
python3 -m compileall agent_cli.py
```

Consider adding automated tests or linting as the project grows.
