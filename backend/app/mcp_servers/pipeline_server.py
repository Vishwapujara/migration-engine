"""Pipeline MCP Server — drives the full LangGraph migration pipeline end-to-end.

Lets an external MCP client (e.g. Claude Desktop) run an entire migration —
clone, parse, rank, human approval, convert, validate, commit — by calling a
handful of tools instead of the individual code_analysis/validation/plan_manager
tools one at a time. Each run is backed by the same compiled LangGraph `graph`
used by the FastAPI service, so behavior (retries, checkpointing, the approval
interrupt) is identical either way.
"""
from __future__ import annotations
import json
import os
import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
os.chdir(os.path.join(os.path.dirname(__file__), "..", ".."))

from langgraph.types import Command
from mcp.server.fastmcp import FastMCP

from app.config import settings, SUPPORTED_MIGRATIONS
from app.graph.pipeline import graph
from app.graph.state import initial_state
from app.mcp_servers.plan_manager_server import get_progress

mcp = FastMCP("Pipeline Server")

# ── In-memory job store (mirrors the FastAPI layer's _jobs dict) ─────
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _update_job(job_id: str, **fields) -> None:
    with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id].update(fields)
            _jobs[job_id]["updated_at"] = _now()


def _drain(job_id: str, stream) -> None:
    """Consume a graph.stream() iterator on a background thread, updating job state.

    Runs until the graph either hits the await_approval interrupt or finishes —
    tool calls that kick this off return immediately so a long migration never
    blocks an MCP tool call.
    """
    try:
        for chunk in stream:
            if "__interrupt__" in chunk:
                interrupts = chunk["__interrupt__"]
                risk_summary: dict = {}
                if interrupts:
                    val = getattr(interrupts[0], "value", {}) or {}
                    risk_summary = val.get("plan_risk_summary", val) if isinstance(val, dict) else {}
                _update_job(job_id, status="awaiting_approval", plan_risk_summary=risk_summary)
                return

            for _node_name, node_output in chunk.items():
                messages = node_output.get("messages", [])
                if messages:
                    with _jobs_lock:
                        if job_id in _jobs:
                            _jobs[job_id]["messages"] = _jobs[job_id].get("messages", []) + messages
                            _jobs[job_id]["updated_at"] = _now()

        try:
            progress = json.loads(get_progress(job_id))
        except Exception:
            progress = {}

        _update_job(
            job_id,
            status="completed",
            stats=progress,
            output_repo_path=str(settings.workspace_dir / job_id / "output"),
        )
    except Exception as exc:
        _update_job(job_id, status="failed", error=str(exc))


# ------------------------------------------------------------------
# Tool 1: start_migration
# ------------------------------------------------------------------

@mcp.tool()
def start_migration(repo_url: str, source_language: str, target_language: str) -> str:
    """Start a full end-to-end migration from a GitHub repository URL.

    Clones the repo, parses every file, builds the dependency graph, and ranks
    files by risk — then pauses for human approval. Runs in the background;
    poll get_migration_status with the returned job_id until status becomes
    'awaiting_approval'.

    Args:
        repo_url: HTTPS GitHub repository URL to clone.
        source_language: Language to convert from ('python' or 'javascript').
        target_language: Language to convert to ('python', 'javascript', or 'typescript').

    Returns:
        JSON with 'job_id' and 'status', or an 'error' if the language pair
        isn't supported.
    """
    if (source_language, target_language) not in SUPPORTED_MIGRATIONS:
        return json.dumps({
            "error": f"Migration pair ({source_language} -> {target_language}) is not supported.",
            "supported": [list(pair) for pair in SUPPORTED_MIGRATIONS],
        })

    job_id = str(uuid.uuid4())
    state = initial_state(
        job_id=job_id,
        source_language=source_language,
        target_language=target_language,
        repo_url=repo_url,
    )

    with _jobs_lock:
        _jobs[job_id] = {
            "job_id": job_id,
            "status": "pending",
            "source_language": source_language,
            "target_language": target_language,
            "repo_url": repo_url,
            "messages": [],
            "created_at": _now(),
            "updated_at": _now(),
        }

    config = {"configurable": {"thread_id": job_id}}
    stream = graph.stream(state, config=config, stream_mode="updates")
    thread = threading.Thread(
        target=_drain, args=(job_id, stream), daemon=True, name=f"pipeline-{job_id}"
    )
    _update_job(job_id, status="running")
    thread.start()

    return json.dumps({"job_id": job_id, "status": "running"})


# ------------------------------------------------------------------
# Tool 2: get_migration_status
# ------------------------------------------------------------------

@mcp.tool()
def get_migration_status(job_id: str) -> str:
    """Check the current status of a running or paused migration job.

    Args:
        job_id: Job identifier returned by start_migration.

    Returns:
        JSON with 'status' (pending/running/awaiting_approval/completed/failed),
        the most recent messages, and 'plan_risk_summary' once awaiting approval.
    """
    with _jobs_lock:
        job = _jobs.get(job_id)
    if job is None:
        return json.dumps({"error": f"Job {job_id} not found."})
    return json.dumps({**job, "messages": job.get("messages", [])[-20:]})


# ------------------------------------------------------------------
# Tool 3: approve_migration
# ------------------------------------------------------------------

@mcp.tool()
def approve_migration(job_id: str) -> str:
    """Approve the migration plan and resume the pipeline to convert every file.

    Call this only after get_migration_status reports 'awaiting_approval' and
    the plan_risk_summary has been reviewed with the human. Runs in the
    background — poll get_migration_status until status is 'completed' or
    'failed'.

    Args:
        job_id: Job identifier returned by start_migration.

    Returns:
        JSON with 'job_id' and 'status', or an 'error' if the job isn't
        currently awaiting approval.
    """
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is None:
            return json.dumps({"error": f"Job {job_id} not found."})
        if job["status"] != "awaiting_approval":
            return json.dumps({
                "error": f"Job is not awaiting approval (current status: {job['status']})."
            })

    config = {"configurable": {"thread_id": job_id}}
    stream = graph.stream(Command(resume=True), config=config, stream_mode="updates")
    thread = threading.Thread(
        target=_drain, args=(job_id, stream), daemon=True, name=f"pipeline-resume-{job_id}"
    )
    _update_job(job_id, status="running")
    thread.start()

    return json.dumps({"job_id": job_id, "status": "running"})


# ------------------------------------------------------------------
# Tool 4: get_migration_result
# ------------------------------------------------------------------

@mcp.tool()
def get_migration_result(job_id: str) -> str:
    """Return the final report and output location for a completed migration.

    Args:
        job_id: Job identifier returned by start_migration.

    Returns:
        JSON with 'stats', 'report' (migration_report.json contents), and
        'output_repo_path' (local disk path holding the converted files).
    """
    with _jobs_lock:
        job = _jobs.get(job_id)
    if job is None:
        return json.dumps({"error": f"Job {job_id} not found."})
    if job["status"] not in ("completed", "failed"):
        return json.dumps({"error": f"Job is still {job['status']}."})

    out_dir = Path(job.get("output_repo_path") or "")
    report_path = out_dir / "migration_report.json"
    report = json.loads(report_path.read_text()) if report_path.exists() else {}

    return json.dumps({
        "job_id": job_id,
        "status": job["status"],
        "stats": job.get("stats"),
        "report": report,
        "output_repo_path": job.get("output_repo_path"),
        "error": job.get("error"),
    })


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
