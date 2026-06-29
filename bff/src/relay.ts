/**
 * WebSocket relay: connects to FastAPI WS for a given job and forwards
 * events to all Socket.IO clients subscribed to that job room.
 */
import { Server as IOServer } from "socket.io";
import WebSocket from "ws";
import { config } from "./config";

const _relays = new Map<string, WebSocket>();

export function attachRelay(io: IOServer): void {
  io.on("connection", (socket) => {
    socket.on("subscribe", (jobId: string) => {
      socket.join(jobId);

      // Only open one upstream WS per job
      if (!_relays.has(jobId)) {
        const wsUrl = config.fastApiUrl.replace(/^http/, "ws") + `/ws/jobs/${jobId}`;
        const ws = new WebSocket(wsUrl);

        ws.on("message", (raw) => {
          try {
            const payload = JSON.parse(raw.toString());
            io.to(jobId).emit("job_event", payload);
          } catch {
            // non-JSON message from FastAPI — ignore
          }
        });

        ws.on("close", () => {
          _relays.delete(jobId);
          io.to(jobId).emit("job_event", { type: "ws_closed" });
        });

        ws.on("error", (err) => {
          console.error(`[relay] WS error for ${jobId}:`, err.message);
          _relays.delete(jobId);
        });

        _relays.set(jobId, ws);
      }
    });

    socket.on("unsubscribe", (jobId: string) => {
      socket.leave(jobId);
      // Close upstream WS when no clients remain in that room
      const room = io.sockets.adapter.rooms.get(jobId);
      if (!room || room.size === 0) {
        const ws = _relays.get(jobId);
        if (ws) {
          ws.close();
          _relays.delete(jobId);
        }
      }
    });
  });
}
