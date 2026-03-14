"""
SQLite storage for raw articles.

Creates data/raw/sentinel.db if not exists.
Uses INSERT OR IGNORE so article_id (PK) prevents duplicates.
"""

import json
import sqlite3
from pathlib import Path
from typing import List

from collector.sources.base import RawArticle
from collector.utils.logging import get_logger

logger = get_logger(__name__)

DB_PATH = Path(__file__).parents[2] / "data" / "raw" / "sentinel.db"

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS raw_articles (
    article_id      TEXT PRIMARY KEY,
    source_name     TEXT NOT NULL,
    source_type     TEXT NOT NULL,
    source_url      TEXT NOT NULL,
    title           TEXT NOT NULL,
    summary         TEXT NOT NULL,
    full_text       TEXT,
    url             TEXT DEFAULT '',
    published_at    TEXT,
    collected_at    TEXT NOT NULL,
    countries       TEXT NOT NULL DEFAULT '[]',
    regions         TEXT NOT NULL DEFAULT '[]',
    categories      TEXT NOT NULL DEFAULT '[]',
    keywords        TEXT NOT NULL DEFAULT '[]',
    event_latitude  REAL,
    event_longitude REAL,
    event_magnitude REAL,
    raw_data        TEXT NOT NULL DEFAULT '{}',
    analyzed        INTEGER NOT NULL DEFAULT 0,
    content_hash    TEXT
);
CREATE INDEX IF NOT EXISTS idx_source   ON raw_articles(source_name);
CREATE INDEX IF NOT EXISTS idx_analyzed ON raw_articles(analyzed);
CREATE INDEX IF NOT EXISTS idx_coords   ON raw_articles(event_latitude, event_longitude)
    WHERE event_latitude IS NOT NULL;
"""

INSERT_SQL = """
INSERT OR IGNORE INTO raw_articles (
    article_id, source_name, source_type, source_url,
    title, summary, full_text, url,
    published_at, collected_at,
    countries, regions, categories, keywords,
    event_latitude, event_longitude, event_magnitude,
    raw_data, content_hash
) VALUES (
    :article_id, :source_name, :source_type, :source_url,
    :title, :summary, :full_text, :url,
    :published_at, :collected_at,
    :countries, :regions, :categories, :keywords,
    :event_latitude, :event_longitude, :event_magnitude,
    :raw_data, :content_hash
)
"""


def _get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.executescript(CREATE_TABLE_SQL)
    conn.commit()
    return conn


def store_articles(articles: List[RawArticle]) -> int:
    """
    Insert articles using INSERT OR IGNORE.

    Returns:
        Count of newly stored rows (ignores duplicates).
    """
    if not articles:
        return 0

    conn = _get_connection()
    rows = []
    for a in articles:
        rows.append({
            "article_id": a.article_id,
            "source_name": a.source_name,
            "source_type": a.source_type.value,
            "source_url": a.source_url,
            "title": a.title,
            "summary": a.summary,
            "full_text": a.full_text,
            "url": a.url,
            "published_at": a.published_at.isoformat() if a.published_at else None,
            "collected_at": a.collected_at.isoformat(),
            "countries": json.dumps(a.countries),
            "regions": json.dumps(a.regions),
            "categories": json.dumps(a.categories),
            "keywords": json.dumps(a.keywords),
            "event_latitude": a.event_latitude,
            "event_longitude": a.event_longitude,
            "event_magnitude": a.event_magnitude,
            "raw_data": json.dumps(a.raw_data),
            "content_hash": a.content_hash,
        })

    before = conn.execute("SELECT COUNT(*) FROM raw_articles").fetchone()[0]
    conn.executemany(INSERT_SQL, rows)
    conn.commit()
    after = conn.execute("SELECT COUNT(*) FROM raw_articles").fetchone()[0]
    conn.close()

    new_count = after - before
    logger.info("stored_articles", new=new_count, total_submitted=len(articles))
    return new_count
