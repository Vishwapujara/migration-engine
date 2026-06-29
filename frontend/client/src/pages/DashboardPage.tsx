import { useParams, Link } from "react-router-dom";
import { useMigrationJob } from "@/hooks/useMigrationJob";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Button } from "@/components/ui/button";
import {
  CheckCircle2, XCircle, Loader2, Clock, ArrowRight, FileCode2,
  RefreshCw, Terminal,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { JobStatus } from "@/types";

const STATUS_COLOR: Record<JobStatus, string> = {
  pending:            "text-muted-foreground",
  running:            "text-primary",
  awaiting_approval:  "text-yellow-500",
  completed:          "text-green-500",
  failed:             "text-destructive",
};

const GRAPH_NODES = [
  "ingest", "profile", "classify", "warn", "rank",
  "await_approval",
  "pick_next", "gather_context", "generate", "validate",
  "self_correct", "commit", "flag", "done",
];

function NodePill({ name, active }: { name: string; active: boolean }) {
  return (
    <div
      className={cn(
        "rounded-full border px-3 py-1 text-xs transition-all",
        active
          ? "border-primary bg-primary/20 text-primary font-medium"
          : "border-border text-muted-foreground"
      )}
    >
      {name}
    </div>
  );
}

function StatusBadge({ status }: { status: JobStatus }) {
  const icons: Record<JobStatus, React.ReactNode> = {
    pending:            <Clock className="h-3 w-3" />,
    running:            <Loader2 className="h-3 w-3 animate-spin" />,
    awaiting_approval:  <Clock className="h-3 w-3" />,
    completed:          <CheckCircle2 className="h-3 w-3" />,
    failed:             <XCircle className="h-3 w-3" />,
  };
  return (
    <span className={cn("flex items-center gap-1 font-medium capitalize", STATUS_COLOR[status])}>
      {icons[status]} {status}
    </span>
  );
}

export function DashboardPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const { job, plan, loading, error, currentFile, activeNode, refresh } = useMigrationJob(jobId!);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24 text-muted-foreground">
        <Loader2 className="mr-2 h-5 w-5 animate-spin" /> Loading…
      </div>
    );
  }

  if (error || !job) {
    return (
      <div className="py-24 text-center text-muted-foreground">
        {error ?? "Job not found."}
      </div>
    );
  }

  const stats = plan?.stats ?? job.stats;
  const pct = stats?.percent_complete ?? 0;

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="font-mono text-xs text-muted-foreground">{jobId}</p>
          <h1 className="text-3xl font-bold">
            {job.sourceLanguage} → {job.targetLanguage}
          </h1>
          <StatusBadge status={job.status} />
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={refresh}>
            <RefreshCw className="mr-1 h-4 w-4" /> Refresh
          </Button>
          <Button asChild size="sm">
            <Link to={`/jobs/${jobId}/plan`}>
              View plan <ArrowRight className="ml-1 h-4 w-4" />
            </Link>
          </Button>
          {job.status === "awaiting_approval" && (
            <Button asChild variant="default" size="sm">
              <Link to={`/jobs/${jobId}/review`}>Review plan →</Link>
            </Button>
          )}
          {job.status === "completed" && (
            <Button asChild variant="secondary" size="sm">
              <Link to={`/jobs/${jobId}/report`}>Report</Link>
            </Button>
          )}
        </div>
      </div>

      {/* Progress */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex flex-col gap-2">
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">
                {stats
                  ? `${stats.converted} converted · ${stats.flagged} flagged · ${stats.failed} failed`
                  : "Waiting to start…"}
              </span>
              <span className="font-medium">{Math.round(pct)}%</span>
            </div>
            <Progress value={pct} className="h-2.5" />
          </div>
        </CardContent>
      </Card>

      {/* Stats grid */}
      {stats && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[
            { label: "Total",     value: stats.total,       cls: "text-foreground" },
            { label: "Converted", value: stats.converted,   cls: "text-green-500" },
            { label: "Flagged",   value: stats.flagged,     cls: "text-yellow-400" },
            { label: "Failed",    value: stats.failed,      cls: "text-destructive" },
          ].map(({ label, value, cls }) => (
            <Card key={label}>
              <CardContent className="flex flex-col items-center py-4">
                <span className={cn("text-3xl font-bold", cls)}>{value}</span>
                <span className="text-xs text-muted-foreground">{label}</span>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Pipeline nodes */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Pipeline</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            {GRAPH_NODES.map((n) => (
              <NodePill key={n} name={n} active={n === activeNode} />
            ))}
          </CardContent>
        </Card>

        {/* Current file */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Current file</CardTitle>
          </CardHeader>
          <CardContent>
            {currentFile ? (
              <Link
                to={`/jobs/${jobId}/files/${currentFile}`}
                className="flex items-center gap-2 rounded-md border border-primary/40 bg-primary/10 px-4 py-3 text-sm font-medium text-primary hover:bg-primary/20 transition-colors"
              >
                <FileCode2 className="h-4 w-4 shrink-0" />
                <span className="truncate font-mono text-xs">{currentFile}</span>
                <ArrowRight className="ml-auto h-4 w-4 shrink-0" />
              </Link>
            ) : (
              <p className="text-sm text-muted-foreground">
                {job.status === "running" ? "Waiting for next file…" : "—"}
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Message log */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Terminal className="h-4 w-4" /> Log
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="max-h-72 overflow-y-auto rounded-md bg-black/40 p-4 font-mono text-xs">
            {job.messages.length === 0 ? (
              <p className="text-muted-foreground">No messages yet.</p>
            ) : (
              [...job.messages].reverse().map((msg, i) => (
                <p key={i} className={cn(
                  "py-0.5",
                  msg.startsWith("[ERROR]") || msg.startsWith("[FAIL]") ? "text-red-400"
                  : msg.startsWith("[WARN]") ? "text-yellow-400"
                  : msg.startsWith("[OK]") || msg.startsWith("[DONE]") ? "text-green-400"
                  : "text-muted-foreground"
                )}>
                  {msg}
                </p>
              ))
            )}
          </div>
        </CardContent>
      </Card>

      {/* Error banner */}
      {job.error && (
        <Card className="border-destructive/50 bg-destructive/10">
          <CardContent className="pt-6">
            <p className="text-sm text-destructive">{job.error}</p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
