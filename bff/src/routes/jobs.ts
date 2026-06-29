import { Router, Request, Response, NextFunction } from "express";
import { Job } from "../models/Job";

const router = Router();

// GET /api/jobs  — list all stored jobs (most recent first)
router.get("/", async (_req: Request, res: Response, next: NextFunction) => {
  try {
    const jobs = await Job.find({}, { files: 0 }).sort({ createdAt: -1 }).limit(100);
    res.json(jobs);
  } catch (err) {
    next(err);
  }
});

// DELETE /api/jobs/:jobId  — remove a job record
router.delete("/:jobId", async (req: Request, res: Response, next: NextFunction) => {
  try {
    await Job.deleteOne({ jobId: req.params["jobId"] as string });
    res.json({ deleted: req.params.jobId });
  } catch (err) {
    next(err);
  }
});

export default router;
