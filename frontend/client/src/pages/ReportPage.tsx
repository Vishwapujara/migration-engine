import { useState, useEffect } from "react";
import { useParams, Link } from "react-router-dom";
import { api } from "@/api/client";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { ArrowLeft, CheckCircle2, XCircle, AlertTriangle, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import type { MigrationReport } from "@/types";

interface ResultData {
  status: string;
  stats: MigrationReport["stats"];
  report: MigrationReport;
  output_repo_path?: string;
  pr_url?: string;
}

export function ReportPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const [data, setData] = useState<ResultData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getResult(jobId!)
      .then((r) => setData(r as ResultData))
      .catch((e) => {
        const msg =
          e?.response?.data?.detail ?? e?.message ?? "Failed to load report.";
        setError(msg);
      })
      .finally(() => setLoading(false));
  }, [jobId]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24 text-muted-foreground">
        <Loader2 className="mr-2 h-5 w-5 animate-spin" /> Loading report…
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="flex flex-col items-center gap-4 py-24 text-center text-muted-foreground">
        <p>{error ?? "Report unavailable."}</p>
        <Button asChild variant="outline">
          <Link to={`/jobs/${jobId}`}><ArrowLeft className="mr-2 h-4 w-4" />Back to dashboard</Link>
        </Button>
      </div>
    );
  }

  const { stats, report } = data;
  const pct = stats?.percent_complete ?? 0;

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <Button asChild variant="ghost" size="sm" className="mb-2 -ml-2">
            <Link to={`/jobs/${jobId}`}><ArrowLeft className="mr-1 h-4 w-4" />Dashboard</Link>
          </Button>
          <h1 className="text-3xl font-bold">Migration report</h1>
          <p className="text-muted-foreground">
            {report?.source_language} → {report?.target_language} &middot;{" "}
            <span className="font-mono text-xs">{jobId}</span>
          </p>
        </div>
        <Badge
          variant={pct === 100 ? "success" : pct > 0 ? "default" : "destructive"}
          className="text-sm px-3 py-1"
        >
          {Math.round(pct)}% complete
        </Badge>
      </div>

      {/* Overall progress */}
      <Card>
        <CardContent className="pt-6">
          <Progress value={pct} className="h-3" />
        </CardContent>
      </Card>

      {/* Stats */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          { label: "Total",     value: stats.total,     cls: "text-foreground" },
          { label: "Converted", value: stats.converted, cls: "text-green-500" },
          { label: "Flagged",   value: stats.flagged,   cls: "text-yellow-400" },
          { label: "Failed",    value: stats.failed,    cls: "text-destructive" },
        ].map(({ label, value, cls }) => (
          <Card key={label}>
            <CardContent className="flex flex-col items-center py-5">
              <span className={cn("text-4xl font-bold", cls)}>{value}</span>
              <span className="mt-1 text-xs text-muted-foreground">{label}</span>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Converted files */}
        <Card className="lg:col-span-1">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <CheckCircle2 className="h-4 w-4 text-green-500" />
              Converted ({report?.converted_files?.length ?? 0})
            </CardTitle>
          </CardHeader>
          <CardContent className="max-h-64 overflow-y-auto">
            {report?.converted_files?.length ? (
              <ul className="flex flex-col gap-1">
                {report.converted_files.map((f) => (
                  <li key={f}>
                    <Link
                      to={`/jobs/${jobId}/files/${f}`}
                      className="block rounded px-2 py-1 font-mono text-xs text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
                    >
                      {f}
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">None</p>
            )}
          </CardContent>
        </Card>

        {/* Flagged files */}
        <Card className="lg:col-span-1">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <AlertTriangle className="h-4 w-4 text-yellow-400" />
              Flagged ({report?.flagged_files?.length ?? 0})
            </CardTitle>
          </CardHeader>
          <CardContent className="max-h-64 overflow-y-auto">
            {report?.flagged_files?.length ? (
              <ul className="flex flex-col gap-1">
                {report.flagged_files.map((f) => (
                  <li key={f}>
                    <Link
                      to={`/jobs/${jobId}/files/${f}`}
                      className="block rounded px-2 py-1 font-mono text-xs text-yellow-400 hover:bg-accent transition-colors"
                    >
                      {f}
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">None</p>
            )}
          </CardContent>
        </Card>

        {/* Failed files */}
        <Card className="lg:col-span-1">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <XCircle className="h-4 w-4 text-destructive" />
              Failed ({report?.failed_files?.length ?? 0})
            </CardTitle>
          </CardHeader>
          <CardContent className="max-h-64 overflow-y-auto">
            {report?.failed_files?.length ? (
              <ul className="flex flex-col gap-1">
                {report.failed_files.map((f) => (
                  <li key={f}>
                    <Link
                      to={`/jobs/${jobId}/files/${f}`}
                      className="block rounded px-2 py-1 font-mono text-xs text-destructive hover:bg-accent transition-colors"
                    >
                      {f}
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">None</p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Output / PR info */}
      {(data.output_repo_path || data.pr_url) && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Output</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-2 text-sm">
            {data.output_repo_path && (
              <p>
                <span className="text-muted-foreground">Output path: </span>
                <code className="font-mono text-xs">{data.output_repo_path}</code>
              </p>
            )}
            {data.pr_url && (
              <p>
                <span className="text-muted-foreground">Pull request: </span>
                <a
                  href={data.pr_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-primary underline-offset-2 hover:underline"
                >
                  {data.pr_url}
                </a>
              </p>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
