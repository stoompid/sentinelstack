from __future__ import annotations

import json
import os
from typing import List

import psycopg2
import psycopg2.extras

from collector.base import Article

_VALID_STAGES = {"collect", "analyze", "write"}


def get_conn():
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        raise RuntimeError("DATABASE_URL environment variable not set. Add it to config/.env")
    return psycopg2.connect(url, cursor_factory=psycopg2.extras.RealDictCursor)


def init_db() -> None:
    """Create all tables if they don't exist."""
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS articles (
            article_id   TEXT PRIMARY KEY,
            content_hash TEXT NOT NULL,
            source       TEXT NOT NULL,
            title        TEXT NOT NULL,
            summary      TEXT,
            url          TEXT,
            published_at TEXT,
            collected_at TEXT NOT NULL,
            country      TEXT,
            categories   TEXT,
            latitude     FLOAT,
            longitude    FLOAT,
            magnitude    FLOAT,
            analyzed     INTEGER DEFAULT 0
        )
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_articles_analyzed ON articles(analyzed)
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS scored_events (
            event_id         TEXT PRIMARY KEY,
            article_id       TEXT NOT NULL,
            title            TEXT NOT NULL,
            country          TEXT,
            category         TEXT,
            severity         INTEGER,
            tier             TEXT,
            is_noise         INTEGER DEFAULT 0,
            gemini_rationale TEXT,
            scored_at        TEXT NOT NULL,
            reported         INTEGER DEFAULT 0
        )
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_events_reported ON scored_events(reported, is_noise)
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            report_id    TEXT PRIMARY KEY,
            tier         TEXT NOT NULL,
            title        TEXT NOT NULL,
            situation    TEXT,
            impact       TEXT,
            action       TEXT,
            distro       TEXT DEFAULT '',
            event_ids    TEXT,
            generated_at TEXT NOT NULL,
            printed      INTEGER DEFAULT 0
        )
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_reports_tier ON reports(tier, printed)
    """)

    # Single-row table tracking which pipeline stages are currently running.
    # Survives worker restarts and works with multi-worker deployments.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS pipeline_state (
            id               INTEGER PRIMARY KEY DEFAULT 1,
            collect_running  BOOLEAN DEFAULT FALSE,
            analyze_running  BOOLEAN DEFAULT FALSE,
            write_running    BOOLEAN DEFAULT FALSE
        )
    """)

    cur.execute("""
        INSERT INTO pipeline_state (id, collect_running, analyze_running, write_running)
        VALUES (1, FALSE, FALSE, FALSE)
        ON CONFLICT (id) DO NOTHING
    """)

    conn.commit()
    cur.close()
    conn.close()


def bulk_insert(articles: List[Article]) -> tuple[int, int]:
    """Insert a batch of articles in a single transaction. Returns (new_count, skipped_count)."""
    if not articles:
        return 0, 0

    conn = get_conn()
    cur = conn.cursor()
    new, skipped = 0, 0
    try:
        for a in articles:
            cur.execute(
                """
                INSERT INTO articles
                    (article_id, content_hash, source, title, summary, url,
                     published_at, collected_at, country, categories,
                     latitude, longitude, magnitude, analyzed)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,0)
                ON CONFLICT (article_id) DO NOTHING
                """,
                (
                    a.article_id,
                    a.content_hash,
                    a.source,
                    a.title,
                    a.summary,
                    a.url,
                    a.published_at.isoformat() if a.published_at else None,
                    a.collected_at.isoformat(),
                    a.country,
                    json.dumps(a.categories),
                    a.latitude,
                    a.longitude,
                    a.magnitude,
                ),
            )
            if cur.rowcount == 1:
                new += 1
            else:
                skipped += 1
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

    return new, skipped


def get_pipeline_state() -> dict:
    """Return current running state for all pipeline stages."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT collect_running, analyze_running, write_running FROM pipeline_state WHERE id = 1"
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    if row is None:
        return {"collect": False, "analyze": False, "write": False}
    return {
        "collect": bool(row["collect_running"]),
        "analyze": bool(row["analyze_running"]),
        "write": bool(row["write_running"]),
    }


def set_pipeline_state(stage: str, running: bool) -> None:
    """Mark a pipeline stage as running (True) or idle (False)."""
    if stage not in _VALID_STAGES:
        raise ValueError(f"Invalid pipeline stage: {stage!r}. Must be one of {_VALID_STAGES}")
    col = f"{stage}_running"
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(f"UPDATE pipeline_state SET {col} = %s WHERE id = 1", (running,))
    conn.commit()
    cur.close()
    conn.close()
