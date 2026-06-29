import dotenv from "dotenv";
dotenv.config();

export const config = {
  port: parseInt(process.env.PORT || "4000", 10),
  mongoUri: process.env.MONGO_URI || "mongodb://localhost:27017/migration_engine",
  fastApiUrl: process.env.FASTAPI_URL || "http://localhost:8000",
  corsOrigin: process.env.CORS_ORIGIN || "http://localhost:5173",
} as const;
