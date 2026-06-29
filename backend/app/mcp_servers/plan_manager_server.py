"""Plan Manager — tracks per-job migration plans in memory + disk.

Functions are called directly from graph nodes (no MCP transport needed).
The @tool decorator is a no-op identity wrapper kept for future MCP compatibility.
"""
from __future__ import annotations
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Literal, TypeVar

_F = TypeVar("_F", bound=Callable)


def _tool_noop() -> Callable[[_F], _F]:
    """Identity decorator — functions are called directly, not via MCP transport."""
    def decorator(func: _F) -> _F:
        return func
    return decorator


class _PlanManagerStub:
    """Stub that makes @mcp.tool() a no-op so functions remain plain callables."""
    tool = staticmethod(_tool_noop)

    def run(self) -> None:
        print("Plan Manager: running in direct-call mode (no MCP transport).")


mcp = _PlanManagerStub()

FileStatus = Literal["pending", "in_progress", "converted", "failed", "flagged"]

# ── In-memory store ──────────────────────────────────────────────────
_plans: dict[str, dict] = {}

# ── Disk persistence ─────────────────────────────────────────────────
_WORKSPACE = Path(os.environ.get("WORKSPACE_DIR", "/app/workspace"))


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _complexity_class(score: float) -> str:
    if score < 3.0:
        return "simple"
    if score < 6.0:
        return "moderate"
    return "complex"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _plan_path(job_id: str) -> Path:
    return _WORKSPACE / job_id / "plan.json"


def _save_plan(job_id: str) -> None:
    try:
        path = _plan_path(job_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(_plans[job_id]))
    except Exception:
        pass  # Non-fatal — disk write failure doesn't break the migration


def _require_plan(job_id: str) -> dict | None:
    if job_id in _plans:
        return _plans[job_id]
    # Try loading from disk (survives FastAPI restart)
    path = _plan_path(job_id)
    if path.exists():
        try:
            _plans[job_id] = json.loads(path.read_text())
            return _plans[job_id]
        except Exception:
            pass
    return None


def _stats(plan: dict) -> dict:
    files = plan["files"]
    counts: dict[str, int] = {
        "pending": 0, "in_progress": 0,
        "converted": 0, "failed": 0, "flagged": 0,
    }
    complexity_dist: dict[str, int] = {"simple": 0, "moderate": 0, "complex": 0}

    for f in files.values():
        counts[f["status"]] = counts.get(f["status"], 0) + 1
        complexity_dist[f["complexity_class"]] += 1

    total = len(files)
    done = counts["converted"] + counts["failed"] + counts["flagged"]
    return {
        "total": total,
        "done": done,
        "pending": counts["pending"],
        "in_progress": counts["in_progress"],
        "converted": counts["converted"],
        "failed": counts["failed"],
        "flagged": counts["flagged"],
        "percent_complete": round((done / total * 100) if total else 0, 1),
        "complexity_distribution": complexity_dist,
    }


# ------------------------------------------------------------------
# Tool 1: initialize_plan
# ------------------------------------------------------------------

@mcp.tool()
def initialize_plan(
    job_id: str,
    source_language: str,
    target_language: str,
    parsed_files_json: str,
    topological_order_json: str,
) -> str:
    """Create a new migration plan for a job.

    Args:
        job_id: Unique job identifier.
        source_language: Language being migrated from (e.g. 'python').
        target_language: Language being migrated to (e.g. 'javascript').
        parsed_files_json: JSON array of ParsedFile objects from parse_files_batch.
        topological_order_json: JSON array of file paths in dependency-first order.

    Returns:
        JSON with 'success' (bool), 'job_id', 'total_files', and 'complexity_distribution'.
    """
    try:
        raw_files = json.loads(parsed_files_json)
        topo_order: list[str] = json.loads(topological_order_json)
    except json.JSONDecodeError as exc:
        return json.dumps({"success": False, "error": f"Invalid JSON: {exc}"})

    # Build order lookup
    order_index = {path: i for i, path in enumerate(topo_order)}

    files: dict[str, dict] = {}
    for pf in raw_files:
        fp = pf.get("file_path", "")
        score = float(pf.get("complexity_score", 0.0))
        files[fp] = {
            "file_path": fp,
            "language": pf.get("language", source_language),
            "status": "pending",
            "complexity_score": score,
            "complexity_class": _complexity_class(score),
            "line_count": pf.get("line_count", 0),
            "original_source": pf.get("raw_source", ""),
            "converted_source": None,
            "validation_errors": [],
            "retry_count": 0,
            "retry_history": [],
            "order": order_index.get(fp, 9999),
            "started_at": None,
            "completed_at": None,
            "imports": pf.get("imports", []),
            "functions": [f["name"] for f in pf.get("functions", [])],
            "classes": [c["name"] for c in pf.get("classes", [])],
        }

    _plans[job_id] = {
        "job_id": job_id,
        "source_language": source_language,
        "target_language": target_language,
        "files": files,
        "topological_order": topo_order,
        "created_at": _now(),
        "updated_at": _now(),
    }

    _save_plan(job_id)
    st = _stats(_plans[job_id])
    return json.dumps({
        "success": True,
        "job_id": job_id,
        "total_files": st["total"],
        "complexity_distribution": st["complexity_distribution"],
        "topological_order": topo_order,
    })


# ------------------------------------------------------------------
# Tool 2: get_next_file
# ------------------------------------------------------------------

@mcp.tool()
def get_next_file(job_id: str) -> str:
    """Return the next pending file to convert and mark it as in_progress.

    Files are returned in topological order (dependencies first).

    Args:
        job_id: Unique job identifier.

    Returns:
        JSON with 'file_path', 'language', 'complexity_class', 'original_source',
        'local_dependencies', or 'done' (bool) if all files are processed.
    """
    plan = _require_plan(job_id)
    if plan is None:
        return json.dumps({"error": f"No plan found for job_id={job_id}"})

    files = plan["files"]
    # Walk topological order; pick first pending file
    for fp in plan["topological_order"]:
        entry = files.get(fp)
        if entry and entry["status"] == "pending":
            entry["status"] = "in_progress"
            entry["started_at"] = _now()
            plan["updated_at"] = _now()
            return json.dumps({
                "done": False,
                "file_path": fp,
                "language": entry["language"],
                "complexity_score": entry["complexity_score"],
                "complexity_class": entry["complexity_class"],
                "line_count": entry["line_count"],
                "original_source": entry["original_source"],
                "functions": entry["functions"],
                "classes": entry["classes"],
                "retry_count": entry["retry_count"],
            })

    # All files processed
    return json.dumps({"done": True, "stats": _stats(plan)})


# ------------------------------------------------------------------
# Tool 3: update_file_status
# ------------------------------------------------------------------

@mcp.tool()
def update_file_status(
    job_id: str,
    file_path: str,
    status: str,
    converted_source: str | None = None,
    validation_errors: str | None = None,
) -> str:
    """Update the status and optional converted output for a file.

    Args:
        job_id: Unique job identifier.
        file_path: Relative path of the file to update.
        status: New status — one of 'pending', 'in_progress', 'converted', 'failed', 'flagged'.
        converted_source: The converted code (set when status is 'converted' or after self-correction).
        validation_errors: JSON array of error objects from check_syntax / check_types.

    Returns:
        JSON with 'success' (bool), 'file_path', 'status', and current 'retry_count'.
    """
    plan = _require_plan(job_id)
    if plan is None:
        return json.dumps({"success": False, "error": f"No plan for job_id={job_id}"})

    entry = plan["files"].get(file_path)
    if entry is None:
        return json.dumps({"success": False, "error": f"File not in plan: {file_path}"})

    valid_statuses = {"pending", "in_progress", "converted", "failed", "flagged"}
    if status not in valid_statuses:
        return json.dumps({"success": False, "error": f"Invalid status '{status}'. Must be one of {valid_statuses}"})

    prev_status = entry["status"]
    entry["status"] = status

    errors: list[dict] = []
    if validation_errors:
        try:
            errors = json.loads(validation_errors)
        except json.JSONDecodeError:
            pass

    if converted_source is not None:
        # Record the attempt in retry history before updating
        if entry["converted_source"] is not None or entry["retry_count"] > 0:
            entry["retry_history"].append({
                "attempt": entry["retry_count"],
                "converted_source": entry["converted_source"],
                "validation_errors": entry["validation_errors"],
                "timestamp": _now(),
            })
            entry["retry_count"] += 1

        entry["converted_source"] = converted_source
        entry["validation_errors"] = errors

    if status in ("converted", "failed", "flagged"):
        entry["completed_at"] = _now()

    plan["updated_at"] = _now()
    _save_plan(job_id)
    return json.dumps({
        "success": True,
        "file_path": file_path,
        "status": status,
        "prev_status": prev_status,
        "retry_count": entry["retry_count"],
    })


# ------------------------------------------------------------------
# Tool 4: get_progress
# ------------------------------------------------------------------

@mcp.tool()
def get_progress(job_id: str) -> str:
    """Return a summary of migration progress for a job.

    Args:
        job_id: Unique job identifier.

    Returns:
        JSON with counts for each status, percent_complete, and complexity_distribution.
    """
    plan = _require_plan(job_id)
    if plan is None:
        return json.dumps({"error": f"No plan for job_id={job_id}"})

    st = _stats(plan)
    return json.dumps({
        "job_id": job_id,
        "source_language": plan["source_language"],
        "target_language": plan["target_language"],
        "created_at": plan["created_at"],
        "updated_at": plan["updated_at"],
        **st,
    })


# ------------------------------------------------------------------
# Tool 5: get_full_plan
# ------------------------------------------------------------------

@mcp.tool()
def get_full_plan(job_id: str, include_sources: bool = False) -> str:
    """Return the complete migration plan for a job.

    Args:
        job_id: Unique job identifier.
        include_sources: Whether to include original_source and converted_source
                         in each file entry (default False to keep payload small).

    Returns:
        JSON with full plan including all file entries and stats.
    """
    plan = _require_plan(job_id)
    if plan is None:
        return json.dumps({"error": f"No plan for job_id={job_id}"})

    files_out = []
    for fp in plan["topological_order"]:
        entry = plan["files"].get(fp)
        if entry is None:
            continue
        row = {k: v for k, v in entry.items()
               if k not in ("original_source", "converted_source", "retry_history")}
        if include_sources:
            row["original_source"] = entry["original_source"]
            row["converted_source"] = entry["converted_source"]
        files_out.append(row)

    return json.dumps({
        "job_id": job_id,
        "source_language": plan["source_language"],
        "target_language": plan["target_language"],
        "created_at": plan["created_at"],
        "updated_at": plan["updated_at"],
        "topological_order": plan["topological_order"],
        "stats": _stats(plan),
        "files": files_out,
    })


# ------------------------------------------------------------------
# Tool 6: get_file_details
# ------------------------------------------------------------------

@mcp.tool()
def get_file_details(job_id: str, file_path: str) -> str:
    """Return full details for a specific file, including source code and retry history.

    Args:
        job_id: Unique job identifier.
        file_path: Relative path of the file to query.

    Returns:
        JSON with original_source, converted_source, validation_errors,
        retry_history, and all metadata fields.
    """
    plan = _require_plan(job_id)
    if plan is None:
        return json.dumps({"error": f"No plan for job_id={job_id}"})

    entry = plan["files"].get(file_path)
    if entry is None:
        return json.dumps({"error": f"File not in plan: {file_path}"})

    return json.dumps({**entry,
                       "source_language": plan["source_language"],
                       "target_language": plan["target_language"]})


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
