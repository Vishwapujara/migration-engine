import { useState, useEffect } from "react";
import { api } from "@/api/client";
import type { FileDetail } from "@/types";

export function useFileDetail(jobId: string, filePath: string) {
  const [detail, setDetail] = useState<FileDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!jobId || !filePath) return;
    setLoading(true);
    api
      .getFileDetail(jobId, filePath)
      .then(setDetail)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [jobId, filePath]);

  return { detail, loading, error };
}
