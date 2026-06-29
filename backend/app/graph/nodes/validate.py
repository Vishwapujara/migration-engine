from __future__ import annotations
import json

from app.graph.state import MigrationState
from app.config import settings
from app.mcp_servers.validation_server import check_syntax, check_types


def validate_node(state: MigrationState) -> dict:
    """VALIDATE: Run syntax + type checks on current_converted."""
    if state.get("error") or not state.get("current_file"):
        return {}

    converted = state.get("current_converted") or ""
    tgt_lang = state["target_language"]

    if not converted:
        errors = [{"line": 0, "column": 0, "message": "No converted source produced by GENERATE."}]
        return {
            "current_validation_errors": errors,
            "messages": [f"[VALIDATE] {state['current_file']}: FAIL — empty output from LLM."],
        }

    all_errors: list[dict] = []

    # Syntax check
    syntax_result = json.loads(check_syntax(converted, tgt_lang, state["current_file"]))
    all_errors.extend(syntax_result.get("errors", []))

    # Type check (only if syntax passed — avoids redundant cascaded errors)
    if not all_errors:
        type_result = json.loads(check_types(converted, tgt_lang, state["current_file"]))
        if not type_result.get("skipped"):
            all_errors.extend(type_result.get("errors", []))

    status = "PASS" if not all_errors else f"FAIL ({len(all_errors)} errors)"
    return {
        "current_validation_errors": all_errors,
        "messages": [f"[VALIDATE] {state['current_file']}: {status}"],
    }


def route_validation(state: MigrationState) -> str:
    """Conditional edge: pass -> commit, fail < max_retries -> self_correct, else -> flag."""
    errors = state.get("current_validation_errors", [])
    attempts = state.get("self_correction_attempts", 0)
    if not errors:
        return "commit"
    if attempts < settings.max_self_correction_retries:
        return "self_correct"
    return "flag"
