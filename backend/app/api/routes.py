"""FastAPI routes — all REST + WebSocket endpoints."""
from __future__ import annotations
import asyncio
import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from langgraph.types import Command
from pydantic import BaseModel

from app.config import settings, SUPPORTED_MIGRATIONS
from app.graph.pipeline import graph
from app.graph.state import initial_state
from app.mcp_servers.plan_manager_server import get_full_plan, get_progress, get_file_details
from app.api.websockets import manager

router = APIRouter()

# ── In-memory job store ───────────────────────────────────────────────
_jobs: dict[str, dict] = {}
_jobs_lock = asyncio.Lock()


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_migration_pair(src: str, tgt: str) -> None:
    if (src, tgt) not in SUPPORTED_MIGRATIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Migration pair ({src} -> {tgt}) is not supported. "
                   f"Supported: {list(SUPPORTED_MIGRATIONS)}",
        )


async def _update_job(job_id: str, **fields) -> None:
    async with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id].update(fields)
            _jobs[job_id]["updated_at"] = _now()


def _make_thread_worker(stream_iter, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop):
    """Return a callable that drains a LangGraph stream into an asyncio queue."""
    def _worker():
        try:
            for chunk in stream_iter:
                if "__interrupt__" in chunk:
                    asyncio.run_coroutine_threadsafe(
                        queue.put(("interrupted", chunk["__interrupt__"])), loop
                    ).result()
                    return  # stream ends after interrupt
                asyncio.run_coroutine_threadsafe(
                    queue.put(("chunk", chunk)), loop
                ).result()
            asyncio.run_coroutine_threadsafe(
                queue.put(("done", None)), loop
            ).result()
        except Exception as exc:
            asyncio.run_coroutine_threadsafe(
                queue.put(("error", str(exc))), loop
            ).result()
    return _worker


async def _drain_graph_stream(
    job_id: str,
    queue: asyncio.Queue,
    thread: threading.Thread,
) -> None:
    """Pull events from the thread queue and update job state / broadcast."""
    try:
        while True:
            event_type, data = await queue.get()

            if event_type == "chunk":
                for node_name, node_output in data.items():
                    messages = node_output.get("messages", [])
                    if messages:
                        async with _jobs_lock:
                            if job_id in _jobs:
                                _jobs[job_id]["messages"] = _jobs[job_id].get("messages", []) + messages
                                _jobs[job_id]["updated_at"] = _now()

                    try:
                        progress = json.loads(get_progress(job_id))
                    except Exception:
                        progress = {}

                    await manager.broadcast(job_id, {
                        "type": "node_complete",
                        "node": node_name,
                        "messages": messages,
                        "progress": progress,
                        "current_file": node_output.get("current_file"),
                        "self_correction_attempts": node_output.get("self_correction_attempts"),
                    })

            elif event_type == "interrupted":
                # Graph paused at await_approval node — extract risk summary
                interrupts = data  # tuple of Interrupt objects
                risk_summary: dict = {}
                if interrupts:
                    val = getattr(interrupts[0], "value", {}) if interrupts else {}
                    if isinstance(val, dict):
                        risk_summary = val.get("plan_risk_summary", val)

                await _update_job(
                    job_id,
                    status="awaiting_approval",
                    plan_risk_summary=risk_summary,
                )
                await manager.broadcast(job_id, {
                    "type": "awaiting_approval",
                    "plan_risk_summary": risk_summary,
                })
                break

            elif event_type == "done":
                try:
                    progress = json.loads(get_progress(job_id))
                except Exception:
                    progress = {}

                await _update_job(
                    job_id,
                    status="completed",
                    stats=progress,
                    output_repo_path=str(settings.workspace_dir / job_id / "output"),
                )
                await manager.broadcast(job_id, {"type": "done", "progress": progress})
                break

            elif event_type == "error":
                await _update_job(job_id, status="failed", error=str(data))
                await manager.broadcast(job_id, {"type": "error", "error": str(data)})
                break

    except asyncio.CancelledError:
        # Server shutting down while a job is in-flight — exit without raising.
        pass
    finally:
        manager.remove_queue(job_id)
        thread.join(timeout=5)


async def _run_graph(
    job_id: str,
    state: dict,
    loop: asyncio.AbstractEventLoop,
) -> None:
    """Run graph.stream() from the initial state in a daemon thread."""
    queue = manager.create_queue(job_id)
    await _update_job(job_id, status="running")

    config = {"configurable": {"thread_id": job_id}}
    stream = graph.stream(state, config=config, stream_mode="updates")
    thread = threading.Thread(
        target=_make_thread_worker(stream, queue, loop),
        daemon=True,
        name=f"graph-{job_id}",
    )
    thread.start()
    await _drain_graph_stream(job_id, queue, thread)


async def _run_graph_resume(
    job_id: str,
    loop: asyncio.AbstractEventLoop,
) -> None:
    """Resume a paused graph after human approval."""
    queue = manager.create_queue(job_id)
    await _update_job(job_id, status="running")

    config = {"configurable": {"thread_id": job_id}}
    stream = graph.stream(Command(resume=True), config=config, stream_mode="updates")
    thread = threading.Thread(
        target=_make_thread_worker(stream, queue, loop),
        daemon=True,
        name=f"graph-resume-{job_id}",
    )
    thread.start()
    await _drain_graph_stream(job_id, queue, thread)


def _initial_job(job_id: str, source_language: str, target_language: str,
                 repo_url: str | None = None, zip_path: str | None = None) -> dict:
    return {
        "job_id": job_id,
        "status": "pending",
        "source_language": source_language,
        "target_language": target_language,
        "repo_url": repo_url,
        "zip_path": zip_path,
        "messages": [],
        "stats": None,
        "plan_risk_summary": None,
        "error": None,
        "output_repo_path": None,
        "pr_url": None,
        "created_at": _now(),
        "updated_at": _now(),
    }


# ------------------------------------------------------------------
# POST /api/migrate  (GitHub URL)
# ------------------------------------------------------------------

class MigrateRequest(BaseModel):
    repo_url: str
    source_language: str
    target_language: str


@router.post("/api/migrate")
async def start_migration(body: MigrateRequest, background_tasks: BackgroundTasks):
    _validate_migration_pair(body.source_language, body.target_language)

    job_id = str(uuid.uuid4())
    state = initial_state(
        job_id=job_id,
        source_language=body.source_language,
        target_language=body.target_language,
        repo_url=body.repo_url,
    )

    async with _jobs_lock:
        _jobs[job_id] = _initial_job(
            job_id, body.source_language, body.target_language, repo_url=body.repo_url
        )

    loop = asyncio.get_event_loop()
    background_tasks.add_task(_run_graph, job_id, state, loop)

    return {"job_id": job_id, "status": "pending"}


# ------------------------------------------------------------------
# POST /api/migrate/upload  (ZIP file)
# ------------------------------------------------------------------

@router.post("/api/migrate/upload")
async def upload_and_migrate(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    source_language: str = Form(...),
    target_language: str = Form(...),
):
    _validate_migration_pair(source_language, target_language)

    if not file.filename or not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip files are accepted.")

    job_id = str(uuid.uuid4())
    upload_dir = settings.workspace_dir / job_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    zip_path = upload_dir / "upload.zip"

    content = await file.read()
    zip_path.write_bytes(content)

    state = initial_state(
        job_id=job_id,
        source_language=source_language,
        target_language=target_language,
        zip_path=str(zip_path),
    )

    async with _jobs_lock:
        _jobs[job_id] = _initial_job(
            job_id, source_language, target_language, zip_path=str(zip_path)
        )

    loop = asyncio.get_event_loop()
    background_tasks.add_task(_run_graph, job_id, state, loop)

    return {"job_id": job_id, "status": "pending"}


# ------------------------------------------------------------------
# POST /api/jobs/{job_id}/approve
# ------------------------------------------------------------------

@router.post("/api/jobs/{job_id}/approve")
async def approve_job(job_id: str, background_tasks: BackgroundTasks):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")
    if job["status"] != "awaiting_approval":
        raise HTTPException(
            status_code=400,
            detail=f"Job is not awaiting approval (current status: {job['status']}).",
        )

    loop = asyncio.get_event_loop()
    background_tasks.add_task(_run_graph_resume, job_id, loop)

    return {"job_id": job_id, "status": "running"}


# ------------------------------------------------------------------
# GET /api/jobs/{job_id}
# ------------------------------------------------------------------

@router.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")
    return job


# ------------------------------------------------------------------
# GET /api/jobs/{job_id}/plan
# ------------------------------------------------------------------

@router.get("/api/jobs/{job_id}/plan")
async def get_job_plan(job_id: str):
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")
    try:
        plan = json.loads(get_full_plan(job_id))
        if "error" in plan:
            raise HTTPException(status_code=404, detail=plan["error"])
        return plan
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ------------------------------------------------------------------
# GET /api/jobs/{job_id}/result
# ------------------------------------------------------------------

@router.get("/api/jobs/{job_id}/result")
async def get_job_result(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")
    if job["status"] not in ("completed", "failed"):
        raise HTTPException(status_code=202, detail="Job is still running.")

    out_dir = Path(job.get("output_repo_path") or "")
    report_path = out_dir / "migration_report.json"
    report = json.loads(report_path.read_text()) if report_path.exists() else {}

    return {
        "job_id": job_id,
        "status": job["status"],
        "stats": job.get("stats"),
        "report": report,
        "output_repo_path": job.get("output_repo_path"),
        "pr_url": job.get("pr_url"),
        "error": job.get("error"),
    }


# ------------------------------------------------------------------
# GET /api/jobs/{job_id}/files/{file_path}
# ------------------------------------------------------------------

@router.get("/api/jobs/{job_id}/files/{file_path:path}")
async def get_file_detail(job_id: str, file_path: str):
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")
    try:
        detail = json.loads(get_file_details(job_id, file_path))
        if "error" in detail:
            raise HTTPException(status_code=404, detail=detail["error"])
        return detail
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ------------------------------------------------------------------
# WebSocket /ws/jobs/{job_id}
# ------------------------------------------------------------------

@router.websocket("/ws/jobs/{job_id}")
async def websocket_job(job_id: str, ws: WebSocket):
    await manager.connect(job_id, ws)
    try:
        job = _jobs.get(job_id)
        if job:
            await manager.send_personal(ws, {"type": "connected", "job": job})

        while True:
            try:
                await asyncio.wait_for(ws.receive_text(), timeout=30.0)
            except asyncio.TimeoutError:
                await manager.send_personal(ws, {"type": "ping"})
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(job_id, ws)
