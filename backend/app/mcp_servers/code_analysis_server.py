"""Code Analysis MCP Server — AST parsing and dependency graph tools."""
from __future__ import annotations
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
os.chdir(os.path.join(os.path.dirname(__file__), "..", ".."))

def _tool_noop():
    return lambda f: f


class _MCPStub:
    tool = staticmethod(_tool_noop)
    def run(self): pass


mcp = _MCPStub()

from app.code_analysis.registry import (
    parse_file as _parse_file,
    detect_language as _detect_language,
    supported_extensions,
)
from app.ingestion.dependency_graph import DependencyGraph

mcp = FastMCP("Code Analysis Server")

# Module-level graph instance shared across tool calls within a session
_graph = DependencyGraph()


# ------------------------------------------------------------------
# Tool 1: parse_file
# ------------------------------------------------------------------

@mcp.tool()
def parse_file(file_path: str, source: str) -> str:
    """Parse a single source file and return its AST summary as JSON.

    Args:
        file_path: Relative path of the file (used to infer language via extension).
        source: Full source code text of the file.

    Returns:
        JSON string containing imports, functions, classes, complexity score, and dependency lists.
    """
    result = _parse_file(file_path, source)
    if result is None:
        return json.dumps({"error": f"Unsupported file extension: {file_path}"})
    return result.model_dump_json()


# ------------------------------------------------------------------
# Tool 2: parse_files_batch
# ------------------------------------------------------------------

@mcp.tool()
def parse_files_batch(files: list[dict]) -> str:
    """Parse multiple source files in one call.

    Args:
        files: List of objects, each with keys 'file_path' (str) and 'source' (str).

    Returns:
        JSON array of ParsedFile objects. Files that fail to parse include an 'error' key.
    """
    results = []
    for item in files:
        fp = item.get("file_path", "")
        src = item.get("source", "")
        try:
            pf = _parse_file(fp, src)
            if pf:
                results.append(json.loads(pf.model_dump_json()))
            else:
                results.append({"file_path": fp, "error": "unsupported extension"})
        except Exception as exc:
            results.append({"file_path": fp, "error": str(exc)})
    return json.dumps(results)


# ------------------------------------------------------------------
# Tool 3: detect_language
# ------------------------------------------------------------------

@mcp.tool()
def detect_language(file_path: str) -> str:
    """Detect the programming language of a file based on its extension.

    Args:
        file_path: Path or filename (only the extension matters).

    Returns:
        JSON object with 'language' (str or null) and 'supported_extensions' list.
    """
    lang = _detect_language(file_path)
    return json.dumps({
        "language": lang,
        "supported_extensions": supported_extensions(),
    })


# ------------------------------------------------------------------
# Tool 4: build_dependency_graph
# ------------------------------------------------------------------

@mcp.tool()
def build_dependency_graph(parsed_files_json: str, repo_root: str) -> str:
    """Build a dependency graph from a list of ParsedFile JSON objects.

    Args:
        parsed_files_json: JSON array of ParsedFile objects (output of parse_files_batch).
        repo_root: Absolute path to the repository root directory.

    Returns:
        JSON object with nodes, edges, node_count, edge_count, and has_cycles flag.
    """
    from app.code_analysis.models import ParsedFile

    raw = json.loads(parsed_files_json)
    parsed = [ParsedFile.model_validate(item) for item in raw]
    _graph.build(parsed, repo_root)
    return json.dumps(_graph.to_dict())


# ------------------------------------------------------------------
# Tool 5: get_dependents
# ------------------------------------------------------------------

@mcp.tool()
def get_dependents(file_path: str) -> str:
    """Return all files that directly import the given file.

    Args:
        file_path: Relative path of the file to query.

    Returns:
        JSON object with 'direct' and 'all_transitive' lists of file paths.
    """
    return json.dumps({
        "file_path": file_path,
        "direct": _graph.get_dependents(file_path),
        "all_transitive": _graph.get_all_dependents(file_path),
    })


# ------------------------------------------------------------------
# Tool 6: get_dependencies
# ------------------------------------------------------------------

@mcp.tool()
def get_dependencies(file_path: str) -> str:
    """Return all files that the given file directly imports.

    Args:
        file_path: Relative path of the file to query.

    Returns:
        JSON object with 'direct' and 'all_transitive' lists of file paths.
    """
    return json.dumps({
        "file_path": file_path,
        "direct": _graph.get_dependencies(file_path),
        "all_transitive": _graph.get_all_dependencies(file_path),
    })


# ------------------------------------------------------------------
# Tool 7: get_topological_order
# ------------------------------------------------------------------

@mcp.tool()
def get_topological_order() -> str:
    """Return files in topological order (dependencies before dependents).

    Dependency-free files appear first so they can be converted first.
    If the graph has cycles, a best-effort order is returned.

    Returns:
        JSON array of file paths in processing order.
    """
    return json.dumps(_graph.get_topological_order())


# ------------------------------------------------------------------
# Tool 8: get_circular_dependencies
# ------------------------------------------------------------------

@mcp.tool()
def get_circular_dependencies() -> str:
    """Detect all circular dependency cycles in the codebase.

    Returns:
        JSON object with 'cycles' (list of file-path lists) and 'count'.
    """
    cycles = _graph.get_circular_dependencies()
    return json.dumps({"cycles": cycles, "count": len(cycles)})


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
