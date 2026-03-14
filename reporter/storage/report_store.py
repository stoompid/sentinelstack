"""
Reporter storage — saves generated reports to sentinel_reports.db.
"""

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List

DB_PATH = Path(__file__).parents[2] / "data" / "raw" / "sentinel_reports.db"

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS reports (
    report_id    TEXT PRIMARY KEY,
    event_ids    TEXT NOT NULL,   -- JSON array of event_id strings
    alert_tier   TEXT NOT NULL,
    title        TEXT NOT NULL,
    report_text  TEXT NOT NULL,
    generated_at TEXT NOT NULL
);
"""

INSERT_SQL = """
INSERT OR IGNORE INTO reports (report_id, event_ids, alert_tier, title, report_text, generated_at)
VALUES (:report_id, :event_ids, :alert_tier, :title, :report_text, :generated_at)
"""


def _get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.executescript(CREATE_SQL)
    conn.commit()
    return conn


def store_report(event_ids: List[str], alert_tier: str, title: str, report_text: str) -> str:
    """
    Persist a generated report.

    Returns the new report_id.
    """
    conn = _get_connection()
    import json
    report_id = str(uuid.uuid4())
    conn.execute(INSERT_SQL, {
        "report_id": report_id,
        "event_ids": json.dumps(event_ids),
        "alert_tier": alert_tier,
        "title": title,
        "report_text": report_text,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
    })
    conn.commit()
    conn.close()
    return report_id
