from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Query

from collector.store import get_conn

router = APIRouter()


@router.get("/articles")
def get_articles(limit: int = Query(50, le=200), tier: Optional[str] = None):
    """Recent articles joined with scoring data where available."""
    conn = get_conn()
    cur = conn.cursor()

    if tier and tier.upper() != "ALL":
        cur.execute(
            """
            SELECT a.article_id, a.source, a.title, a.country, a.categories,
                   a.published_at, a.collected_at, a.url, a.analyzed,
                   a.latitude, a.longitude, a.magnitude,
                   se.severity, se.tier, se.is_noise, se.gemini_rationale
            FROM articles a
            LEFT JOIN scored_events se ON se.article_id = a.article_id
            WHERE se.tier = %s
            ORDER BY a.collected_at DESC
            LIMIT %s
            """,
            (tier.upper(), limit),
        )
    else:
        cur.execute(
            """
            SELECT a.article_id, a.source, a.title, a.country, a.categories,
                   a.published_at, a.collected_at, a.url, a.analyzed,
                   a.latitude, a.longitude, a.magnitude,
                   se.severity, se.tier, se.is_noise, se.gemini_rationale
            FROM articles a
            LEFT JOIN scored_events se ON se.article_id = a.article_id
            ORDER BY a.collected_at DESC
            LIMIT %s
            """,
            (limit,),
        )

    rows = cur.fetchall()
    cur.close()
    conn.close()

    results = []
    for row in rows:
        r = dict(row)
        try:
            r["categories"] = json.loads(r["categories"] or "[]")
        except Exception:
            r["categories"] = []
        results.append(r)

    return results
