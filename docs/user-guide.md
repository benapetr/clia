# CLI Agent User Guide

This guide explains how to install, configure, and run the CLI agent that turns local or hosted language models into tool-using assistants. The agent streams model output in real time, executes registered tools (shell commands, URL fetching, internet search), and offers local slash-commands for session management.

## 1. Prerequisites

- **Python** 3.9 or newer
- The following Python packages (install them into your virtual environment):
  ```bash
  pip install requests beautifulsoup4 ddgs
  ```
  `requests` handles HTTP calls, `beautifulsoup4` extracts text from HTML, and `ddgs` powers DuckDuckGo search results.
- At least one supported model provider:
  - **Ollama** running locally (default) on `http://localhost:11434`
  - **OpenAI API** access with a valid key
  - **Mistral API** access with a valid key

## 2. Installation

1. Clone or copy the repository to your machine.
2. (Recommended) Create and activate a virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```
3. Install dependencies inside the environment:
   ```bash
   pip install requests beautifulsoup4 ddgs
   ```
4. Ensure Ollama or the remote provider you plan to use is reachable.

## 3. Configuration

Configuration is optional but recommended for convenience. The agent looks for `config.ini` inside the configuration directory (default: `~/.config/clia`). You can override the location with `--config-dir`.

Create `~/.config/clia/config.ini` with content such as:
```ini
[model]
provider = ollama           # ollama | openai | mistral
model = llama3
endpoint = http://localhost:11434
api_key =                   # required for openai/mistral
temperature = 0.7
timeout = 120
system_prompt = prompts/system-prompt.txt

[search]
provider = duckduckgo       # duckduckgo | google
api_key =                   # required when provider = google
engine_id =                 # Google Programmable Search Engine ID

[storage]
sessions_dir = ~/.config/clia/sessions

[debug]
log_file = /tmp/clia.log

[output]
truncation_limit = 4000
```
Notes:
- The CLI flags always override values from `config.ini`.
- For Google Programmable Search Engine, set both `api_key` and `engine_id`.
- DuckDuckGo search requires no API key but needs the `ddgs` Python package (installed earlier).
- Set `storage.sessions_dir` to change where sessions are saved. Paths may be absolute and will expand `~`.
- Provide `system_prompt` to point at a template file (absolute or relative to the config directory). Use `{tools}`, `{tool_descriptions}`, or `{{tools}}` inside the template to inject the current tool descriptions.
  See `docs/system-prompt-example.txt` for a starter template you can copy.
- Use `[debug] log_file` to choose where debug traces are written (defaults to `/tmp/clia.log`).
- Set `[output] truncation_limit` to adjust how many characters tool outputs keep before truncation (default 4000).

## 4. Running the Agent

Launch the agent from the repository root:
```bash
python3 agent_cli.py
```
Optional flags:
- `--provider`, `--model`, `--endpoint`, `--api-key`, `--temperature`, `--request-timeout`
- `--shell-timeout` (seconds limit for the shell tool)
- `--no-color` to disable ANSI colors
- `--config-dir` to point at a different configuration directory

Example (OpenAI provider):
```bash
python3 agent_cli.py --provider openai --model gpt-4o-mini --api-key "$OPENAI_API_KEY"
```

## 5. Using the Agent

### Conversation Flow
- Prompts appear after the `you>` label. Type a message and press Enter.
- The assistant responds after the `agent>` label, streaming in real time.
- If the model invokes a tool, the CLI prints the tool call and the tool’s output before continuing the dialogue.

### Slash Commands
Inputs starting with `/` are handled locally (not sent to the model). Built-in commands:
- `/help` – list available commands
- `/info` – display current provider/model and approximate session token usage
- `/save <name|path>` – save the conversation to the configured sessions directory or an explicit path
- `/load <name|path>` – load a previous session using a name or direct file path
- `/ls` – list saved sessions in the configured directory
- `/rm <name|path>` – delete a saved session file
- `/tail [N]` – display the last `N` conversation messages (defaults to 5)
- `/truncate on|off` – toggle global tool output truncation
- `/debug [on|off]` – toggle or display debug logging status
- `/debug_tool <tool> <json>` – execute a tool manually for debugging
  Example:
    `/debug_tool search_internet \"{\\"query\\": \\"format input data for fine tuning mistral model\\"}\"`
    `/debug_tool run_shell \"{\\"command\\": \\"ls\\"}\"`
- `/exit` – exit immediately

### Tool Permissions
When the model requests a tool that has not been pre-approved, the CLI prompts you to allow it once (`y`), deny it (`n`), or always (`a`). Permanent approvals are stored in `<config-dir>/allowed_tools`.

## 6. Default Tools
Tools registered by default:

| Tool | Description |
|------|-------------|
| `run_shell` | Execute shell commands in the repository workspace (timeout configurable). |
| `read_url` | Fetch webpage content, preserve links, and return a trimmed text summary. |
| `search_internet` | Perform DuckDuckGo (via `ddgs`) or Google PSE search and return snippets. |
| `bc` | Evaluate math expressions via the system `bc -l` calculator. |

Extend `clia/tools/__init__.py` and add modules under `clia/tools/` to create new tools.

## 7. Extending Slash Commands
Slash commands are implemented in `clia/commands/`. Each command exposes:
- `name`, `description`, and `usage`
- `execute(agent, argument)` returning a `CommandOutcome`

Add new command modules and register them in `clia/commands/__init__.py`.

## 8. Tips & Troubleshooting
- **Ollama 404**: Older Ollama versions might not expose `/api/chat`. The client falls back to `/api/generate`, but ensure the requested model is pulled (`ollama pull <model>`).
- **Missing packages**: If you see errors about `requests` or `ddgs`, install them in the active environment.
- **Session files**: Saved sessions are stored in `<config-dir>/sessions`. Delete files there to clean up old runs.
- **Logs**: The CLI prints any tool errors or HTTP failures to stdout. Use these messages to diagnose issues quickly.

---
Feel free to adapt the configuration, add tools, or implement additional commands to fit your workflow.
