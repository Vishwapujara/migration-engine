/**
 * Thin client for the Python FastAPI backend.
 */
import axios from "axios";
import { config } from "../config";

const api = axios.create({ baseURL: config.fastApiUrl });

export interface StartMigrationPayload {
  repo_url: string;
  source_language: string;
  target_language: string;
}

export const FastAPIService = {
  async startMigration(payload: StartMigrationPayload) {
    const { data } = await api.post("/api/migrate", payload);
    return data as { job_id: string; status: string };
  },

  async uploadAndMigrate(formData: FormData) {
    const { data } = await api.post("/api/migrate/upload", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    return data as { job_id: string; status: string };
  },

  async getJob(jobId: string) {
    const { data } = await api.get(`/api/jobs/${jobId}`);
    return data;
  },

  async getJobPlan(jobId: string) {
    const { data } = await api.get(`/api/jobs/${jobId}/plan`);
    return data;
  },

  async getJobResult(jobId: string) {
    const { data } = await api.get(`/api/jobs/${jobId}/result`);
    return data;
  },

  async getFileDetail(jobId: string, filePath: string) {
    const { data } = await api.get(`/api/jobs/${jobId}/files/${filePath}`);
    return data;
  },

  async approveMigration(jobId: string) {
    const { data } = await api.post(`/api/jobs/${jobId}/approve`);
    return data as { job_id: string; status: string };
  },
};
