"""
Event grouper — clusters same-country + same-category events within 6h.

Returns a list of groups; each group is a list of event dicts.
Single-event groups are fine — the writer handles both.
"""

import json
from datetime import datetime, timedelta
from typing import List, Dict

SIX_HOURS = timedelta(hours=6)


def _parse_dt(iso: str) -> datetime:
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return datetime.min


def _first_category(categories_json: str) -> str:
    try:
        cats = json.loads(categories_json or "[]")
        return cats[0].lower() if cats else ""
    except (json.JSONDecodeError, IndexError):
        return ""


def _first_country(countries_json: str) -> str:
    try:
        countries = json.loads(countries_json or "[]")
        return countries[0].lower() if countries else ""
    except (json.JSONDecodeError, IndexError):
        return ""


def group_events(events: List[dict]) -> List[List[dict]]:
    """
    Cluster events by (country, category) within a 6-hour window.

    Events without country or category land in their own singleton group.
    """
    groups: List[List[dict]] = []
    ungrouped = list(events)

    while ungrouped:
        seed = ungrouped.pop(0)
        group = [seed]
        seed_dt = _parse_dt(seed.get("analyzed_at") or "")
        seed_country = _first_country(seed.get("countries", "[]"))
        seed_category = _first_category(seed.get("categories", "[]"))

        if not seed_country or not seed_category:
            groups.append(group)
            continue

        remaining = []
        for candidate in ungrouped:
            cand_dt = _parse_dt(candidate.get("analyzed_at") or "")
            cand_country = _first_country(candidate.get("countries", "[]"))
            cand_category = _first_category(candidate.get("categories", "[]"))
            if (
                cand_country == seed_country
                and cand_category == seed_category
                and abs(cand_dt - seed_dt) <= SIX_HOURS
            ):
                group.append(candidate)
            else:
                remaining.append(candidate)

        ungrouped = remaining
        groups.append(group)

    return groups
