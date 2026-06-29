from __future__ import annotations
import sqlite3
from pathlib import Path
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver

from app.graph.state import MigrationState
from app.graph.nodes.ingest import ingest_node
from app.graph.nodes.profile import profile_node
from app.graph.nodes.classify import classify_node, route_complexity
from app.graph.nodes.warn import warn_node
from app.graph.nodes.rank import rank_node
from app.graph.nodes.await_approval import await_approval_node
from app.graph.nodes.pick_next import pick_next_node, route_files_left
from app.graph.nodes.gather_context import gather_context_node
from app.graph.nodes.generate import generate_node
from app.graph.nodes.validate import validate_node, route_validation
from app.graph.nodes.self_correct import self_correct_node
from app.graph.nodes.commit import commit_node, flag_node, done_node


def build_graph():
    """Assemble and compile the full migration LangGraph with human-in-the-loop approval."""
    g = StateGraph(MigrationState)

    # ── Register nodes ───────────────────────────────────────────────
    g.add_node("ingest",          ingest_node)
    g.add_node("profile",         profile_node)
    g.add_node("classify",        classify_node)
    g.add_node("warn",            warn_node)
    g.add_node("rank",            rank_node)
    g.add_node("await_approval",  await_approval_node)
    g.add_node("pick_next",       pick_next_node)
    g.add_node("gather_context",  gather_context_node)
    g.add_node("generate",        generate_node)
    g.add_node("validate",        validate_node)
    g.add_node("self_correct",    self_correct_node)
    g.add_node("commit",          commit_node)
    g.add_node("flag",            flag_node)
    g.add_node("done",            done_node)

    # ── Linear planning edges ────────────────────────────────────────
    g.add_edge(START,      "ingest")
    g.add_edge("ingest",   "profile")
    g.add_edge("profile",  "classify")

    # classify → warn OR rank
    g.add_conditional_edges(
        "classify",
        route_complexity,
        {"warn": "warn", "rank": "rank"},
    )

    # warn → rank (migration still proceeds after warning)
    g.add_edge("warn",           "rank")
    # rank → await_approval: human reviews plan before conversion starts
    g.add_edge("rank",           "await_approval")
    g.add_edge("await_approval", "pick_next")

    # ── File execution loop ──────────────────────────────────────────
    g.add_conditional_edges(
        "pick_next",
        route_files_left,
        {"done": "done", "gather_context": "gather_context"},
    )

    g.add_edge("gather_context", "generate")
    g.add_edge("generate",       "validate")

    # validate → commit OR self_correct OR flag
    g.add_conditional_edges(
        "validate",
        route_validation,
        {"commit": "commit", "self_correct": "self_correct", "flag": "flag"},
    )

    # self_correct loops back to generate for a re-attempt
    g.add_edge("self_correct", "generate")

    # commit and flag both loop back to pick_next for the next file
    g.add_edge("commit", "pick_next")
    g.add_edge("flag",   "pick_next")

    # done is the terminal node
    g.add_edge("done", END)

    # SqliteSaver persists checkpoints to disk so approval-pause state survives
    # FastAPI restarts. check_same_thread=False is safe because SqliteSaver
    # serialises its own writes internally.
    db_path = Path(__file__).parent.parent.parent / "workspace" / "checkpoints.sqlite"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    return g.compile(checkpointer=SqliteSaver(conn))


# Module-level compiled graph — import this in the FastAPI layer
graph = build_graph()
