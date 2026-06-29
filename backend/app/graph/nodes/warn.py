from __future__ import annotations

from app.graph.state import MigrationState


def warn_node(state: MigrationState) -> dict:
    """WARN: Emit complexity warning; migration continues to RANK afterwards."""
    warning = state.get("complexity_warning") or "Codebase exceeds recommended complexity thresholds."
    return {
        "messages": [f"[WARN] {warning}"],
    }
