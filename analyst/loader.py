"""
Analyst loader — reads unanalyzed articles from SQLite.
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List

from collector.sources.base import RawArticle, SourceType

DB_PATH = Path(__file__).parents[1] / "data" / "raw" / "sentinel.db"

SELECT_SQL = """
SELECT article_id, source_name, source_type, source_url,
       title, summary, full_text, url,
       published_at, collected_at,
       countries, regions, categories, keywords,
       event_latitude, event_longitude, event_magnitude,
       raw_data, content_hash
FROM raw_articles
WHERE analyzed = 0
ORDER BY collected_at ASC
"""


def load_unanalyzed() -> List[RawArticle]:
    """Return all raw_articles rows where analyzed=0."""
    if not DB_PATH.exists():
        return []
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(SELECT_SQL).fetchall()
    conn.close()

    articles = []
    for row in rows:
        articles.append(RawArticle(
            article_id=row["article_id"],
            source_name=row["source_name"],
            source_type=SourceType(row["source_type"]),
            source_url=row["source_url"],
            title=row["title"],
            summary=row["summary"],
            full_text=row["full_text"],
            url=row["url"] or "",
            published_at=datetime.fromisoformat(row["published_at"]) if row["published_at"] else None,
            collected_at=datetime.fromisoformat(row["collected_at"]),
            countries=json.loads(row["countries"] or "[]"),
            regions=json.loads(row["regions"] or "[]"),
            categories=json.loads(row["categories"] or "[]"),
            keywords=json.loads(row["keywords"] or "[]"),
            event_latitude=row["event_latitude"],
            event_longitude=row["event_longitude"],
            event_magnitude=row["event_magnitude"],
            content_hash=row["content_hash"],
            raw_data=json.loads(row["raw_data"] or "{}"),
        ))
    return articles


def mark_analyzed(article_ids: List[str]) -> None:
    """Set analyzed=1 for the given article IDs."""
    if not article_ids or not DB_PATH.exists():
        return
    conn = sqlite3.connect(str(DB_PATH))
    conn.executemany(
        "UPDATE raw_articles SET analyzed=1 WHERE article_id=?",
        [(aid,) for aid in article_ids],
    )
    conn.commit()
    conn.close()
