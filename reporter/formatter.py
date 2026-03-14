"""
Report formatter — assembles final report string with tier header.
"""

from datetime import datetime, timezone
from typing import List


TIER_LABELS = {
    "flash": "FLASH",
    "priority": "PRIORITY",
    "routine": "ROUTINE",
    "none": "INFO",
}


def format_report(events: List[dict], sections: dict) -> str:
    """
    Assemble the final report string.

    Args:
        events:   The event group (1 or more scored_events rows).
        sections: Dict with situation/impact/action keys from writer.py.

    Returns:
        Formatted report string ready for output or storage.
    """
    lead = events[0]
    tier = lead.get("alert_tier", "none")
    label = TIER_LABELS.get(tier, tier.upper())
    title = lead.get("title", "")
    nearest_city = lead.get("nearest_city_name")
    distance_km = lead.get("distance_km")
    generated = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    proximity_line = ""
    if nearest_city and distance_km is not None:
        proximity_line = f"Watchlist Proximity: {nearest_city} ({distance_km:.0f} km)\n"

    lines = [
        f"[{label}] — {title}",
        f"Generated: {generated}",
    ]
    if proximity_line:
        lines.append(proximity_line.rstrip())
    lines += [
        "",
        "SITUATION",
        sections.get("situation", ""),
        "",
        "IMPACT",
        sections.get("impact", ""),
        "",
        "ACTION",
        sections.get("action", ""),
    ]

    return "\n".join(lines)
