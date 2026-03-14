"""
Reporter loader — reads unreported scored events from sentinel_reports.db.
"""

import sqlite3
from pathlib import Path
from typing import List

DB_PATH = Path(__file__).parents[1] / "data" / "raw" / "sentinel_reports.db"

SELECT_SQL = """
SELECT event_id, article_id, source_name, title, summary, published_at,
       countries, categories, severity_score, is_noise,
       nearest_city_id, nearest_city_name, distance_km, alert_tier, analyzed_at
FROM scored_events
WHERE reported = 0
  AND is_noise = 0
  {tier_filter}
ORDER BY severity_score DESC, analyzed_at ASC
"""


def load_unreported(tier: str = "all") -> List[dict]:
    """Return unreported scored_events rows.

    Args:
        tier: "all", "flash", "priority", or "routine"
    """
    if not DB_PATH.exists():
        return []

    if tier == "all":
        tier_filter = ""
    else:
        tier_filter = f"AND alert_tier = '{tier}'"

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(SELECT_SQL.format(tier_filter=tier_filter)).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def mark_reported(event_ids: List[str]) -> None:
    """Set reported=1 for given event IDs."""
    if not event_ids or not DB_PATH.exists():
        return
    conn = sqlite3.connect(str(DB_PATH))
    conn.executemany(
        "UPDATE scored_events SET reported=1 WHERE event_id=?",
        [(eid,) for eid in event_ids],
    )
    conn.commit()
    conn.close()
