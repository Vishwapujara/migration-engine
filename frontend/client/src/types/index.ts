export type Language = "python" | "javascript" | "typescript";

export type FileStatus = "pending" | "in_progress" | "converted" | "flagged" | "failed";

export type JobStatus = "pending" | "running" | "awaiting_approval" | "completed" | "failed";

export interface FileEntry {
  file_path: string;
  status: FileStatus;
  complexity_score: number;
  complexity_class: "simple" | "moderate" | "complex";
  line_count: number;
  retry_count: number;
  converted_source?: string;
  error_message?: string;
}

export interface PlanStats {
  total: number;
  converted: number;
  flagged: number;
  failed: number;
  pending: number;
  in_progress: number;
  percent_complete: number;
}

export interface MigrationPlan {
  job_id: string;
  source_language: Language;
  target_language: Language;
  files: FileEntry[];
  topological_order: string[];
  stats: PlanStats;
}

// Per-file risk assessment returned by RANK node
export interface RiskItem {
  risk_level: "low" | "medium" | "high";
  reasons: string[];
  line_count: number;
  complexity_score: number;
  complexity_class: "simple" | "moderate" | "complex";
}

export type PlanRiskSummary = Record<string, RiskItem>;

export interface Job {
  jobId: string;
  status: JobStatus;
  sourceLanguage: Language;
  targetLanguage: Language;
  repoUrl?: string;
  messages: string[];
  stats: PlanStats | null;
  plan_risk_summary: PlanRiskSummary | null;
  error?: string;
  outputRepoPath?: string;
  prUrl?: string;
  createdAt: string;
  updatedAt: string;
}

export interface FileDetail extends FileEntry {
  language: string;
  complexity_score: number;
  retry_history: string[];
}

export interface MigrationReport {
  job_id: string;
  source_language: Language;
  target_language: Language;
  stats: PlanStats;
  converted_files: string[];
  flagged_files: string[];
  failed_files: string[];
}

// Socket.IO event payloads from the BFF relay
export type JobEvent =
  | { type: "connected"; job: Job }
  | { type: "node_complete"; node: string; messages: string[]; progress: PlanStats; current_file: string | null }
  | { type: "awaiting_approval"; plan_risk_summary: PlanRiskSummary }
  | { type: "done"; progress: PlanStats }
  | { type: "error"; error: string }
  | { type: "ping" }
  | { type: "ws_closed" };
