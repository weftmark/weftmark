"""Runs claude -p non-interactively and returns the output."""

import asyncio
import subprocess
from functools import partial

from config import settings


def _run_sync(prompt: str, allowed_tools: str) -> str:
    cmd = [
        settings.claude_bin,
        "-p", prompt,
        "--allowedTools", allowed_tools,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", cwd=settings.repo_path)
    if result.returncode != 0:
        raise RuntimeError(f"claude exited {result.returncode}: {result.stderr[:500]}")
    return result.stdout.strip()


async def run_claude(prompt: str, allowed_tools: str = "Bash,Read,Glob,Grep") -> str:
    """Invoke the claude CLI with the given prompt and return stdout."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, partial(_run_sync, prompt, allowed_tools))
