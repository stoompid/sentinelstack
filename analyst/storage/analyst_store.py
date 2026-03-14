"""
Analyst storage — writes ScoredEvent rows to sentinel_reports.db.
"""

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from analyst.models import ScoredEvent

DB_PATH = Path(__file__).parents[2] / "data" / "raw" / "sentinel_reports.db"

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS scored_events (
    event_id          TEXT PRIMARY KEY,
    article_id        TEXT NOT NULL,
    source_name       TEXT,
    title             TEXT,
    summary           TEXT,
    published_at      TEXT,
    countries         TEXT,
    categories        TEXT,
    severity_score    INTEGER,
    is_noise          INTEGER,
    nearest_city_id   TEXT,
    nearest_city_name TEXT,
    distance_km       REAL,
    alert_tier        TEXT,
    analyzed_at       TEXT NOT NULL,
    reported          INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_alert_tier ON scored_events(alert_tier);
CREATE INDEX IF NOT EXISTS idx_reported   ON scored_events(reported);
"""

INSERT_SQL = """
INSERT OR IGNORE INTO scored_events (
    event_id, article_id, source_name, title, summary, published_at,
    countries, categories, severity_score, is_noise,
    nearest_city_id, nearest_city_name, distance_km, alert_tier, analyzed_at
) VALUES (
    :event_id, :article_id, :source_name, :title, :summary, :published_at,
    :countries, :categories, :severity_score, :is_noise,
    :nearest_city_id, :nearest_city_name, :distance_km, :alert_tier, :analyzed_at
)
"""


def _get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.executescript(CREATE_SQL)
    conn.commit()
    return conn


def store_scored_events(events: List[ScoredEvent]) -> int:
    """
    Insert ScoredEvent rows using INSERT OR IGNORE.

    Returns count of newly stored rows.
    """
    if not events:
        return 0
    conn = _get_connection()
    analyzed_at = datetime.now(tz=timezone.utc).isoformat()
    rows = []
    for e in events:
        rows.append({
            "event_id": str(uuid.uuid4()),
            "article_id": e.article_id,
            "source_name": e.source_name,
            "title": e.title,
            "summary": e.summary,
            "published_at": e.published_at,
            "countries": e.countries,
            "categories": e.categories,
            "severity_score": e.severity_score,
            "is_noise": 1 if e.is_noise else 0,
            "nearest_city_id": e.nearest_city_id,
            "nearest_city_name": e.nearest_city_name,
            "distance_km": e.distance_km,
            "alert_tier": e.alert_tier,
            "analyzed_at": analyzed_at,
        })
    before = conn.execute("SELECT COUNT(*) FROM scored_events").fetchone()[0]
    conn.executemany(INSERT_SQL, rows)
    conn.commit()
    after = conn.execute("SELECT COUNT(*) FROM scored_events").fetchone()[0]
    conn.close()
    return after - before
