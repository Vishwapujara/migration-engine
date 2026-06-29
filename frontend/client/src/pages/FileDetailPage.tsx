import { useParams, Link } from "react-router-dom";
import { useFileDetail } from "@/hooks/useFileDetail";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ArrowLeft, AlertTriangle, CheckCircle2, XCircle, Clock, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import type { FileStatus } from "@/types";

function statusIcon(s: FileStatus) {
  if (s === "converted")   return <CheckCircle2 className="h-4 w-4 text-green-500" />;
  if (s === "flagged")     return <AlertTriangle className="h-4 w-4 text-yellow-400" />;
  if (s === "failed")      return <XCircle className="h-4 w-4 text-destructive" />;
  if (s === "in_progress") return <Loader2 className="h-4 w-4 animate-spin text-primary" />;
  return <Clock className="h-4 w-4 text-muted-foreground" />;
}

function CodePanel({ title, code, language }: { title: string; code: string; language: string }) {
  return (
    <Card className="flex flex-1 flex-col overflow-hidden">
      <CardHeader className="border-b py-3">
        <CardTitle className="flex items-center gap-2 text-sm font-medium">
          {title}
          <Badge variant="outline" className="text-xs">{language}</Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="flex-1 overflow-auto p-0">
        <pre className="min-h-full bg-black/40 p-4 font-mono text-xs leading-relaxed text-foreground whitespace-pre-wrap break-words">
          {code || <span className="text-muted-foreground italic">No content</span>}
        </pre>
      </CardContent>
    </Card>
  );
}

export function FileDetailPage() {
  // react-router v7 wildcard: params["*"] holds the path after /files/
  const { jobId, "*": filePath } = useParams<{ jobId: string; "*": string }>();
  const { detail, loading, error } = useFileDetail(jobId!, filePath ?? "");

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24 text-muted-foreground">
        <Loader2 className="mr-2 h-5 w-5 animate-spin" /> Loading file…
      </div>
    );
  }

  if (error || !detail) {
    return (
      <div className="flex flex-col items-center gap-4 py-24 text-center text-muted-foreground">
        <p>{error ?? "File not found."}</p>
        <Button asChild variant="outline">
          <Link to={`/jobs/${jobId}/plan`}><ArrowLeft className="mr-2 h-4 w-4" />Back to plan</Link>
        </Button>
      </div>
    );
  }

  const hasConverted = !!detail.converted_source;
  const hasError = !!detail.error_message;

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <div>
        <Button asChild variant="ghost" size="sm" className="mb-2 -ml-2">
          <Link to={`/jobs/${jobId}/plan`}><ArrowLeft className="mr-1 h-4 w-4" />Plan</Link>
        </Button>
        <div className="flex flex-wrap items-center gap-3">
          {statusIcon(detail.status)}
          <h1 className="font-mono text-xl font-semibold">{filePath}</h1>
          <Badge variant="outline" className="capitalize">{detail.status}</Badge>
          {detail.retry_count > 0 && (
            <Badge variant="secondary">{detail.retry_count}× retry</Badge>
          )}
        </div>
        <p className="mt-1 text-sm text-muted-foreground">
          Complexity score: {detail.complexity_score.toFixed(1)} / 10
        </p>
      </div>

      {/* Error message */}
      {hasError && (
        <Card className="border-destructive/50 bg-destructive/10">
          <CardContent className="pt-6">
            <p className="font-mono text-xs text-destructive whitespace-pre-wrap">{detail.error_message}</p>
          </CardContent>
        </Card>
      )}

      {/* Side-by-side code panels */}
      <div
        className={cn(
          "flex gap-4",
          hasConverted ? "flex-row" : "flex-col"
        )}
        style={{ minHeight: "60vh" }}
      >
        <CodePanel
          title="Original source"
          code={""}
          language={detail.language ?? "source"}
        />
        {hasConverted && (
          <CodePanel
            title="Converted"
            code={detail.converted_source!}
            language="converted"
          />
        )}
      </div>

      {/* Retry history */}
      {detail.retry_history && detail.retry_history.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Retry history ({detail.retry_history.length})</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            {detail.retry_history.map((attempt, i) => (
              <div key={i} className="rounded-md border bg-black/30 p-3">
                <p className="mb-1 text-xs text-muted-foreground">Attempt {i + 1}</p>
                <pre className="font-mono text-xs text-foreground whitespace-pre-wrap">{attempt}</pre>
              </div>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
