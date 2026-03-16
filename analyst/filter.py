from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List

from analyst.llm import call_llm, configure_llm, LLMError
from collector.store import get_conn

logger = logging.getLogger(__name__)

MODEL_FAST = "auto"

# ── Monitored cities & proximity filter ──────────────────────────────────────

_CITIES: list[dict] | None = None
_RADIUS_MILES: float = 50.0
_MONITORED_COUNTRIES: set[str] | None = None

# Keywords that indicate global-impact events — bypass proximity filter
_GLOBAL_KEYWORDS = {
    "war", "invasion", "missile", "airstrike", "nuclear", "coup", "sanctions",
    "tariff", "earthquake", "tsunami", "eruption", "hurricane", "cyclone",
    "typhoon", "terror", "bombing", "cyberattack", "pandemic", "ceasefire",
    "martial law", "assassination", "hostage", "armed conflict", "civil war",
}


def _load_cities() -> tuple[list[dict], set[str]]:
    """Load monitored cities from config/cities.json."""
    global _CITIES, _MONITORED_COUNTRIES, _RADIUS_MILES
    if _CITIES is not None:
        return _CITIES, _MONITORED_COUNTRIES

    cities_path = Path(__file__).resolve().parent.parent / "config" / "cities.json"
    try:
        data = json.loads(cities_path.read_text())
        _CITIES = data.get("cities", [])
        _RADIUS_MILES = data.get("radius_miles", 50.0)
        _MONITORED_COUNTRIES = {c["country"].lower().strip() for c in _CITIES}
        logger.info(f"Proximity filter: {len(_CITIES)} cities, {_RADIUS_MILES}mi radius, {len(_MONITORED_COUNTRIES)} countries")
    except Exception as e:
        logger.warning(f"Failed to load cities.json: {e} — proximity filter disabled")
        _CITIES = []
        _MONITORED_COUNTRIES = set()

    return _CITIES, _MONITORED_COUNTRIES


def _haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine distance between two points in miles."""
    R = 3958.8  # Earth radius in miles
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _is_near_monitored_city(lat: float | None, lon: float | None, country: str, title: str, summary: str) -> tuple[bool, str]:
    """Check if an article is relevant based on proximity to monitored cities.

    Returns (passes_filter, reason).
    Articles pass if:
    1. They have coordinates within radius of a monitored city
    2. Their country matches a monitored city's country
    3. They contain global-impact keywords (bypass proximity)
    """
    cities, monitored_countries = _load_cities()

    if not cities:
        return True, "no cities configured"

    # Check for global-impact keywords — these always pass
    text_lower = f"{title} {summary}".lower()
    for kw in _GLOBAL_KEYWORDS:
        if kw in text_lower:
            return True, f"global-impact keyword: {kw}"

    # Check coordinate proximity
    if lat is not None and lon is not None:
        for city in cities:
            dist = _haversine_miles(lat, lon, city["lat"], city["lon"])
            if dist <= _RADIUS_MILES:
                return True, f"within {dist:.0f}mi of {city['name']}"

    # Check country match
    country_lower = country.lower().strip()
    if country_lower and country_lower in monitored_countries:
        return True, f"monitored country: {country}"

    return False, "not near any monitored city"


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


def is_noise(title: str, summary: str, country: str, categories: list) -> tuple[bool, str]:
    prompt = f"""You are an intelligence filter for a GSOC at a major technology company. Your job is to sort through news articles and ONLY keep high-impact events that immediately disrupt a city or change global geopolitics.

KEEP (NOT NOISE):
- Natural Disasters: Wildfires, earthquakes, major hurricanes, or floods
- Major Geopolitical Actions: Military invasions, large-scale troop deployments, new international tariffs, sanctions
- Severe Local Disruptions: Major law enforcement actions (like city-wide raids), terror attacks, infrastructure collapses (like city-wide blackouts), cyberattacks on critical infrastructure
- Direct threats to tech operations: attacks near corporate campuses or data centers, supply chain disruptions

FILTER OUT (NOISE):
- Routine politics (elections, referendums, rallies, debates, legislative votes)
- Standard diplomacy (trade talks, summit meetings, diplomatic statements)
- Minor protests or strikes
- Updates on individual people (health of leaders, celebrities, arrests of individuals)
- Routine crime or local accidents
- Sports, entertainment, lifestyle, product reviews
- Stock market fluctuations, earnings reports
- Minor local weather, seasonal forecasts
- Opinion pieces, editorials, analysis without new events

Title: {title}
Summary: {summary[:300]}
Country: {country}
Categories: {', '.join(categories)}

Respond with JSON only:
{{"is_noise": true or false, "reason": "one sentence"}}"""

    result = call_llm(MODEL_FAST, prompt, temperature=0)
    return bool(result.get("is_noise", False)), result.get("reason", "No reason provided")


def score_severity(title: str, summary: str, country: str, categories: list) -> tuple[int, str, str]:
    prompt = f"""You are a GSOC analyst at a major technology company scoring physical threat severity for employee safety, executive protection, travel risk, and tech industry operations.

Score 1-10:
1-3: Low — situational awareness only, no operational impact
4-6: Moderate — monitor closely, may affect employee travel, office operations, or supply chain
7-8: High — recommend operational precautions, brief security leadership, potential impact to company sites or personnel
9-10: Critical — immediate threat to personnel, offices, or operations — escalate now

Title: {title}
Summary: {summary[:300]}
Country: {country}
Categories: {', '.join(categories)}

Respond with JSON only:
{{"severity": <integer 1-10>, "rationale": "one sentence"}}"""

    result = call_llm(MODEL_FAST, prompt, temperature=0)
    severity = max(1, min(10, int(result.get("severity", 3))))
    rationale = result.get("rationale", "No rationale provided")
    return severity, _assign_tier(severity), rationale


def _load_recent_content_hashes(conn) -> set:
    """Return content_hashes for all analyzed articles collected in the last 24h."""
    cutoff = (datetime.now(tz=timezone.utc) - timedelta(hours=24)).isoformat()
    cur = conn.cursor()
    cur.execute(
        "SELECT content_hash FROM articles WHERE analyzed = 1 AND collected_at > %s",
        (cutoff,),
    )
    return {row["content_hash"] for row in cur.fetchall()}


def run_analysis(api_key: str, dry_run: bool = False) -> dict:
    configure_llm(api_key)
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT * FROM articles WHERE analyzed = 0 ORDER BY collected_at ASC")
    rows = cur.fetchall()

    if not rows:
        cur.close()
        conn.close()
        return {"analyzed": 0, "noise": 0, "flash": 0, "priority": 0, "routine": 0, "filtered_proximity": 0}

    recent_hashes = _load_recent_content_hashes(conn)
    summary = {"analyzed": 0, "noise": 0, "flash": 0, "priority": 0, "routine": 0, "filtered_proximity": 0}

    for row in rows:
        article_id = row["article_id"]
        content_hash = row["content_hash"]
        title = row["title"] or ""
        summary_text = row["summary"] or ""
        country = row["country"] or ""
        categories = json.loads(row["categories"] or "[]")
        category = categories[0] if categories else "unknown"
        lat = row.get("latitude")
        lon = row.get("longitude")

        # Dedup check
        if content_hash in recent_hashes:
            if not dry_run:
                cur.execute("UPDATE articles SET analyzed=1 WHERE article_id=%s", (article_id,))
                conn.commit()
            continue

        # ── Proximity filter (before LLM) ──
        passes, prox_reason = _is_near_monitored_city(lat, lon, country, title, summary_text)
        if not passes:
            summary["filtered_proximity"] += 1
            if not dry_run:
                cur.execute("UPDATE articles SET analyzed=1 WHERE article_id=%s", (article_id,))
                conn.commit()
            recent_hashes.add(content_hash)
            continue

        logger.debug(f"Proximity pass: {prox_reason} — {title[:60]}")

        # ── LLM noise check ──
        try:
            noise, noise_reason = is_noise(title, summary_text, country, categories)
        except LLMError as e:
            logger.warning(f"LLM error on noise check for {article_id}: {e} — skipping article")
            continue

        if noise:
            summary["noise"] += 1
            if not dry_run:
                cur.execute("UPDATE articles SET analyzed=1 WHERE article_id=%s", (article_id,))
                conn.commit()
            recent_hashes.add(content_hash)
            continue

        # ── LLM severity score ──
        try:
            severity, tier, rationale = score_severity(title, summary_text, country, categories)
        except LLMError as e:
            logger.warning(f"LLM error on severity score for {article_id}: {e} — skipping article")
            continue

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
    logger.info(f"Proximity filter removed {summary['filtered_proximity']} irrelevant articles before LLM")
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
