import axios from "axios";
import type { Job, MigrationPlan, MigrationReport, FileDetail } from "@/types";

const http = axios.create({ baseURL: "/api" });

export const api = {
  // Start from GitHub URL
  startMigration(payload: {
    repo_url: string;
    source_language: string;
    target_language: string;
  }) {
    return http.post<{ job_id: string; status: string }>("/migrate", payload).then((r) => r.data);
  },

  // Start from ZIP upload
  uploadAndMigrate(file: File, sourceLanguage: string, targetLanguage: string) {
    const form = new FormData();
    form.append("file", file);
    form.append("source_language", sourceLanguage);
    form.append("target_language", targetLanguage);
    return http
      .post<{ job_id: string; status: string }>("/migrate/upload", form)
      .then((r) => r.data);
  },

  getJob(jobId: string) {
    return http.get<Job>(`/migrate/${jobId}`).then((r) => r.data);
  },

  getPlan(jobId: string) {
    return http.get<MigrationPlan>(`/migrate/${jobId}/plan`).then((r) => r.data);
  },

  getResult(jobId: string) {
    return http
      .get<{ status: string; stats: MigrationPlan["stats"]; report: MigrationReport }>(`/migrate/${jobId}/result`)
      .then((r) => r.data);
  },

  getFileDetail(jobId: string, filePath: string) {
    return http.get<FileDetail>(`/migrate/${jobId}/files/${filePath}`).then((r) => r.data);
  },

  approveMigration(jobId: string) {
    return http.post<{ job_id: string; status: string }>(`/migrate/${jobId}/approve`).then((r) => r.data);
  },

  listJobs() {
    return http.get<Job[]>("/jobs").then((r) => r.data);
  },
};
