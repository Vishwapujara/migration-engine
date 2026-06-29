from __future__ import annotations
import json

from app.graph.state import MigrationState
from app.mcp_servers.plan_manager_server import get_next_file


def pick_next_node(state: MigrationState) -> dict:
    """PICK_NEXT: Ask Plan Manager for the next pending file."""
    if state.get("error"):
        return {"current_file": None}

    result = json.loads(get_next_file(state["job_id"]))

    if result.get("done"):
        return {
            "current_file": None,
            "current_source": None,
            "current_converted": None,
            "current_context": [],
            "current_validation_errors": [],
            "self_correction_attempts": 0,
            "messages": [f"[PICK_NEXT] All files processed. {result.get('stats', {}).get('converted', 0)} converted."],
        }

    return {
        "current_file": result["file_path"],
        "current_source": result["original_source"],
        "current_converted": None,
        "current_context": [],
        "current_validation_errors": [],
        "self_correction_attempts": 0,
        "messages": [
            f"[PICK_NEXT] Converting: {result['file_path']} "
            f"({result['complexity_class']}, {result['line_count']} lines)"
        ],
    }


def route_files_left(state: MigrationState) -> str:
    """Conditional edge: no more files -> done, else -> gather_context."""
    return "done" if state.get("current_file") is None else "gather_context"
