from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import List

from groq import Groq

from analyst.llm import call_llm
from collector.store import get_conn

logger = logging.getLogger(__name__)

MODEL_FAST = "llama-3.3-70b-versatile"


@dataclass
class ScoredEvent:
    event_id: str
    article_id: str
    title: str
    country: str
    category: str
    severity: int       # 1-10
    tier: str           # FLASH | PRIORITY | ROUTINE
    is_noise: bool
    gemini_rationale: str
    scored_at: datetime


def _assign_tier(severity: int) -> str:
    if severity >= 8:
        return "FLASH"
    if severity >= 5:
        return "PRIORITY"
    return "ROUTINE"


def is_noise(client: Groq, title: str, summary: str, country: str, categories: list) -> tuple[bool, str]:
    prompt = f"""You are a GSOC analyst. Determine if this article is noise for physical security and geopolitical threat intelligence.

NOISE = routine politics, economics, sports, entertainment, minor weather, stock markets, product launches, celebrity news, or events with zero physical security implications.

NOT NOISE = civil unrest, protests, riots, conflict escalation, terrorist attacks, coups, sanctions with operational impact, evacuations, natural disasters, seismic events, leadership travel risk.

Title: {title}
Summary: {summary[:300]}
Country: {country}
Categories: {', '.join(categories)}

Respond with JSON only:
{{"is_noise": true or false, "reason": "one sentence"}}"""

    result = call_llm(client, prompt, MODEL_FAST, temperature=0)
    return bool(result.get("is_noise", False)), result.get("reason", "No reason provided")


def score_severity(client: Groq, title: str, summary: str, country: str, categories: list) -> tuple[int, str, str]:
    prompt = f"""You are a GSOC analyst scoring physical threat severity for executive protection and travel risk.

Score 1-10:
1-3: Low — situational awareness only, no operational impact
4-6: Moderate — monitor closely, may affect travel or operations
7-8: High — recommend operational precautions, brief leadership
9-10: Critical — immediate threat to personnel or operations, escalate now

Title: {title}
Summary: {summary[:300]}
Country: {country}
Categories: {', '.join(categories)}

Respond with JSON only:
{{"severity": <integer 1-10>, "rationale": "one sentence"}}"""

    result = call_llm(client, prompt, MODEL_FAST, temperature=0)
    severity = max(1, min(10, int(result.get("severity", 3))))
    rationale = result.get("rationale", "No rationale provided")
    return severity, _assign_tier(severity), rationale


def _load_recent_content_hashes(conn) -> set:
    """Return content_hashes for all analyzed articles collected in the last 24h.

    Queries articles directly (not scored_events) so noise-classified articles
    are also caught and not re-processed.
    """
    cutoff = (datetime.now(tz=timezone.utc) - timedelta(hours=24)).isoformat()
    cur = conn.cursor()
    cur.execute(
        "SELECT content_hash FROM articles WHERE analyzed = 1 AND collected_at > %s",
        (cutoff,),
    )
    return {row["content_hash"] for row in cur.fetchall()}


def run_analysis(api_key: str, dry_run: bool = False) -> dict:
    client = Groq(api_key=api_key)
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT * FROM articles WHERE analyzed = 0 ORDER BY collected_at ASC")
    rows = cur.fetchall()

    if not rows:
        cur.close()
        conn.close()
        return {"analyzed": 0, "noise": 0, "flash": 0, "priority": 0, "routine": 0}

    recent_hashes = _load_recent_content_hashes(conn)
    summary = {"analyzed": 0, "noise": 0, "flash": 0, "priority": 0, "routine": 0}

    for row in rows:
        article_id = row["article_id"]
        content_hash = row["content_hash"]
        title = row["title"] or ""
        summary_text = row["summary"] or ""
        country = row["country"] or ""
        categories = json.loads(row["categories"] or "[]")
        category = categories[0] if categories else "unknown"

        if content_hash in recent_hashes:
            if not dry_run:
                cur.execute("UPDATE articles SET analyzed=1 WHERE article_id=%s", (article_id,))
                conn.commit()
            continue

        noise, noise_reason = is_noise(client, title, summary_text, country, categories)

        if noise:
            summary["noise"] += 1
            if not dry_run:
                cur.execute("UPDATE articles SET analyzed=1 WHERE article_id=%s", (article_id,))
                conn.commit()
            continue

        severity, tier, rationale = score_severity(client, title, summary_text, country, categories)

        scored = ScoredEvent(
            event_id=article_id,
            article_id=article_id,
            title=title,
            country=country,
            category=category,
            severity=severity,
            tier=tier,
            is_noise=False,
            gemini_rationale=rationale,
            scored_at=datetime.now(tz=timezone.utc),
        )

        summary["analyzed"] += 1
        summary[tier.lower()] += 1
        recent_hashes.add(content_hash)

        if not dry_run:
            _write_scored_event(cur, scored)
            cur.execute("UPDATE articles SET analyzed=1 WHERE article_id=%s", (article_id,))
            conn.commit()
        else:
            logger.info(f"[dry-run] {tier} ({severity}/10) — {title[:80]}")

    cur.close()
    conn.close()
    return summary


def _write_scored_event(cur, event: ScoredEvent) -> None:
    cur.execute(
        """
        INSERT INTO scored_events
            (event_id, article_id, title, country, category, severity, tier,
             is_noise, gemini_rationale, scored_at, reported)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,0)
        ON CONFLICT (event_id) DO UPDATE SET
            severity = EXCLUDED.severity,
            tier = EXCLUDED.tier,
            gemini_rationale = EXCLUDED.gemini_rationale,
            scored_at = EXCLUDED.scored_at
        """,
        (
            event.event_id, event.article_id, event.title, event.country,
            event.category, event.severity, event.tier, 0,
            event.gemini_rationale, event.scored_at.isoformat(),
        ),
    )
