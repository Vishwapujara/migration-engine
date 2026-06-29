import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { api } from "@/api/client";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { ArrowRight, RefreshCw, Clock, CheckCircle2, XCircle, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Job, JobStatus } from "@/types";

function StatusIcon({ status }: { status: JobStatus }) {
  if (status === "completed") return <CheckCircle2 className="h-4 w-4 text-green-500" />;
  if (status === "failed") return <XCircle className="h-4 w-4 text-destructive" />;
  if (status === "running") return <Loader2 className="h-4 w-4 animate-spin text-primary" />;
  return <Clock className="h-4 w-4 text-muted-foreground" />;
}

function statusVariant(s: JobStatus): "success" | "destructive" | "default" | "secondary" {
  if (s === "completed") return "success";
  if (s === "failed") return "destructive";
  if (s === "running") return "default";
  return "secondary";
}

export function JobsPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    try {
      const data = await api.listJobs();
      setJobs(data);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Migration jobs</h1>
          <p className="text-muted-foreground">All past and running migrations</p>
        </div>
        <Button variant="outline" size="sm" onClick={load} disabled={loading}>
          <RefreshCw className={cn("mr-2 h-4 w-4", loading && "animate-spin")} />
          Refresh
        </Button>
      </div>

      {loading && jobs.length === 0 ? (
        <div className="flex items-center justify-center py-24 text-muted-foreground">
          <Loader2 className="mr-2 h-5 w-5 animate-spin" /> Loading jobs…
        </div>
      ) : jobs.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-4 py-16 text-center">
            <p className="text-muted-foreground">No migrations yet.</p>
            <Button asChild>
              <Link to="/">Start your first migration</Link>
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="flex flex-col gap-3">
          {jobs.map((job) => {
            const pct = job.stats?.percent_complete ?? 0;
            return (
              <Card key={job.jobId} className="transition-colors hover:border-primary/50">
                <CardHeader className="pb-3">
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex flex-col gap-1">
                      <CardTitle className="flex items-center gap-2 text-base font-medium">
                        <StatusIcon status={job.status} />
                        <span className="font-mono text-sm text-muted-foreground">{job.jobId.slice(0, 8)}…</span>
                        <Badge variant={statusVariant(job.status)} className="capitalize">
                          {job.status}
                        </Badge>
                      </CardTitle>
                      <p className="text-sm text-muted-foreground">
                        {job.sourceLanguage} → {job.targetLanguage}
                        {job.repoUrl && (
                          <span className="ml-2 text-xs opacity-60">{job.repoUrl}</span>
                        )}
                      </p>
                    </div>
                    <Button asChild variant="ghost" size="sm">
                      <Link to={`/jobs/${job.jobId}`}>
                        View <ArrowRight className="ml-1 h-3 w-3" />
                      </Link>
                    </Button>
                  </div>
                </CardHeader>
                <CardContent className="pb-4">
                  <div className="flex flex-col gap-1">
                    <div className="flex justify-between text-xs text-muted-foreground">
                      <span>
                        {job.stats
                          ? `${job.stats.converted} / ${job.stats.total} files`
                          : "Waiting to start…"}
                      </span>
                      <span>{Math.round(pct)}%</span>
                    </div>
                    <Progress value={pct} className="h-1.5" />
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
