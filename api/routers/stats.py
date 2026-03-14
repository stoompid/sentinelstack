from __future__ import annotations

from fastapi import APIRouter

from collector.store import get_conn

router = APIRouter()


@router.get("/stats")
def get_stats():
    """Dashboard summary stats: article counts, tier breakdown, last collected."""
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            COUNT(*) FILTER (WHERE collected_at::timestamptz > NOW() - INTERVAL '24 hours') AS articles_today,
            COUNT(*) AS articles_total
        FROM articles
    """)
    article_row = cur.fetchone()

    cur.execute("""
        SELECT tier, COUNT(*) as count
        FROM scored_events
        WHERE is_noise = 0 AND scored_at::timestamptz > NOW() - INTERVAL '24 hours'
        GROUP BY tier
    """)
    tier_rows = cur.fetchall()

    cur.execute("""
        SELECT COUNT(*) as count
        FROM reports
        WHERE generated_at::timestamptz > NOW() - INTERVAL '24 hours'
    """)
    reports_today = cur.fetchone()["count"]

    cur.execute("""
        SELECT MAX(collected_at) as last_collected FROM articles
    """)
    last_row = cur.fetchone()

    cur.close()
    conn.close()

    tier_counts = {"flash": 0, "priority": 0, "routine": 0}
    for row in tier_rows:
        key = (row["tier"] or "routine").lower()
        if key in tier_counts:
            tier_counts[key] = row["count"]

    return {
        "articles_today": article_row["articles_today"] or 0,
        "articles_total": article_row["articles_total"] or 0,
        "flash": tier_counts["flash"],
        "priority": tier_counts["priority"],
        "routine": tier_counts["routine"],
        "reports_today": reports_today or 0,
        "last_collected": last_row["last_collected"] if last_row else None,
    }


@router.get("/chart/events")
def get_chart_events():
    """Event volume per hour for the last 24 hours."""
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            DATE_TRUNC('hour', collected_at::timestamptz) AS hour,
            COUNT(*) AS count
        FROM articles
        WHERE collected_at::timestamptz > NOW() - INTERVAL '24 hours'
        GROUP BY hour
        ORDER BY hour ASC
    """)

    rows = cur.fetchall()
    cur.close()
    conn.close()

    return [
        {
            "hour": row["hour"].strftime("%H:%M") if row["hour"] else "",
            "count": row["count"],
        }
        for row in rows
    ]
