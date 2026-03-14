"""SentinelStack FastAPI backend — serves data to SentinelTower web dashboard."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv(Path(__file__).resolve().parent.parent / "config" / ".env")

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

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

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
AUTO_PIPELINE_INTERVAL = int(os.getenv("AUTO_PIPELINE_INTERVAL_SECONDS", "900"))
CLEANUP_MAX_AGE_HOURS = int(os.getenv("CLEANUP_MAX_AGE_HOURS", "6"))
CFG_PATH = Path(__file__).resolve().parent.parent / "config" / "sources.json"


# ---------------------------------------------------------------------------
# Auto-pipeline: collect → analyze → write
# ---------------------------------------------------------------------------
STALE_LOCK_MINUTES = 10  # force-reset any stage stuck longer than this


def _break_stale_locks() -> bool:
    """Reset pipeline stages that have been 'running' for too long. Returns True if any were reset."""
    from datetime import datetime, timezone, timedelta
    from collector.store import get_conn, set_pipeline_state

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT collect_running, analyze_running, write_running, updated_at FROM pipeline_state WHERE id = 1")
    row = cur.fetchone()
    cur.close()
    conn.close()

    if not row:
        return False

    any_running = row["collect_running"] or row["analyze_running"] or row["write_running"]
    if not any_running:
        return False

    updated_at = row["updated_at"]
    if not updated_at:
        # No timestamp — legacy stuck state, force reset
        logger.warning("Auto-pipeline: found stuck state with no timestamp — force resetting")
        for stage in ("collect", "analyze", "write"):
            set_pipeline_state(stage, False)
        return True

    try:
        lock_time = datetime.fromisoformat(updated_at)
        age = datetime.now(tz=timezone.utc) - lock_time
        if age > timedelta(minutes=STALE_LOCK_MINUTES):
            logger.warning(f"Auto-pipeline: lock held for {age} — force resetting stale state")
            for stage in ("collect", "analyze", "write"):
                set_pipeline_state(stage, False)
            return True
    except (ValueError, TypeError):
        for stage in ("collect", "analyze", "write"):
            set_pipeline_state(stage, False)
        return True

    return False


def _run_full_pipeline() -> None:
    """Run collect → analyze → write synchronously. Called from async wrapper."""
    from collector.base import build_source
    from collector.store import init_db, bulk_insert, get_pipeline_state, set_pipeline_state
    from analyst.filter import run_analysis
    from writer.reporter import run_writer

    state = get_pipeline_state()
    if state["collect"] or state["analyze"] or state["write"]:
        if _break_stale_locks():
            logger.info("Auto-pipeline: stale locks cleared — proceeding")
        else:
            logger.info("Auto-pipeline: skipping — a stage is actively running")
            return

    init_db()

    # --- Collect ---
    try:
        set_pipeline_state("collect", True)
        with open(CFG_PATH) as f:
            sources_cfg = json.load(f)

        for name, cfg in sources_cfg.items():
            if not cfg.get("enabled", True):
                continue
            try:
                articles = build_source(name, cfg).fetch()
                new, skipped = bulk_insert(articles)
                logger.info(f"auto-collect [{name}]: {new} new, {skipped} skipped")
            except Exception as e:
                logger.error(f"auto-collect [{name}] failed: {e}")
    except Exception as e:
        logger.error(f"auto-collect failed: {e}")
    finally:
        set_pipeline_state("collect", False)

    # --- Analyze ---
    try:
        set_pipeline_state("analyze", True)
        groq_key = os.getenv("GROQ_API_KEY", "")
        if groq_key:
            summary = run_analysis(api_key=groq_key)
            logger.info(f"auto-analyze summary: {summary}")
        else:
            logger.warning("auto-analyze skipped: GROQ_API_KEY not set")
    except Exception as e:
        logger.error(f"auto-analyze failed: {e}")
    finally:
        set_pipeline_state("analyze", False)

    # --- Write ---
    try:
        set_pipeline_state("write", True)
        groq_key = os.getenv("GROQ_API_KEY", "")
        if groq_key:
            result = run_writer(api_key=groq_key, tier=None)
            logger.info(f"auto-write result: {result}")
        else:
            logger.warning("auto-write skipped: GROQ_API_KEY not set")
    except Exception as e:
        logger.error(f"auto-write failed: {e}")
    finally:
        set_pipeline_state("write", False)


async def _auto_pipeline_loop() -> None:
    """Background loop: run pipeline immediately, then every INTERVAL seconds."""
    # Run immediately on startup
    logger.info("Auto-pipeline: running initial collection...")
    await asyncio.get_event_loop().run_in_executor(None, _run_full_pipeline)
    logger.info("Auto-pipeline: initial run complete")

    while True:
        await asyncio.sleep(AUTO_PIPELINE_INTERVAL)
        logger.info("Auto-pipeline: starting scheduled run")
        await asyncio.get_event_loop().run_in_executor(None, _run_full_pipeline)
        logger.info("Auto-pipeline: scheduled run complete")


# ---------------------------------------------------------------------------
# Data cleanup: purge records older than CLEANUP_MAX_AGE_HOURS
# ---------------------------------------------------------------------------
def _run_cleanup() -> None:
    """Delete articles, scored_events, and reports older than max age."""
    from collector.store import get_conn
    from datetime import datetime, timezone, timedelta

    cutoff = (datetime.now(tz=timezone.utc) - timedelta(hours=CLEANUP_MAX_AGE_HOURS)).isoformat()
    conn = get_conn()
    cur = conn.cursor()
    try:
        # Delete old reports
        cur.execute("DELETE FROM reports WHERE generated_at < %s", (cutoff,))
        reports_deleted = cur.rowcount

        # Delete old scored_events
        cur.execute("DELETE FROM scored_events WHERE scored_at < %s", (cutoff,))
        events_deleted = cur.rowcount

        # Delete old articles
        cur.execute("DELETE FROM articles WHERE collected_at < %s", (cutoff,))
        articles_deleted = cur.rowcount

        conn.commit()
        logger.info(
            f"Cleanup: deleted {articles_deleted} articles, "
            f"{events_deleted} scored_events, {reports_deleted} reports "
            f"older than {CLEANUP_MAX_AGE_HOURS}h"
        )
    except Exception as e:
        conn.rollback()
        logger.error(f"Cleanup failed: {e}")
    finally:
        cur.close()
        conn.close()


async def _cleanup_loop() -> None:
    """Run cleanup every CLEANUP_MAX_AGE_HOURS hours."""
    cleanup_interval = CLEANUP_MAX_AGE_HOURS * 3600
    while True:
        await asyncio.sleep(cleanup_interval)
        logger.info("Running scheduled data cleanup...")
        await asyncio.get_event_loop().run_in_executor(None, _run_cleanup)


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def startup():
    from collector.store import init_db, set_pipeline_state
    init_db()
    # Reset any stuck pipeline state from a previous crash/restart
    for stage in ("collect", "analyze", "write"):
        set_pipeline_state(stage, False)
    logger.info("Pipeline state reset — all stages idle")
    asyncio.create_task(_auto_pipeline_loop())
    asyncio.create_task(_cleanup_loop())
    logger.info(
        f"Started: auto-pipeline every {AUTO_PIPELINE_INTERVAL}s, "
        f"cleanup every {CLEANUP_MAX_AGE_HOURS}h"
    )


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
