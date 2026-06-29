"""File System MCP Server — safe file I/O and command execution."""
from __future__ import annotations
import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
os.chdir(os.path.join(os.path.dirname(__file__), "..", ".."))

def _tool_noop():
    return lambda f: f


class _MCPStub:
    tool = staticmethod(_tool_noop)
    def run(self): pass


mcp = _MCPStub()

# Commands permitted in run_command — anything not in this set is rejected.
_ALLOWED_COMMANDS: frozenset[str] = frozenset({
    "python", "python3", "node", "npm", "npx", "pip", "pip3",
    "git", "tsc", "eslint", "prettier", "pytest", "mypy",
    "ruff", "black", "isort", "flake8", "pylint",
})

_CMD_TIMEOUT_SECONDS = 60


# ------------------------------------------------------------------
# Tool 1: read_file
# ------------------------------------------------------------------

@mcp.tool()
def read_file(file_path: str, encoding: str = "utf-8") -> str:
    """Read the full text content of a file from disk.

    Args:
        file_path: Absolute or relative path to the file.
        encoding: File encoding (default utf-8).

    Returns:
        JSON object with 'content' (str), 'size_bytes' (int), and 'exists' (bool).
    """
    p = Path(file_path)
    if not p.exists():
        return json.dumps({"exists": False, "content": None, "size_bytes": 0})
    try:
        content = p.read_text(encoding=encoding, errors="replace")
        return json.dumps({
            "exists": True,
            "content": content,
            "size_bytes": p.stat().st_size,
        })
    except OSError as exc:
        return json.dumps({"exists": True, "content": None, "size_bytes": 0, "error": str(exc)})


# ------------------------------------------------------------------
# Tool 2: write_file
# ------------------------------------------------------------------

@mcp.tool()
def write_file(file_path: str, content: str, encoding: str = "utf-8") -> str:
    """Write text content to a file, creating parent directories as needed.

    Args:
        file_path: Absolute or relative path to the target file.
        content: Text content to write.
        encoding: File encoding (default utf-8).

    Returns:
        JSON object with 'success' (bool), 'bytes_written' (int), and optional 'error'.
    """
    p = Path(file_path)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding=encoding)
        return json.dumps({"success": True, "bytes_written": p.stat().st_size})
    except OSError as exc:
        return json.dumps({"success": False, "bytes_written": 0, "error": str(exc)})


# ------------------------------------------------------------------
# Tool 3: rename_file
# ------------------------------------------------------------------

@mcp.tool()
def rename_file(source_path: str, dest_path: str) -> str:
    """Move or rename a file or directory.

    Args:
        source_path: Current path of the file or directory.
        dest_path: New path (parent directories are created automatically).

    Returns:
        JSON object with 'success' (bool) and optional 'error'.
    """
    src = Path(source_path)
    dst = Path(dest_path)
    if not src.exists():
        return json.dumps({"success": False, "error": f"Source not found: {source_path}"})
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        return json.dumps({"success": True, "source": source_path, "destination": dest_path})
    except OSError as exc:
        return json.dumps({"success": False, "error": str(exc)})


# ------------------------------------------------------------------
# Tool 4: delete_file
# ------------------------------------------------------------------

@mcp.tool()
def delete_file(file_path: str) -> str:
    """Delete a file (not a directory) from disk.

    Args:
        file_path: Absolute or relative path to the file to delete.

    Returns:
        JSON object with 'success' (bool) and optional 'error'.
    """
    p = Path(file_path)
    if not p.exists():
        return json.dumps({"success": True, "note": "file did not exist"})
    if p.is_dir():
        return json.dumps({"success": False, "error": "Path is a directory; only files may be deleted."})
    try:
        p.unlink()
        return json.dumps({"success": True})
    except OSError as exc:
        return json.dumps({"success": False, "error": str(exc)})


# ------------------------------------------------------------------
# Tool 5: run_command
# ------------------------------------------------------------------

@mcp.tool()
def run_command(command: str, cwd: str | None = None, timeout: int = _CMD_TIMEOUT_SECONDS) -> str:
    """Execute a shell command from a safety allowlist and return its output.

    Allowed executables: python, python3, node, npm, npx, pip, pip3, git, tsc,
    eslint, prettier, pytest, mypy, ruff, black, isort, flake8, pylint.

    Args:
        command: Full command string (e.g. 'python -m pytest tests/').
        cwd: Working directory for the command. Defaults to current directory.
        timeout: Max seconds before the process is killed (default 60).

    Returns:
        JSON object with 'stdout', 'stderr', 'returncode', and 'success' (bool).
    """
    try:
        parts = shlex.split(command, posix=(os.name != "nt"))
    except ValueError as exc:
        return json.dumps({"success": False, "error": f"Command parse error: {exc}"})

    if not parts:
        return json.dumps({"success": False, "error": "Empty command."})

    executable = Path(parts[0]).name.lower().removesuffix(".exe")
    if executable not in _ALLOWED_COMMANDS:
        return json.dumps({
            "success": False,
            "error": (
                f"Command '{executable}' is not in the safety allowlist. "
                f"Allowed: {sorted(_ALLOWED_COMMANDS)}"
            ),
        })

    try:
        result = subprocess.run(
            parts,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return json.dumps({
            "success": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        })
    except subprocess.TimeoutExpired:
        return json.dumps({"success": False, "error": f"Command timed out after {timeout}s."})
    except FileNotFoundError:
        return json.dumps({"success": False, "error": f"Executable not found: {parts[0]}"})
    except OSError as exc:
        return json.dumps({"success": False, "error": str(exc)})


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
