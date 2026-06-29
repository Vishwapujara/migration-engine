import express from "express";
import cors from "cors";
import http from "http";
import { Server as IOServer } from "socket.io";
import { connectDB } from "./db";
import { config } from "./config";
import { attachRelay } from "./relay";
import migrationsRouter from "./routes/migrations";
import jobsRouter from "./routes/jobs";

async function main() {
  await connectDB();

  const app = express();

  app.use(cors({ origin: config.corsOrigin, credentials: true }));
  app.use(express.json());

  // Health
  app.get("/health", (_req, res) => {
    res.json({ status: "ok", service: "migration-engine-bff" });
  });

  // REST routes
  app.use("/api/migrate", migrationsRouter);
  app.use("/api/jobs", jobsRouter);

  // Generic error handler
  app.use((err: Error, _req: express.Request, res: express.Response, _next: express.NextFunction) => {
    console.error("[BFF]", err);
    res.status(500).json({ error: err.message });
  });

  // HTTP server + Socket.IO
  const httpServer = http.createServer(app);
  const io = new IOServer(httpServer, {
    cors: { origin: config.corsOrigin, methods: ["GET", "POST"] },
  });
  attachRelay(io);

  httpServer.listen(config.port, () => {
    console.log(`[BFF] Listening on http://localhost:${config.port}`);
    console.log(`[BFF] FastAPI upstream: ${config.fastApiUrl}`);
  });
}

main().catch((err) => {
  console.error("[BFF] Fatal startup error:", err);
  process.exit(1);
});
