import { Schema, model, Document } from "mongoose";

export interface IFileEntry {
  file_path: string;
  status: "pending" | "in_progress" | "converted" | "flagged" | "failed";
  source_language: string;
  target_language: string;
  complexity_score: number;
  converted_source?: string;
  retry_count: number;
  retry_history: string[];
  error_message?: string;
}

export interface IJob extends Document {
  jobId: string;
  status: "pending" | "running" | "awaiting_approval" | "completed" | "failed";
  sourceLanguage: string;
  targetLanguage: string;
  repoUrl?: string;
  zipPath?: string;
  messages: string[];
  stats: Record<string, unknown>;
  planRiskSummary?: Record<string, unknown>;
  error?: string;
  outputRepoPath?: string;
  prUrl?: string;
  files: IFileEntry[];
  createdAt: Date;
  updatedAt: Date;
}

const FileEntrySchema = new Schema<IFileEntry>(
  {
    file_path: { type: String, required: true },
    status: {
      type: String,
      enum: ["pending", "in_progress", "converted", "flagged", "failed"],
      default: "pending",
    },
    source_language: String,
    target_language: String,
    complexity_score: { type: Number, default: 0 },
    converted_source: String,
    retry_count: { type: Number, default: 0 },
    retry_history: [String],
    error_message: String,
  },
  { _id: false }
);

const JobSchema = new Schema<IJob>(
  {
    jobId: { type: String, required: true, unique: true, index: true },
    status: {
      type: String,
      enum: ["pending", "running", "awaiting_approval", "completed", "failed"],
      default: "pending",
    },
    sourceLanguage: { type: String, required: true },
    targetLanguage: { type: String, required: true },
    repoUrl: String,
    zipPath: String,
    messages: [String],
    stats: { type: Schema.Types.Mixed, default: {} },
    planRiskSummary: { type: Schema.Types.Mixed, default: null },
    error: String,
    outputRepoPath: String,
    prUrl: String,
    files: [FileEntrySchema],
  },
  { timestamps: true }
);

export const Job = model<IJob>("Job", JobSchema);
