from __future__ import annotations

from app.graph.state import MigrationState
from app.code_analysis.registry import parse_file


def profile_node(state: MigrationState) -> dict:
    """PROFILE: Parse every source file with tree-sitter; build ParsedFile list."""
    if state.get("error"):
        return {}

    repo_files = state["repo_files"]
    parsed: list[dict] = []
    errors = 0

    for rf in repo_files:
        try:
            pf = parse_file(rf["rel_path"], rf["source"])
            if pf:
                parsed.append(pf.model_dump())
            else:
                errors += 1
        except Exception:
            errors += 1

    avg_complexity = (
        round(sum(p["complexity_score"] for p in parsed) / len(parsed), 2)
        if parsed else 0.0
    )

    return {
        "parsed_files": parsed,
        "messages": [
            f"[PROFILE] Parsed {len(parsed)} files ({errors} parse errors). "
            f"Avg complexity: {avg_complexity}."
        ],
    }
