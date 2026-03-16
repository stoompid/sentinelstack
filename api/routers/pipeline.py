from __future__ import annotations

import logging
import os

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Security
from fastapi.security import APIKeyHeader

from collector.store import get_pipeline_state, set_pipeline_state

logger = logging.getLogger(__name__)
router = APIRouter()

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def _verify_key(api_key: str = Security(_api_key_header)) -> None:
    """Dependency: reject requests with a missing or invalid X-API-Key header."""
    secret = os.getenv("API_SECRET", "")
    if not secret:
        raise HTTPException(status_code=503, detail="API_SECRET not configured on server")
    if api_key != secret:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")


def _get_api_key() -> str:
    key = os.getenv("GROQ_API_KEY") or os.getenv("GEMINI_API_KEY", "")
    if not key:
        raise RuntimeError("No LLM API key set (GROQ_API_KEY or GEMINI_API_KEY)")
    return key


def _run_collect(source: str) -> None:
    set_pipeline_state("collect", True)
    try:
        import json
        from pathlib import Path
        from collector.base import build_source
        from collector.store import init_db, bulk_insert

        init_db()
        cfg_path = Path(__file__).resolve().parent.parent.parent / "config" / "sources.json"
        with open(cfg_path) as f:
            sources_cfg = json.load(f)

        priority_order = ["un_news", "bbc", "aljazeera", "reuters", "cnn", "fox", "abc", "skynews", "usgs", "gdacs", "nws"]
        targets = priority_order if source == "all" else [source.lower()]

        for name in targets:
            cfg = sources_cfg.get(name, {})
            if not cfg.get("enabled", True):
                continue
            try:
                articles = build_source(name, cfg).fetch()
                new, skipped = bulk_insert(articles)
                logger.info(f"collect [{name}]: {new} new, {skipped} skipped")
            except Exception as e:
                logger.error(f"collect [{name}] failed: {e}")
    finally:
        set_pipeline_state("collect", False)


def _run_analyze() -> None:
    set_pipeline_state("analyze", True)
    try:
        from analyst.filter import run_analysis
        from collector.store import init_db
        init_db()
        summary = run_analysis(api_key=_get_api_key())
        logger.info(f"analyze summary: {summary}")
    except Exception as e:
        logger.error(f"analyze failed: {e}")
    finally:
        set_pipeline_state("analyze", False)


def _run_write(tier: str) -> None:
    set_pipeline_state("write", True)
    try:
        from writer.reporter import run_writer
        from collector.store import init_db
        init_db()
        tier_arg = None if tier.lower() == "all" else tier.upper()
        result = run_writer(api_key=_get_api_key(), tier=tier_arg)
        logger.info(f"write result: {result}")
    except Exception as e:
        logger.error(f"write failed: {e}")
    finally:
        set_pipeline_state("write", False)


@router.post("/pipeline/collect", dependencies=[Depends(_verify_key)])
def trigger_collect(
    source: str = "all",
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    state = get_pipeline_state()
    if state["collect"]:
        raise HTTPException(status_code=409, detail="Collection already running")
    valid = {"all", "un_news", "bbc", "aljazeera", "reuters", "cnn", "fox", "abc", "skynews", "usgs", "gdacs", "nws"}
    if source not in valid:
        raise HTTPException(status_code=400, detail=f"Invalid source. Must be one of: {valid}")
    background_tasks.add_task(_run_collect, source)
    return {"status": "started", "stage": "collect", "source": source}


@router.post("/pipeline/analyze", dependencies=[Depends(_verify_key)])
def trigger_analyze(background_tasks: BackgroundTasks = BackgroundTasks()):
    state = get_pipeline_state()
    if state["analyze"]:
        raise HTTPException(status_code=409, detail="Analysis already running")
    background_tasks.add_task(_run_analyze)
    return {"status": "started", "stage": "analyze"}


@router.post("/pipeline/write", dependencies=[Depends(_verify_key)])
def trigger_write(
    tier: str = "all",
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    state = get_pipeline_state()
    if state["write"]:
        raise HTTPException(status_code=409, detail="Writer already running")
    valid = {"all", "flash", "priority", "routine"}
    if tier.lower() not in valid:
        raise HTTPException(status_code=400, detail=f"Invalid tier. Must be one of: {valid}")
    background_tasks.add_task(_run_write, tier)
    return {"status": "started", "stage": "write", "tier": tier}


@router.get("/pipeline/status")
def pipeline_status():
    state = get_pipeline_state()
    return {
        "collect": "running" if state["collect"] else "idle",
        "analyze": "running" if state["analyze"] else "idle",
        "write": "running" if state["write"] else "idle",
    }
