from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from collector.store import get_conn

router = APIRouter()


@router.get("/reports")
def get_reports(
    tier: Optional[str] = None,
    limit: int = Query(50, le=200),
):
    """Retrieve generated crisis-comms reports, newest first."""
    conn = get_conn()
    cur = conn.cursor()

    if tier and tier.upper() != "ALL":
        cur.execute(
            """
            SELECT * FROM reports
            WHERE tier = %s
            ORDER BY generated_at DESC
            LIMIT %s
            """,
            (tier.upper(), limit),
        )
    else:
        cur.execute(
            "SELECT * FROM reports ORDER BY generated_at DESC LIMIT %s",
            (limit,),
        )

    rows = cur.fetchall()
    cur.close()
    conn.close()

    return [dict(r) for r in rows]
