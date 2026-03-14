"""SentinelStack FastAPI backend — serves data to SentinelTower web dashboard."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv(Path(__file__).resolve().parent.parent / "config" / ".env")

_frontend_url = os.getenv("FRONTEND_URL", "")
if not _frontend_url:
    raise RuntimeError(
        "FRONTEND_URL is not set. Add it to config/.env "
        "(e.g. FRONTEND_URL=http://localhost:3000 for local dev)"
    )

app = FastAPI(title="SentinelStack API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_frontend_url.split(","),
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    from collector.store import init_db
    init_db()


from api.routers import articles, reports, pipeline, health, stats, chat  # noqa: E402

app.include_router(articles.router, prefix="/api")
app.include_router(reports.router, prefix="/api")
app.include_router(pipeline.router, prefix="/api")
app.include_router(health.router, prefix="/api")
app.include_router(stats.router, prefix="/api")
app.include_router(chat.router, prefix="/api")


@app.get("/")
def root():
    return {"service": "SentinelStack API", "status": "ok"}
