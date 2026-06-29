# Checkpoint Design: Surviving the Approval Pause

## The Problem

The migration pipeline has a human-in-the-loop gate between the analysis phase and the conversion phase:

```
Ingest → Profile → Classify → Rank → [PAUSE: wait for human approval] → Convert → Done
```

When the pipeline hits that pause, it stops and waits — potentially for minutes or hours — while the user reviews the risk table in the UI and decides whether to approve.

**The failure mode:** If the FastAPI server restarts while the pipeline is paused (crash, redeploy, dev server restart), all in-memory workflow state disappears. When the user clicks "Approve & Start," the backend has nothing to resume. The user has to resubmit the entire job and sit through the full analysis phase again.

This is especially painful because:

- Analysis (ingest → rank) can take 30–120 seconds on a real repo.
- The user has already reviewed the risk table and made a decision — losing that feels broken.
- In development, restarting the server between testing approval flows is common.

---

## Why It Happens

LangGraph's `interrupt()` function works by saving the paused workflow's state to a **checkpointer**. If no checkpointer is configured, the state lives only in RAM.

```
Process A (running graph)
│
├─ Ingest ──────────────────────── saved to: RAM
├─ Profile ─────────────────────── saved to: RAM
├─ Classify ────────────────────── saved to: RAM
├─ Rank ────────────────────────── saved to: RAM
│
interrupt() ← graph pauses here, state is in RAM
│
│ ← server crashes
│
▼
[RAM cleared. State gone.]
```

When `Command(resume=True)` arrives from the approve endpoint, LangGraph tries to load the checkpoint for that `thread_id`. With no checkpointer, there is nothing to load.

---

## The Solution: SQLite Checkpointer

LangGraph supports pluggable checkpointers. The SQLite checkpointer (`langgraph-checkpoint-sqlite`) saves a snapshot of the workflow state to a local `.sqlite` file after every node completes — including at the interrupt point.

```
Process A (running graph)
│
├─ Ingest ──────────────────────── saved to: workspace/checkpoints.sqlite
├─ Profile ─────────────────────── saved to: workspace/checkpoints.sqlite
├─ Classify ────────────────────── saved to: workspace/checkpoints.sqlite
├─ Rank ────────────────────────── saved to: workspace/checkpoints.sqlite
│
interrupt() ← graph pauses, checkpoint saved to disk
│
│ ← server crashes
│
Process B (server restarts)
│
user clicks Approve
│
Command(resume=True) → LangGraph reads checkpoint from disk
│
├─ await_approval (resumes) ────── picks up exactly where it left off
├─ pick_next → generate → ... ─── continues normally
```

The `.sqlite` file is a single file on disk. No separate database server is needed. SQLite is built into Python.

---

## Implementation

### Package

```
langgraph-checkpoint-sqlite>=3.0.0
```

### Code change in `backend/app/graph/pipeline.py`

**Before:**
```python
from langgraph.checkpoint.memory import MemorySaver
...
return g.compile(checkpointer=MemorySaver())
```

**After:**
```python
import sqlite3
from pathlib import Path
from langgraph.checkpoint.sqlite import SqliteSaver

db_path = Path(__file__).parent.parent.parent / "workspace" / "checkpoints.sqlite"
db_path.parent.mkdir(parents=True, exist_ok=True)
conn = sqlite3.connect(str(db_path), check_same_thread=False)
return g.compile(checkpointer=SqliteSaver(conn))
```

`check_same_thread=False` is required because the graph runs in a daemon thread (not the main FastAPI thread). `SqliteSaver` serialises its own writes internally, so this is safe.

### Thread ID

Every graph invocation must include a `thread_id` in the config. LangGraph uses this to scope checkpoints per workflow run — different migrations don't collide.

```python
# Initial run
config = {"configurable": {"thread_id": job_id}}
graph.stream(initial_state, config=config, stream_mode="updates")

# Resume after approval
graph.stream(Command(resume=True), config=config, stream_mode="updates")
```

`job_id` (a UUID) is already used as the `thread_id` in this project.

### `.gitignore`

The checkpoint database should not be committed:

```
workspace/
*.sqlite
```

---

## Tradeoffs

| | MemorySaver (old) | SqliteSaver (new) |
|---|---|---|
| Survives server restart | No | Yes |
| Setup complexity | None | 3 lines |
| External dependency | None | `langgraph-checkpoint-sqlite` |
| Storage | RAM | `workspace/checkpoints.sqlite` |
| Multi-process safe | No | No (single process only) |
| Production-ready | No | Good enough for single-instance |

### When SQLite is not enough

SQLite works for a single server process. If you ever run multiple FastAPI instances behind a load balancer, they won't share the same `.sqlite` file — a resume request routed to a different instance will fail to find the checkpoint.

For multi-instance deployments, swap the checkpointer for the PostgreSQL version:

```python
from langgraph.checkpoint.postgres import PostgresSaver
checkpointer = PostgresSaver.from_conn_string(os.environ["DATABASE_URL"])
```

The rest of the code stays identical. This is the point of the checkpointer abstraction — the swap is one line.

---

## Other Benefits

**Time-travel debugging.** Every state snapshot is stored. You can inspect what the workflow's state was at any node, or replay a workflow from any checkpoint.

**Long-duration pauses are safe.** A user could close their browser, come back the next day, and click approve. The workflow resumes correctly.

**Visible in SQLite tooling.** You can open `workspace/checkpoints.sqlite` with any SQLite browser (DB Browser for SQLite, TablePlus, etc.) and inspect raw checkpoint data — useful for debugging stuck workflows.

---

## File Location

```
workspace/checkpoints.sqlite   ← created automatically on first run
```

The `workspace/` directory is already volume-mounted in Docker and already in `.gitignore`.
