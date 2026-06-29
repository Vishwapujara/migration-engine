"""WebSocket connection manager and per-job event queues."""
from __future__ import annotations
import asyncio
from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        # job_id -> list of active WebSocket connections
        self._connections: dict[str, list[WebSocket]] = {}
        # job_id -> asyncio.Queue for streaming graph events
        self._queues: dict[str, asyncio.Queue] = {}

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def connect(self, job_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.setdefault(job_id, []).append(ws)

    def disconnect(self, job_id: str, ws: WebSocket) -> None:
        conns = self._connections.get(job_id, [])
        if ws in conns:
            conns.remove(ws)

    # ------------------------------------------------------------------
    # Queue management (used by background graph task)
    # ------------------------------------------------------------------

    def create_queue(self, job_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._queues[job_id] = q
        return q

    def get_queue(self, job_id: str) -> asyncio.Queue | None:
        return self._queues.get(job_id)

    def remove_queue(self, job_id: str) -> None:
        self._queues.pop(job_id, None)

    # ------------------------------------------------------------------
    # Broadcasting
    # ------------------------------------------------------------------

    async def broadcast(self, job_id: str, payload: dict) -> None:
        dead: list[WebSocket] = []
        for ws in self._connections.get(job_id, []):
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(job_id, ws)

    async def send_personal(self, ws: WebSocket, payload: dict) -> None:
        try:
            await ws.send_json(payload)
        except Exception:
            pass


manager = ConnectionManager()
