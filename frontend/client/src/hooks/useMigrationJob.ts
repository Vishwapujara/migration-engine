import { useState, useEffect, useCallback, useRef } from "react";
import { api } from "@/api/client";
import { useSocket } from "./useSocket";
import type { Job, MigrationPlan, JobEvent } from "@/types";

export interface MigrationJobState {
  job: Job | null;
  plan: MigrationPlan | null;
  loading: boolean;
  error: string | null;
  currentFile: string | null;
  activeNode: string | null;
  refresh: () => Promise<void>;
}

export function useMigrationJob(jobId: string): MigrationJobState {
  const [job, setJob] = useState<Job | null>(null);
  const [plan, setPlan] = useState<MigrationPlan | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [currentFile, setCurrentFile] = useState<string | null>(null);
  const [activeNode, setActiveNode] = useState<string | null>(null);

  // Track whether plan has ever loaded so we can retry
  const planLoaded = useRef(false);

  const refresh = useCallback(async () => {
    try {
      const [j, p] = await Promise.allSettled([
        api.getJob(jobId),
        api.getPlan(jobId),
      ]);
      if (j.status === "fulfilled") setJob(j.value);
      if (p.status === "fulfilled") {
        setPlan(p.value);
        planLoaded.current = true;
      }
    } catch (e) {
      setError(String(e));
    }
  }, [jobId]);

  // Initial load
  useEffect(() => {
    setLoading(true);
    refresh().finally(() => setLoading(false));
  }, [refresh]);

  // Live updates via Socket.IO
  useSocket(jobId, (event: JobEvent) => {
    if (event.type === "node_complete") {
      setActiveNode(event.node);

      // Keep current_file sticky — only update when node actually provides one
      if (event.current_file !== null && event.current_file !== undefined) {
        setCurrentFile(event.current_file);
      }

      // Update messages from socket event
      if (event.messages && event.messages.length > 0) {
        setJob((prev) =>
          prev
            ? { ...prev, messages: [...(prev.messages ?? []), ...event.messages] }
            : prev
        );
      }

      // Update progress stats
      if (event.progress) {
        setPlan((prev) =>
          prev
            ? { ...prev, stats: event.progress }
            : // Plan not loaded yet — create a shell so stats display
              {
                job_id: jobId,
                source_language: "python",
                target_language: "javascript",
                files: [],
                topological_order: [],
                stats: event.progress,
              }
        );
        // If plan never fully loaded, try fetching it now
        if (!planLoaded.current) {
          api.getPlan(jobId).then((p) => {
            setPlan(p);
            planLoaded.current = true;
          }).catch(() => { /* still not ready */ });
        }
      }
    } else if (event.type === "awaiting_approval") {
      setJob((prev) =>
        prev ? { ...prev, status: "awaiting_approval", plan_risk_summary: event.plan_risk_summary } : prev
      );
    } else if (event.type === "done") {
      setActiveNode(null);
      setJob((prev) => (prev ? { ...prev, status: "completed", stats: event.progress } : prev));
      refresh();
    } else if (event.type === "error") {
      setError(event.error);
      setJob((prev) => (prev ? { ...prev, status: "failed" } : prev));
    }
  });

  return { job, plan, loading, error, currentFile, activeNode, refresh };
}
