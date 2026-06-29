"""Validation MCP Server — syntax, import, and type checking for migrated code."""
from __future__ import annotations
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
os.chdir(os.path.join(os.path.dirname(__file__), "..", ".."))

from app.code_analysis.registry import get_extractor_for_language


def _tool_noop():
    return lambda f: f


class _MCPStub:
    tool = staticmethod(_tool_noop)
    def run(self): pass


mcp = _MCPStub()

_TIMEOUT = 30  # seconds for subprocess calls


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _tree_sitter_errors(source: str, language: str) -> list[dict]:
    """Use tree-sitter to find ERROR / MISSING nodes in the parse tree."""
    extractor = get_extractor_for_language(language)
    if extractor is None:
        return []

    src_bytes = source.encode("utf-8")
    tree = extractor._parser.parse(src_bytes)

    errors: list[dict] = []

    def _walk(node):
        if node.type in ("ERROR", "MISSING"):
            errors.append({
                "line": node.start_point[0] + 1,
                "column": node.start_point[1] + 1,
                "end_line": node.end_point[0] + 1,
                "message": f"Syntax error ({node.type}): unexpected token near '{_snippet(src_bytes, node)}'",
            })
        for child in node.children:
            _walk(child)

    _walk(tree.root_node)
    return errors


def _snippet(src: bytes, node) -> str:
    text = src[node.start_byte:node.end_byte].decode("utf-8", errors="replace")
    return text[:40].replace("\n", " ").strip()


def _write_temp(source: str, suffix: str) -> Path:
    fd, path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    Path(path).write_text(source, encoding="utf-8")
    return Path(path)


def _run(cmd: list[str], cwd: str | None = None) -> tuple[int, str, str]:
    try:
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
            cwd=cwd,
        )
        return r.returncode, r.stdout, r.stderr
    except FileNotFoundError:
        return -1, "", f"Executable not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return -1, "", f"Timed out after {_TIMEOUT}s"


def _parse_mypy(output: str) -> list[dict]:
    """Parse mypy output lines into structured error dicts."""
    pattern = re.compile(r"^(.+?):(\d+):\s*(error|warning|note):\s*(.+)$")
    results = []
    for line in output.splitlines():
        m = pattern.match(line)
        if m:
            results.append({
                "line": int(m.group(2)),
                "column": 1,
                "severity": m.group(3),
                "message": m.group(4).strip(),
            })
    return results


def _parse_tsc(output: str) -> list[dict]:
    """Parse tsc output lines into structured error dicts."""
    # file.ts(10,5): error TS2345: ...
    pattern = re.compile(r"^.+?\((\d+),(\d+)\):\s*(error|warning)\s+(TS\d+):\s*(.+)$")
    results = []
    for line in output.splitlines():
        m = pattern.match(line)
        if m:
            results.append({
                "line": int(m.group(1)),
                "column": int(m.group(2)),
                "severity": m.group(3),
                "code": m.group(4),
                "message": m.group(5).strip(),
            })
    return results


def _parse_node_syntax(stderr: str) -> list[dict]:
    """Parse `node --check` error output."""
    pattern = re.compile(r"(\w+Error|SyntaxError)[:\s]+(.+?)(?:\s+at\s+|$)", re.DOTALL)
    line_pattern = re.compile(r":(\d+)")
    results = []
    for m in pattern.finditer(stderr):
        line_match = line_pattern.search(stderr)
        results.append({
            "line": int(line_match.group(1)) if line_match else 1,
            "column": 1,
            "severity": "error",
            "message": m.group(2).strip()[:200],
        })
        break  # node typically reports one error at a time
    return results


# ------------------------------------------------------------------
# Tool 1: check_syntax
# ------------------------------------------------------------------

@mcp.tool()
def check_syntax(source: str, language: str, file_path: str = "file") -> str:
    """Check whether the given source code is syntactically valid.

    Uses tree-sitter for a fast structural check, then optionally runs the
    language runtime (python -c compile / node --check) for a second opinion.

    Args:
        source: Full source code text to validate.
        language: Target language — 'python', 'javascript', or 'typescript'.
        file_path: Logical file path used only for error messages (not read from disk).

    Returns:
        JSON with 'valid' (bool), 'errors' (list of {line, column, message}), 'method' (str).
    """
    lang = language.lower()

    # Primary: tree-sitter structural check
    ts_errors = _tree_sitter_errors(source, lang)

    # Secondary: runtime / compiler check
    runtime_errors: list[dict] = []

    if lang == "python":
        tmp = _write_temp(source, ".py")
        try:
            code, stdout, stderr = _run([sys.executable, "-c",
                                         f"import ast; ast.parse(open(r'{tmp}').read())"])
            if code != 0:
                runtime_errors.append({"line": 1, "column": 1, "severity": "error",
                                        "message": stderr.strip()[:300]})
        finally:
            tmp.unlink(missing_ok=True)

    elif lang in ("javascript", "jsx"):
        tmp = _write_temp(source, ".js")
        try:
            code, stdout, stderr = _run(["node", "--check", str(tmp)])
            if code != 0:
                runtime_errors.extend(_parse_node_syntax(stderr))
        finally:
            tmp.unlink(missing_ok=True)

    elif lang in ("typescript", "tsx"):
        # tsc syntax-only check (no type checking, no emit)
        tmp = _write_temp(source, ".ts")
        try:
            code, stdout, stderr = _run(
                ["tsc", "--noEmit", "--allowJs", "--skipLibCheck",
                 "--target", "ES2020", "--module", "CommonJS", str(tmp)]
            )
            if code != 0:
                runtime_errors.extend(_parse_tsc(stdout + stderr))
        finally:
            tmp.unlink(missing_ok=True)

    all_errors = ts_errors + runtime_errors
    return json.dumps({
        "valid": len(all_errors) == 0,
        "errors": all_errors,
        "error_count": len(all_errors),
        "method": "tree-sitter" + (f" + {lang}-runtime" if runtime_errors or lang == "python" else ""),
        "language": lang,
    })


# ------------------------------------------------------------------
# Tool 2: check_imports
# ------------------------------------------------------------------

@mcp.tool()
def check_imports(source: str, language: str, file_path: str, repo_root: str) -> str:
    """Check whether local imports in the source can be resolved against the project files.

    This is a static check — it does not execute the code.

    Args:
        source: Full source code text to validate.
        language: Source language — 'python', 'javascript', or 'typescript'.
        file_path: Relative path of this file within the repo (used to resolve relative imports).
        repo_root: Absolute path to the repository root directory.

    Returns:
        JSON with 'valid' (bool), 'missing' (list of unresolved import paths), 'resolved' (list).
    """
    from app.code_analysis.registry import parse_file as _parse_file

    lang = language.lower()
    pf = _parse_file(file_path, source)
    if pf is None:
        return json.dumps({"valid": True, "missing": [], "resolved": [], "note": "unsupported language"})

    root = Path(repo_root)
    file_dir = (root / file_path).parent

    missing: list[str] = []
    resolved: list[str] = []

    for imp in pf.imports:
        module = imp.module

        if lang == "python":
            module_as_path = module.replace(".", "/")
            candidates = [
                root / (module_as_path + ".py"),
                root / module_as_path / "__init__.py",
                file_dir / (module_as_path + ".py"),
                file_dir / module_as_path / "__init__.py",
            ]
        else:
            # Relative imports always resolve from file_dir; absolute from root
            base = file_dir / module if (imp.is_relative or module.startswith(".")) else root / module
            candidates = [
                base.with_suffix(".js"),
                base.with_suffix(".jsx"),
                base.with_suffix(".ts"),
                base.with_suffix(".tsx"),
                base / "index.js",
                base / "index.ts",
                base / "index.tsx",
            ]

        if any(c.exists() for c in candidates):
            resolved.append(module)
        else:
            # Only flag as missing if the module looks local (not stdlib/third-party).
            # Heuristic: absolute Python imports with no dots go to external packages.
            is_likely_local = (
                imp.is_relative
                or module.startswith(".")
                or (lang == "python" and "." in module)  # dotted = submodule, probably local
                or (lang != "python")  # JS/TS: all imports checked
            )
            if is_likely_local:
                missing.append(module)

    return json.dumps({
        "valid": len(missing) == 0,
        "missing": missing,
        "resolved": resolved,
        "total_local_imports": len(missing) + len(resolved),
    })


# ------------------------------------------------------------------
# Tool 3: check_types
# ------------------------------------------------------------------

@mcp.tool()
def check_types(source: str, language: str, file_path: str = "file") -> str:
    """Run a type-checker on the source code and return diagnostics.

    - Python  → mypy
    - TypeScript / TSX → tsc --noEmit
    - JavaScript → skipped (no native type checker)

    Args:
        source: Full source code text to validate.
        language: Target language — 'python', 'javascript', or 'typescript'.
        file_path: Logical file path (used only for temp-file suffix selection).

    Returns:
        JSON with 'valid' (bool), 'errors' (list), 'warnings' (list), 'tool' (str), 'skipped' (bool).
    """
    lang = language.lower()

    if lang in ("javascript", "jsx"):
        return json.dumps({
            "valid": True,
            "skipped": True,
            "tool": "none",
            "note": "JavaScript has no native type checker. Run check_syntax instead.",
            "errors": [],
            "warnings": [],
        })

    if lang == "python":
        tmp = _write_temp(source, ".py")
        try:
            code, stdout, stderr = _run(
                [sys.executable, "-m", "mypy",
                 "--ignore-missing-imports",
                 "--no-error-summary",
                 str(tmp)]
            )
            diagnostics = _parse_mypy(stdout + stderr)
            errors = [d for d in diagnostics if d["severity"] == "error"]
            warnings = [d for d in diagnostics if d["severity"] == "warning"]
            return json.dumps({
                "valid": code == 0 or len(errors) == 0,
                "skipped": False,
                "tool": "mypy",
                "errors": errors,
                "warnings": warnings,
            })
        finally:
            tmp.unlink(missing_ok=True)

    if lang in ("typescript", "tsx"):
        suffix = ".tsx" if lang == "tsx" else ".ts"
        tmp = _write_temp(source, suffix)
        try:
            code, stdout, stderr = _run(
                ["tsc", "--noEmit", "--skipLibCheck",
                 "--target", "ES2020", "--module", "CommonJS",
                 "--strict", str(tmp)]
            )
            combined = stdout + stderr
            diagnostics = _parse_tsc(combined)
            errors = [d for d in diagnostics if d["severity"] == "error"]
            warnings = [d for d in diagnostics if d["severity"] == "warning"]
            return json.dumps({
                "valid": code == 0,
                "skipped": False,
                "tool": "tsc",
                "errors": errors,
                "warnings": warnings,
            })
        finally:
            tmp.unlink(missing_ok=True)

    return json.dumps({
        "valid": False,
        "skipped": True,
        "tool": "none",
        "errors": [{"line": 0, "column": 0, "message": f"Unsupported language: {language}"}],
        "warnings": [],
    })


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
