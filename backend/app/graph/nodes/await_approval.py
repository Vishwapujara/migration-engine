from __future__ import annotations
from langgraph.types import interrupt

from app.graph.state import MigrationState


def await_approval_node(state: MigrationState) -> dict:
    """AWAIT_APPROVAL: Pause the graph until the user approves the migration plan.

    LangGraph's interrupt() saves the checkpoint and yields {"__interrupt__": ...}
    in the stream. The graph resumes when the caller sends Command(resume=True).
    """
    if state.get("error"):
        return {}

    plan_risk = state.get("plan_risk_summary", {})
    total_files = len(state.get("topological_order", []))

    high_count  = sum(1 for v in plan_risk.values() if v.get("risk_level") == "high")
    med_count   = sum(1 for v in plan_risk.values() if v.get("risk_level") == "medium")
    low_count   = total_files - high_count - med_count

    # Pause here — resumes after Command(resume=True) is sent
    interrupt({
        "plan_risk_summary": plan_risk,
        "total_files": total_files,
        "risk_counts": {"high": high_count, "medium": med_count, "low": low_count},
    })

    # Execution continues here after user approves
    return {
        "messages": [
            f"[AWAIT_APPROVAL] Plan approved by user. "
            f"Starting conversion of {total_files} files "
            f"(high-risk: {high_count}, medium: {med_count}, low: {low_count})."
        ],
    }
