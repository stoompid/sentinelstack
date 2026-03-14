from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from fastapi import APIRouter

from collector.base import build_source

router = APIRouter()

CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "sources.json"
PRIORITY_ORDER = ["un_news", "bbc", "usgs", "gdacs", "nws"]


def _check_one(name: str, cfg: dict) -> tuple[str, dict]:
    if not cfg.get("enabled", True):
        return name, {"status": "disabled", "latency_ms": None}
    try:
        src = build_source(name, cfg)
        t0 = time.perf_counter()
        ok = src.health_check()
        latency = round((time.perf_counter() - t0) * 1000)
        return name, {"status": "ok" if ok else "fail", "latency_ms": latency}
    except Exception as e:
        return name, {"status": "error", "latency_ms": None, "error": str(e)}


@router.get("/health")
def health_check():
    """Check reachability of all OSINT sources (parallel, max 10s)."""
    with open(CONFIG_PATH) as f:
        sources_cfg = json.load(f)

    results: dict = {}
    with ThreadPoolExecutor(max_workers=len(PRIORITY_ORDER)) as executor:
        futures = {
            executor.submit(_check_one, name, sources_cfg.get(name, {})): name
            for name in PRIORITY_ORDER
        }
        for future in as_completed(futures):
            name, result = future.result()
            results[name] = result

    # Return in priority order
    return {name: results[name] for name in PRIORITY_ORDER if name in results}
