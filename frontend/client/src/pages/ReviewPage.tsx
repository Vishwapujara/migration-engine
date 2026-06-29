import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api } from "@/api/client";
import { useSocket } from "@/hooks/useSocket";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Loader2, CheckCircle2, AlertTriangle, ShieldAlert, ArrowRight,
  FileCode2, GitBranch, Zap, Flag, Layers, RefreshCw, Info, XCircle,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { Job, JobEvent, PlanRiskSummary, RiskItem } from "@/types";

type Phase = "analyzing" | "awaiting" | "approving" | "error";

// ── Sub-components ────────────────────────────────────────────────────────────

const RISK_STYLE: Record<RiskItem["risk_level"], { badge: string; row: string }> = {
  high:   { badge: "bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-300",       row: "bg-red-50/30 dark:bg-red-950/20" },
  medium: { badge: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/50 dark:text-yellow-300", row: "" },
  low:    { badge: "bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-300", row: "" },
};

function RiskBadge({ level }: { level: RiskItem["risk_level"] }) {
  return (
    <span className={cn("inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold", RISK_STYLE[level].badge)}>
      {level.charAt(0).toUpperCase() + level.slice(1)}
    </span>
  );
}

function Step({ n, title, desc }: { n: number; title: string; desc: string }) {
  return (
    <div className="flex gap-3">
      <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-bold text-primary">
        {n}
      </div>
      <div>
        <p className="text-sm font-semibold">{title}</p>
        <p className="text-xs text-muted-foreground">{desc}</p>
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export function ReviewPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const navigate = useNavigate();

  const [phase, setPhase] = useState<Phase>("analyzing");
  const [riskSummary, setRiskSummary] = useState<PlanRiskSummary | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [approveError, setApproveError] = useState<string | null>(null);

  // ── On mount: check current job status (handles page refresh) ──────────────
  useEffect(() => {
    if (!jobId) return;
    api.getJob(jobId).then((j) => {
      setJob(j as unknown as Job);
      if (j.status === "awaiting_approval" && j.plan_risk_summary) {
        setRiskSummary(j.plan_risk_summary);
        setPhase("awaiting");
      } else if (j.status === "completed") {
        navigate(`/jobs/${jobId}`, { replace: true });
      } else if (j.status === "failed") {
        setPhase("error");
        setApproveError((j as unknown as { error?: string }).error ?? "Migration failed during analysis.");
      }
    }).catch(() => {});
  }, [jobId, navigate]);

  // ── Live events ────────────────────────────────────────────────────────────
  useSocket(jobId!, (event: JobEvent) => {
    if (event.type === "awaiting_approval") {
      setRiskSummary(event.plan_risk_summary);
      setPhase("awaiting");
      // Refresh job to get language pair
      api.getJob(jobId!).then((j) => setJob(j as unknown as Job)).catch(() => {});
    } else if (event.type === "node_complete" && phase === "approving") {
      navigate(`/jobs/${jobId}`);
    } else if (event.type === "done") {
      navigate(`/jobs/${jobId}`);
    } else if (event.type === "error") {
      setApproveError(event.error);
      setPhase("error");
    }
  });

  // ── Approve ────────────────────────────────────────────────────────────────
  async function handleApprove() {
    if (!jobId) return;
    setApproveError(null);
    setPhase("approving");
    try {
      await api.approveMigration(jobId);
      navigate(`/jobs/${jobId}`);
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { error?: string; detail?: string } } })?.response?.data?.error ??
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        "Failed to approve migration.";
      setApproveError(msg);
      setPhase("awaiting");
    }
  }

  // ── Analyzing ──────────────────────────────────────────────────────────────
  if (phase === "analyzing") {
    return (
      <div className="flex flex-col items-center justify-center gap-6 py-28 text-center">
        <div className="relative">
          <div className="h-16 w-16 rounded-full border-4 border-primary/20" />
          <Loader2 className="absolute inset-0 m-auto h-10 w-10 animate-spin text-primary" />
        </div>
        <div className="flex flex-col gap-1">
          <h2 className="text-2xl font-bold">Analyzing your codebase…</h2>
          <p className="max-w-sm text-muted-foreground">
            Scanning files, resolving dependencies, and computing per-file risk.
            This takes 30–120 seconds depending on repo size.
          </p>
        </div>
        <div className="flex flex-col gap-2 text-xs text-muted-foreground">
          {["Cloning & filtering files", "Parsing AST & extracting symbols", "Building dependency graph", "Computing risk assessment"].map((s, i) => (
            <div key={i} className="flex items-center gap-2">
              <Loader2 className="h-3 w-3 animate-spin" />
              {s}
            </div>
          ))}
        </div>
      </div>
    );
  }

  // ── Error ──────────────────────────────────────────────────────────────────
  if (phase === "error") {
    return (
      <div className="flex flex-col items-center justify-center gap-4 py-24 text-center">
        <ShieldAlert className="h-12 w-12 text-destructive" />
        <h2 className="text-2xl font-bold text-destructive">Analysis failed</h2>
        <p className="max-w-md text-muted-foreground">{approveError}</p>
        <Button variant="outline" onClick={() => navigate("/")}>Start over</Button>
      </div>
    );
  }

  // ── Main review ────────────────────────────────────────────────────────────
  const files = riskSummary ? Object.entries(riskSummary) : [];
  const sorted = [...files].sort(([, a], [, b]) => ({ high: 0, medium: 1, low: 2 }[a.risk_level] - { high: 0, medium: 1, low: 2 }[b.risk_level]));
  const highFiles   = files.filter(([, r]) => r.risk_level === "high");
  const mediumCount = files.filter(([, r]) => r.risk_level === "medium").length;
  const lowCount    = files.filter(([, r]) => r.risk_level === "low").length;

  const srcLang = (job as unknown as { source_language?: string })?.source_language ?? "source";
  const tgtLang = (job as unknown as { target_language?: string })?.target_language ?? "target";
  const repoUrl = (job as unknown as { repo_url?: string })?.repo_url;

  const totalLines = files.reduce((acc, [, r]) => acc + r.line_count, 0);

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-8 pb-16">

      {/* ── Header ── */}
      <div className="flex flex-col gap-2 border-b pb-6">
        <div className="flex items-center gap-2 text-xs text-muted-foreground font-mono">{jobId}</div>
        <h1 className="text-3xl font-bold">Migration Pre-flight Brief</h1>
        <p className="text-muted-foreground max-w-2xl">
          Read through this report carefully before approving. Once you click
          <strong> Approve &amp; Start</strong>, conversion begins immediately and cannot be paused.
        </p>
      </div>

      {/* ── Section 1: What you're converting ── */}
      <section className="flex flex-col gap-4">
        <h2 className="flex items-center gap-2 text-lg font-semibold">
          <FileCode2 className="h-5 w-5 text-primary" />
          What you're converting
        </h2>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <Card>
            <CardContent className="pt-5">
              <p className="text-xs text-muted-foreground">From</p>
              <p className="text-xl font-bold capitalize">{srcLang}</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-5">
              <p className="text-xs text-muted-foreground">To</p>
              <p className="text-xl font-bold capitalize">{tgtLang}</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-5">
              <p className="text-xs text-muted-foreground">Files</p>
              <p className="text-xl font-bold">{files.length}</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-5">
              <p className="text-xs text-muted-foreground">Total lines</p>
              <p className="text-xl font-bold">{totalLines.toLocaleString()}</p>
            </CardContent>
          </Card>
        </div>
        {repoUrl && (
          <div className="flex items-center gap-2 rounded-md border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
            <GitBranch className="h-3.5 w-3.5 shrink-0" />
            <span className="truncate">{repoUrl}</span>
          </div>
        )}
      </section>

      {/* ── Section 2: What will happen ── */}
      <section className="flex flex-col gap-4">
        <h2 className="flex items-center gap-2 text-lg font-semibold">
          <Layers className="h-5 w-5 text-primary" />
          What happens after you approve
        </h2>
        <Card>
          <CardContent className="pt-6">
            <div className="grid gap-5 sm:grid-cols-2">
              <Step n={1} title="Files converted in dependency order"
                desc="Files your code depends on are converted first, so each file can reference already-converted context when being translated." />
              <Step n={2} title="LLM generates the converted code"
                desc={`Each file is sent to Groq (llama-3.3-70b-versatile) with a targeted prompt to convert it from ${srcLang} to ${tgtLang}.`} />
              <Step n={3} title="Automatic validation & self-correction"
                desc="The output is checked for syntax errors. If errors are found, the LLM is re-prompted with the exact error messages — up to 3 times per file." />
              <Step n={4} title="Files that still fail are flagged, not deleted"
                desc="If a file fails all 3 correction attempts, it's marked as 'flagged' and added to the manual review list in the report. Your originals are never touched." />
            </div>
          </CardContent>
        </Card>
      </section>

      {/* ── Section 3: Risk breakdown ── */}
      <section className="flex flex-col gap-4">
        <h2 className="flex items-center gap-2 text-lg font-semibold">
          <Zap className="h-5 w-5 text-primary" />
          Risk breakdown
        </h2>

        {/* Stat row */}
        <div className="grid grid-cols-3 gap-4">
          <Card className="border-red-200 dark:border-red-900">
            <CardContent className="pt-5">
              <div className="flex items-center justify-between">
                <p className="text-sm text-muted-foreground">High risk</p>
                <XCircle className="h-4 w-4 text-red-500" />
              </div>
              <p className="text-3xl font-bold text-red-600 dark:text-red-400">{highFiles.length}</p>
              <p className="mt-1 text-xs text-muted-foreground">Likely need manual review</p>
            </CardContent>
          </Card>
          <Card className="border-yellow-200 dark:border-yellow-900">
            <CardContent className="pt-5">
              <div className="flex items-center justify-between">
                <p className="text-sm text-muted-foreground">Medium risk</p>
                <AlertTriangle className="h-4 w-4 text-yellow-500" />
              </div>
              <p className="text-3xl font-bold text-yellow-600 dark:text-yellow-400">{mediumCount}</p>
              <p className="mt-1 text-xs text-muted-foreground">May have minor issues</p>
            </CardContent>
          </Card>
          <Card className="border-green-200 dark:border-green-900">
            <CardContent className="pt-5">
              <div className="flex items-center justify-between">
                <p className="text-sm text-muted-foreground">Low risk</p>
                <CheckCircle2 className="h-4 w-4 text-green-500" />
              </div>
              <p className="text-3xl font-bold text-green-600 dark:text-green-400">{lowCount}</p>
              <p className="mt-1 text-xs text-muted-foreground">Should convert cleanly</p>
            </CardContent>
          </Card>
        </div>

        {/* What each level means */}
        <Card className="bg-muted/30">
          <CardContent className="pt-5">
            <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">What each level means</p>
            <div className="flex flex-col gap-3">
              <div className="flex gap-3">
                <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-red-500" />
                <div>
                  <p className="text-sm font-medium">High risk — plan to review these manually</p>
                  <p className="text-xs text-muted-foreground">The file uses patterns that are hard for the LLM to translate reliably — things like <code>eval()</code>, metaclasses, dynamic imports, or prototype manipulation. The conversion may be syntactically valid but semantically wrong.</p>
                </div>
              </div>
              <div className="flex gap-3">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-yellow-500" />
                <div>
                  <p className="text-sm font-medium">Medium risk — spot-check the output</p>
                  <p className="text-xs text-muted-foreground">The file has some complexity or uses patterns that may not map one-to-one between languages. Most will convert correctly, but it's worth a quick read of the output.</p>
                </div>
              </div>
              <div className="flex gap-3">
                <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-green-500" />
                <div>
                  <p className="text-sm font-medium">Low risk — should convert cleanly</p>
                  <p className="text-xs text-muted-foreground">Straightforward code with no detected red flags. Standard functions, classes, and imports that map naturally between languages.</p>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      </section>

      {/* ── Section 4: High-risk files callout ── */}
      {highFiles.length > 0 && (
        <section className="flex flex-col gap-4">
          <h2 className="flex items-center gap-2 text-lg font-semibold">
            <Flag className="h-5 w-5 text-red-500" />
            {highFiles.length} file{highFiles.length > 1 ? "s" : ""} need your attention
          </h2>
          <div className="flex flex-col gap-3">
            {highFiles.map(([fp, info]) => (
              <Card key={fp} className="border-red-200 dark:border-red-900/60">
                <CardContent className="pt-4 pb-4">
                  <div className="flex items-start justify-between gap-4">
                    <p className="font-mono text-xs font-semibold break-all">{fp}</p>
                    <div className="flex shrink-0 flex-col items-end gap-1">
                      <RiskBadge level="high" />
                      <span className="text-xs text-muted-foreground">{info.line_count} lines</span>
                    </div>
                  </div>
                  {info.reasons.length > 0 && (
                    <ul className="mt-3 space-y-1 border-t pt-3">
                      {info.reasons.map((r, i) => (
                        <li key={i} className="flex items-start gap-2 text-xs text-muted-foreground">
                          <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0 text-red-400" />
                          {r}
                        </li>
                      ))}
                    </ul>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
        </section>
      )}

      {/* ── Section 5: What you'll get ── */}
      <section className="flex flex-col gap-4">
        <h2 className="flex items-center gap-2 text-lg font-semibold">
          <Info className="h-5 w-5 text-primary" />
          What you'll get
        </h2>
        <Card>
          <CardContent className="pt-5">
            <ul className="flex flex-col gap-3">
              {[
                { icon: CheckCircle2, color: "text-green-500", text: "Converted files written to workspace/output/ — your original repo is never modified." },
                { icon: RefreshCw,    color: "text-primary",   text: "Files converted in dependency order so each file has context from its already-converted dependencies." },
                { icon: Flag,         color: "text-yellow-500", text: `Files that fail all 3 self-correction attempts are flagged — not deleted. You'll see them listed in the final report so you can convert them manually.` },
                { icon: FileCode2,    color: "text-primary",   text: "A full migration report is generated when conversion completes — with per-file status, retry counts, and validation errors." },
              ].map(({ icon: Icon, color, text }, i) => (
                <li key={i} className="flex items-start gap-3 text-sm">
                  <Icon className={cn("mt-0.5 h-4 w-4 shrink-0", color)} />
                  {text}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      </section>

      {/* ── Section 6: All files table ── */}
      <section className="flex flex-col gap-4">
        <h2 className="flex items-center gap-2 text-lg font-semibold">
          <Layers className="h-5 w-5 text-primary" />
          All files ({files.length})
        </h2>
        <Card>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/50">
                    <th className="px-4 py-3 text-left font-medium">File</th>
                    <th className="px-4 py-3 text-left font-medium">Risk</th>
                    <th className="px-4 py-3 text-left font-medium">Complexity</th>
                    <th className="px-4 py-3 text-right font-medium">Lines</th>
                    <th className="px-4 py-3 text-left font-medium">Concerns</th>
                  </tr>
                </thead>
                <tbody>
                  {sorted.map(([fp, info]) => (
                    <tr key={fp} className={cn("border-b last:border-0 transition-colors hover:bg-muted/30", RISK_STYLE[info.risk_level].row)}>
                      <td className="px-4 py-3 font-mono text-xs max-w-[240px] truncate" title={fp}>{fp}</td>
                      <td className="px-4 py-3"><RiskBadge level={info.risk_level} /></td>
                      <td className="px-4 py-3">
                        <Badge variant="outline" className="capitalize text-xs">{info.complexity_class}</Badge>
                      </td>
                      <td className="px-4 py-3 text-right tabular-nums text-muted-foreground">{info.line_count}</td>
                      <td className="px-4 py-3 max-w-[320px]">
                        {info.reasons.length === 0 ? (
                          <span className="flex items-center gap-1 text-green-600 dark:text-green-400 text-xs">
                            <CheckCircle2 className="h-3.5 w-3.5" /> No concerns
                          </span>
                        ) : (
                          <ul className="space-y-0.5">
                            {info.reasons.map((r, i) => (
                              <li key={i} className="flex items-start gap-1 text-xs text-muted-foreground">
                                <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0 text-yellow-500" />
                                {r}
                              </li>
                            ))}
                          </ul>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      </section>

      {/* ── Approve ── */}
      <div className="flex flex-col gap-4 rounded-xl border-2 border-primary/30 bg-primary/5 p-6">
        <div className="flex flex-col gap-1">
          <p className="text-lg font-bold">Ready to start conversion?</p>
          <p className="text-sm text-muted-foreground">
            You've reviewed the plan. Once started, conversion runs automatically and cannot be paused.
            High-risk files will still be attempted — if they fail they'll be flagged for manual review.
          </p>
        </div>

        {approveError && (
          <p className="rounded-md border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            {approveError}
          </p>
        )}

        <div className="flex items-center gap-4">
          <Button
            size="lg"
            onClick={handleApprove}
            disabled={phase === "approving"}
            className="min-w-[220px]"
          >
            {phase === "approving" ? (
              <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Starting conversion…</>
            ) : (
              <>Approve &amp; Start conversion <ArrowRight className="ml-2 h-4 w-4" /></>
            )}
          </Button>
          <Button variant="ghost" size="sm" onClick={() => navigate("/")}>
            Cancel &amp; start over
          </Button>
        </div>
      </div>

    </div>
  );
}
