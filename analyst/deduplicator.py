"""
Cross-source deduplication.

Two articles are duplicates if:
  - title token overlap > 80%  AND
  - published_at within 6 hours of each other

When duplicates are found, keep the article from the source with the
lowest priority integer (highest quality source).
"""

import json
from datetime import timedelta
from pathlib import Path
from typing import List, Set

from collector.sources.base import RawArticle

SOURCES_CFG = Path(__file__).parents[1] / "config" / "sources.json"
SIX_HOURS = timedelta(hours=6)


def _source_priority(source_name: str, priority_map: dict) -> int:
    """Return priority integer for a source name (lower = better)."""
    for key, cfg in priority_map.items():
        if cfg.get("name") == source_name:
            return cfg.get("priority", 99)
    return 99


def _token_overlap(title_a: str, title_b: str) -> float:
    """Return Jaccard overlap of word tokens (lowercased)."""
    tokens_a: Set[str] = set(title_a.lower().split())
    tokens_b: Set[str] = set(title_b.lower().split())
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)


def deduplicate(articles: List[RawArticle]) -> List[RawArticle]:
    """
    Remove duplicate articles, keeping the highest-priority source copy.

    Returns the deduplicated list.
    """
    cfg = json.loads(SOURCES_CFG.read_text(encoding="utf-8"))
    priority_map = cfg.get("sources", {})

    # Sort by source priority so we process best sources first
    sorted_articles = sorted(
        articles,
        key=lambda a: _source_priority(a.source_name, priority_map),
    )

    kept: List[RawArticle] = []
    for candidate in sorted_articles:
        is_dup = False
        for existing in kept:
            # Time check — strip tzinfo so naive and aware datetimes can be compared
            if candidate.published_at and existing.published_at:
                a = candidate.published_at.replace(tzinfo=None)
                b = existing.published_at.replace(tzinfo=None)
                if abs(a - b) > SIX_HOURS:
                    continue

            overlap = _token_overlap(candidate.title, existing.title)
            if overlap > 0.80:
                is_dup = True
                break

        if not is_dup:
            kept.append(candidate)

    return kept
