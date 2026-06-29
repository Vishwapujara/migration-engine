import mongoose from "mongoose";
import { config } from "./config";

export async function connectDB(): Promise<void> {
  await mongoose.connect(config.mongoUri);
  console.log(`[DB] Connected to MongoDB at ${config.mongoUri}`);
}

mongoose.connection.on("error", (err) => {
  console.error("[DB] MongoDB error:", err);
});

mongoose.connection.on("disconnected", () => {
  console.warn("[DB] MongoDB disconnected.");
});
