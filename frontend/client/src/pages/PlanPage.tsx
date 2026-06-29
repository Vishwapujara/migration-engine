import { useParams, Link } from "react-router-dom";
import { useMigrationJob } from "@/hooks/useMigrationJob";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Button } from "@/components/ui/button";
import {
  CheckCircle2, XCircle, AlertTriangle, Clock, Loader2, ArrowLeft, ArrowRight,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { FileStatus } from "@/types";

function fileStatusIcon(s: FileStatus) {
  if (s === "converted") return <CheckCircle2 className="h-4 w-4 text-green-500" />;
  if (s === "flagged")   return <AlertTriangle className="h-4 w-4 text-yellow-400" />;
  if (s === "failed")    return <XCircle className="h-4 w-4 text-destructive" />;
  if (s === "in_progress") return <Loader2 className="h-4 w-4 animate-spin text-primary" />;
  return <Clock className="h-4 w-4 text-muted-foreground" />;
}

function fileStatusVariant(s: FileStatus): "success" | "warning" | "destructive" | "default" | "secondary" {
  if (s === "converted")   return "success";
  if (s === "flagged")     return "warning";
  if (s === "failed")      return "destructive";
  if (s === "in_progress") return "default";
  return "secondary";
}

function complexityBar(score: number) {
  const pct = (score / 10) * 100;
  const color =
    score < 3 ? "bg-green-500" : score < 6 ? "bg-yellow-400" : "bg-red-500";
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-20 overflow-hidden rounded-full bg-secondary">
        <div className={cn("h-full rounded-full", color)} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-muted-foreground">{score.toFixed(1)}</span>
    </div>
  );
}

export function PlanPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const { job, plan, loading, error, currentFile } = useMigrationJob(jobId!);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24 text-muted-foreground">
        <Loader2 className="mr-2 h-5 w-5 animate-spin" /> Loading plan…
      </div>
    );
  }

  if (error || !plan) {
    return (
      <div className="flex flex-col items-center gap-4 py-24 text-center text-muted-foreground">
        <p>{error ?? "Plan not available yet — migration may still be initialising."}</p>
        <Button asChild variant="outline"><Link to={`/jobs/${jobId}`}><ArrowLeft className="mr-2 h-4 w-4" />Back to dashboard</Link></Button>
      </div>
    );
  }

  const { stats, files, topological_order = [] } = plan;
  // files is already in topo order from get_full_plan; topological_order is for cross-referencing only
  const ordered = topological_order.length
    ? topological_order.map((fp) => files.find((f) => f.file_path === fp)).filter(Boolean)
    : files;

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <Button asChild variant="ghost" size="sm" className="mb-2 -ml-2">
            <Link to={`/jobs/${jobId}`}><ArrowLeft className="mr-1 h-4 w-4" />Dashboard</Link>
          </Button>
          <h1 className="text-3xl font-bold">Migration plan</h1>
          <p className="text-muted-foreground">
            {job?.sourceLanguage} → {job?.targetLanguage} &middot; {stats.total} files
          </p>
        </div>
        <Button asChild variant="outline" size="sm">
          <Link to={`/jobs/${jobId}/report`}>View report <ArrowRight className="ml-1 h-4 w-4" /></Link>
        </Button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
        {[
          { label: "Total",       value: stats.total,       color: "text-foreground" },
          { label: "Converted",   value: stats.converted,   color: "text-green-500" },
          { label: "Flagged",     value: stats.flagged,     color: "text-yellow-400" },
          { label: "Failed",      value: stats.failed,      color: "text-destructive" },
          { label: "Pending",     value: stats.pending + stats.in_progress, color: "text-muted-foreground" },
        ].map(({ label, value, color }) => (
          <Card key={label}>
            <CardContent className="flex flex-col items-center py-4">
              <span className={cn("text-3xl font-bold", color)}>{value}</span>
              <span className="text-xs text-muted-foreground">{label}</span>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Progress bar */}
      <div className="flex flex-col gap-1">
        <div className="flex justify-between text-sm text-muted-foreground">
          <span>Overall progress</span>
          <span>{Math.round(stats.percent_complete)}%</span>
        </div>
        <Progress value={stats.percent_complete} className="h-2" />
      </div>

      {/* File table */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Files — topological order</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <div className="divide-y">
            {(ordered as NonNullable<(typeof ordered)[number]>[]).map((file) => {
              const isActive = file.file_path === currentFile;
              return (
                <Link
                  key={file.file_path}
                  to={`/jobs/${jobId}/files/${file.file_path}`}
                  className={cn(
                    "flex items-center justify-between gap-4 px-6 py-3 text-sm transition-colors hover:bg-accent",
                    isActive && "bg-primary/10"
                  )}
                >
                  <div className="flex items-center gap-3 overflow-hidden">
                    {fileStatusIcon(file.status)}
                    <span className="truncate font-mono text-xs">{file.file_path}</span>
                    {isActive && <Badge variant="default" className="shrink-0 text-[10px]">active</Badge>}
                    {file.retry_count > 0 && (
                      <Badge variant="secondary" className="shrink-0 text-[10px]">
                        {file.retry_count}× retry
                      </Badge>
                    )}
                  </div>
                  <div className="flex shrink-0 items-center gap-3">
                    {complexityBar(file.complexity_score)}
                    <Badge variant={fileStatusVariant(file.status)} className="capitalize text-[10px]">
                      {file.status}
                    </Badge>
                    <ArrowRight className="h-3 w-3 text-muted-foreground" />
                  </div>
                </Link>
              );
            })}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
