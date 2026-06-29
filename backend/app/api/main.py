"""FastAPI application entry point."""
from __future__ import annotations
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure workspace directory exists on startup
    settings.workspace_dir.mkdir(parents=True, exist_ok=True)
    yield
    # Nothing to clean up on shutdown


app = FastAPI(
    title="Migration Engine API",
    description="Codebase migration engine — convert Python ↔ JavaScript, JavaScript → TypeScript.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/health")
async def health():
    return {"status": "ok", "workspace": str(settings.workspace_dir)}
