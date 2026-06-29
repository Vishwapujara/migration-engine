import { Router, Request, Response, NextFunction } from "express";
import multer from "multer";
import { Job } from "../models/Job";
import { FastAPIService } from "../services/fastapi";

const router = Router();
const upload = multer({ storage: multer.memoryStorage() });

// POST /api/migrate  — start from GitHub URL
router.post("/", async (req: Request, res: Response, next: NextFunction) => {
  try {
    const { repo_url, source_language, target_language } = req.body as {
      repo_url: string;
      source_language: string;
      target_language: string;
    };

    if (!repo_url || !source_language || !target_language) {
      res.status(400).json({ error: "repo_url, source_language, and target_language are required." });
      return;
    }

    const result = await FastAPIService.startMigration({ repo_url, source_language, target_language });

    await Job.create({
      jobId: result.job_id,
      status: "pending",
      sourceLanguage: source_language,
      targetLanguage: target_language,
      repoUrl: repo_url,
    });

    res.status(202).json(result);
  } catch (err) {
    next(err);
  }
});

// POST /api/migrate/upload  — start from ZIP upload
router.post(
  "/upload",
  upload.single("file"),
  async (req: Request, res: Response, next: NextFunction) => {
    try {
      if (!req.file) {
        res.status(400).json({ error: "No file uploaded." });
        return;
      }

      const { source_language, target_language } = req.body as {
        source_language: string;
        target_language: string;
      };

      if (!source_language || !target_language) {
        res.status(400).json({ error: "source_language and target_language are required." });
        return;
      }

      const form = new FormData();
      const blob = new Blob([req.file.buffer as unknown as ArrayBuffer], { type: req.file.mimetype });
      form.append("file", blob, req.file.originalname);
      form.append("source_language", source_language);
      form.append("target_language", target_language);

      const result = await FastAPIService.uploadAndMigrate(form);

      await Job.create({
        jobId: result.job_id,
        status: "pending",
        sourceLanguage: source_language,
        targetLanguage: target_language,
      });

      res.status(202).json(result);
    } catch (err) {
      next(err);
    }
  }
);

// GET /api/migrate/:jobId
router.get("/:jobId", async (req: Request, res: Response, next: NextFunction) => {
  try {
    const jobId = req.params["jobId"] as string;

    // Hydrate from FastAPI and sync into Mongo
    let fastapiJob: Record<string, unknown>;
    try {
      fastapiJob = await FastAPIService.getJob(jobId);
    } catch {
      const mongoJob = await Job.findOne({ jobId });
      if (!mongoJob) {
        res.status(404).json({ error: "Job not found." });
        return;
      }
      res.json(mongoJob);
      return;
    }

    const updated = await Job.findOneAndUpdate(
      { jobId },
      {
        status: fastapiJob.status as string,
        messages: fastapiJob.messages as string[],
        stats: fastapiJob.stats as Record<string, unknown>,
        planRiskSummary: (fastapiJob.plan_risk_summary ?? null) as Record<string, unknown> | null,
        error: fastapiJob.error as string | undefined,
        outputRepoPath: fastapiJob.output_repo_path as string | undefined,
        prUrl: fastapiJob.pr_url as string | undefined,
      },
      { new: true, upsert: false }
    );

    // Always include plan_risk_summary from FastAPI (Mongo camelCase → snake_case)
    const base = updated?.toObject() ?? fastapiJob;
    res.json({ ...base, plan_risk_summary: fastapiJob.plan_risk_summary ?? null });
  } catch (err) {
    next(err);
  }
});

// GET /api/migrate/:jobId/plan
router.get("/:jobId/plan", async (req: Request, res: Response, next: NextFunction) => {
  try {
    const plan = await FastAPIService.getJobPlan(req.params["jobId"] as string);
    res.json(plan);
  } catch (err: unknown) {
    const status = (err as { response?: { status?: number } })?.response?.status;
    if (status === 404 || status === 202) {
      res.status(status).json({ error: "Plan not ready yet." });
      return;
    }
    next(err);
  }
});

// GET /api/migrate/:jobId/result
router.get("/:jobId/result", async (req: Request, res: Response, next: NextFunction) => {
  try {
    const result = await FastAPIService.getJobResult(req.params["jobId"] as string);
    res.json(result);
  } catch (err: unknown) {
    const status = (err as { response?: { status?: number } })?.response?.status;
    if (status === 202) {
      res.status(202).json({ error: "Job still running." });
      return;
    }
    next(err);
  }
});

// POST /api/migrate/:jobId/approve
router.post("/:jobId/approve", async (req: Request, res: Response, next: NextFunction) => {
  try {
    const result = await FastAPIService.approveMigration(req.params["jobId"] as string);
    res.json(result);
  } catch (err: unknown) {
    const status = (err as { response?: { status?: number } })?.response?.status;
    if (status === 400 || status === 404) {
      res.status(status).json({ error: (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? "Cannot approve." });
      return;
    }
    next(err);
  }
});

// GET /api/migrate/:jobId/files/*filePath
router.get("/:jobId/files/*filePath", async (req: Request, res: Response, next: NextFunction) => {
  try {
    const jobId = req.params["jobId"] as string;
    const filePath = (req.params["filePath"] ?? "") as string;
    const detail = await FastAPIService.getFileDetail(jobId, filePath);
    res.json(detail);
  } catch (err: unknown) {
    const status = (err as { response?: { status?: number } })?.response?.status;
    if (status === 404) {
      res.status(404).json({ error: "File not found in plan." });
      return;
    }
    next(err);
  }
});

export default router;
