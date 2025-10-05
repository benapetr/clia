from __future__ import annotations

import selectors
import subprocess
import sys
import time
from typing import Any, Dict

from clia.tooling import Tool
from clia.utils import truncate


def create_tool(shell_timeout: int = 60) -> Tool:
    def run(args: Dict[str, Any]) -> str:
        command = args.get("command")
        if not command:
            return "ERROR: 'command' argument is required"
        start_time = time.monotonic()
        try:
            process = subprocess.Popen(
                command,
                shell=True,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=1,
            )
        except OSError as exc:
            return f"ERROR: failed to start command: {exc}"

        selector = selectors.DefaultSelector()
        captured_stdout: list[str] = []
        captured_stderr: list[str] = []

        if process.stdout:
            selector.register(process.stdout, selectors.EVENT_READ, ("stdout", captured_stdout))
        if process.stderr:
            selector.register(process.stderr, selectors.EVENT_READ, ("stderr", captured_stderr))

        try:
            while selector.get_map():
                for key, _ in selector.select(timeout=0.1):
                    stream_name, sink = key.data
                    chunk = key.fileobj.readline()
                    if chunk == "":
                        selector.unregister(key.fileobj)
                        continue
                    sink.append(chunk)
                    print(chunk, end="", flush=True)
                if shell_timeout and time.monotonic() - start_time > shell_timeout:
                    process.kill()
                    return "ERROR: command timed out"
                if process.poll() is not None and not selector.get_map():
                    break
            try:
                remaining = None
                if shell_timeout:
                    elapsed = time.monotonic() - start_time
                    remaining = max(0.0, shell_timeout - elapsed)
                process.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                process.kill()
                return "ERROR: command timed out"
        finally:
            for key in list(selector.get_map().values()):
                selector.unregister(key.fileobj)
                key.fileobj.close()

        exit_code = process.returncode if process.returncode is not None else -1
        stdout_text = "".join(captured_stdout).strip()
        stderr_text = "".join(captured_stderr).strip()
        status = f"exit code {exit_code}"
        combined = stdout_text
        if stderr_text:
            combined = f"{combined}\n[stderr]\n{stderr_text}" if combined else f"[stderr]\n{stderr_text}"
        summary = status
        if combined:
            summary = f"{status}\n{combined}"
        return truncate(summary.strip())

    return Tool(
        name="run_shell",
        description=f"Execute a shell command inside the current workspace (timeout {shell_timeout}s). Commands are run in Linux environment and must not be interactive.",
        schema='{"command": "<shell command string>"}',
        handler=run,
    )
