import { useEffect, useRef } from "react";
import { io, Socket } from "socket.io-client";
import type { JobEvent } from "@/types";

let _socket: Socket | null = null;

function getSocket(): Socket {
  if (!_socket) {
    _socket = io({ path: "/socket.io", transports: ["websocket"] });
  }
  return _socket;
}

export function useSocket(jobId: string, onEvent: (e: JobEvent) => void) {
  const cbRef = useRef(onEvent);
  cbRef.current = onEvent;

  useEffect(() => {
    const socket = getSocket();

    socket.emit("subscribe", jobId);

    const handler = (event: JobEvent) => cbRef.current(event);
    socket.on("job_event", handler);

    return () => {
      socket.off("job_event", handler);
      socket.emit("unsubscribe", jobId);
    };
  }, [jobId]);
}
