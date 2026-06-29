import { useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { GitBranch, Upload, ArrowRight, Loader2, FileCode2, Zap, Shield } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Language } from "@/types";

type Tab = "github" | "zip";

const LANGUAGE_PAIRS: { src: Language; tgt: Language; label: string }[] = [
  { src: "python", tgt: "javascript", label: "Python → JavaScript" },
  { src: "javascript", tgt: "python", label: "JavaScript → Python" },
  { src: "javascript", tgt: "typescript", label: "JavaScript → TypeScript" },
];

export function LandingPage() {
  const navigate = useNavigate();
  const [tab, setTab] = useState<Tab>("github");
  const [repoUrl, setRepoUrl] = useState("");
  const [zipFile, setZipFile] = useState<File | null>(null);
  const [pairIdx, setPairIdx] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const pair = LANGUAGE_PAIRS[pairIdx];

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      let result: { job_id: string };
      if (tab === "github") {
        if (!repoUrl.trim()) throw new Error("Please enter a GitHub URL.");
        result = await api.startMigration({
          repo_url: repoUrl.trim(),
          source_language: pair.src,
          target_language: pair.tgt,
        });
      } else {
        if (!zipFile) throw new Error("Please select a ZIP file.");
        result = await api.uploadAndMigrate(zipFile, pair.src, pair.tgt);
      }
      navigate(`/jobs/${result.job_id}/review`);
    } catch (err: unknown) {
      const msg =
        err instanceof Error
          ? err.message
          : (err as { response?: { data?: { error?: string } } })?.response?.data?.error ?? "Submission failed.";
      setError(msg);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex flex-col items-center gap-12">
      {/* Hero */}
      <div className="mt-8 flex flex-col items-center gap-4 text-center">
        <Badge variant="secondary" className="px-3 py-1 text-xs uppercase tracking-widest">
          Powered by LangGraph + Groq
        </Badge>
        <h1 className="text-5xl font-bold tracking-tight">
          Migrate your codebase{" "}
          <span className="text-primary">in minutes</span>
        </h1>
        <p className="max-w-xl text-lg text-muted-foreground">
          AI-driven conversion between Python, JavaScript, and TypeScript. Fully automated,
          self-correcting, with a detailed migration report.
        </p>
      </div>

      {/* Feature pills */}
      <div className="flex flex-wrap justify-center gap-4">
        {[
          { icon: Zap, text: "LangGraph orchestration" },
          { icon: FileCode2, text: "AST-aware analysis" },
          { icon: Shield, text: "Self-correcting LLM" },
        ].map(({ icon: Icon, text }) => (
          <div key={text} className="flex items-center gap-2 rounded-full border bg-card px-4 py-2 text-sm">
            <Icon className="h-4 w-4 text-primary" />
            {text}
          </div>
        ))}
      </div>

      {/* Submission card */}
      <Card className="w-full max-w-2xl">
        <CardHeader>
          <CardTitle>Start a migration</CardTitle>
          <CardDescription>Paste a GitHub URL or upload a ZIP of your project.</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="flex flex-col gap-6">
            {/* Language pair */}
            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium">Migration type</label>
              <Select
                value={String(pairIdx)}
                onValueChange={(v) => setPairIdx(Number(v))}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {LANGUAGE_PAIRS.map((p, i) => (
                    <SelectItem key={i} value={String(i)}>
                      {p.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Tab toggle */}
            <div className="flex rounded-lg border p-1">
              {(["github", "zip"] as Tab[]).map((t) => (
                <button
                  key={t}
                  type="button"
                  onClick={() => setTab(t)}
                  className={cn(
                    "flex flex-1 items-center justify-center gap-2 rounded-md px-3 py-2 text-sm transition-colors",
                    tab === t
                      ? "bg-primary text-primary-foreground"
                      : "text-muted-foreground hover:text-foreground"
                  )}
                >
                  {t === "github" ? (
                    <><GitBranch className="h-4 w-4" /> GitHub URL</>
                  ) : (
                    <><Upload className="h-4 w-4" /> Upload ZIP</>
                  )}
                </button>
              ))}
            </div>

            {/* Input area */}
            {tab === "github" ? (
              <div className="flex flex-col gap-1.5">
                <label className="text-sm font-medium">Repository URL</label>
                <input
                  type="url"
                  value={repoUrl}
                  onChange={(e) => setRepoUrl(e.target.value)}
                  placeholder="https://github.com/owner/repo"
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                />
              </div>
            ) : (
              <div className="flex flex-col gap-1.5">
                <label className="text-sm font-medium">ZIP file</label>
                <div
                  onClick={() => fileRef.current?.click()}
                  className={cn(
                    "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-md border-2 border-dashed border-input px-6 py-8 text-sm text-muted-foreground transition-colors hover:border-primary hover:text-primary",
                    zipFile && "border-primary text-primary"
                  )}
                >
                  <Upload className="h-8 w-8" />
                  {zipFile ? zipFile.name : "Click to select a .zip file"}
                  <input
                    ref={fileRef}
                    type="file"
                    accept=".zip"
                    className="hidden"
                    onChange={(e) => setZipFile(e.target.files?.[0] ?? null)}
                  />
                </div>
              </div>
            )}

            {error && (
              <p className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
                {error}
              </p>
            )}

            <Button type="submit" disabled={submitting} size="lg" className="w-full">
              {submitting ? (
                <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Starting migration…</>
              ) : (
                <>Start migration <ArrowRight className="ml-2 h-4 w-4" /></>
              )}
            </Button>
          </form>
        </CardContent>
      </Card>

      {/* Supported pairs */}
      <div className="flex flex-col items-center gap-2 pb-8 text-center text-sm text-muted-foreground">
        <p>Supported conversions</p>
        <div className="flex gap-2">
          {LANGUAGE_PAIRS.map((p) => (
            <Badge key={p.label} variant="outline">{p.label}</Badge>
          ))}
        </div>
      </div>
    </div>
  );
}
