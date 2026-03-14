"""
Analyst Agent data models.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class ProximityResult:
    """Result of a proximity check against the watchlist."""
    city_id: str
    city_name: str
    distance_km: float
    alert_tier: str  # "flash" | "priority" | "routine" | "none"


@dataclass
class ScoredEvent:
    """A RawArticle that has been through the analyst pipeline."""
    article_id: str
    source_name: str
    title: str
    summary: str
    published_at: Optional[str]
    countries: str          # JSON string
    categories: str         # JSON string
    severity_score: int     # 1–10
    is_noise: bool
    nearest_city_id: Optional[str]
    nearest_city_name: Optional[str]
    distance_km: Optional[float]
    alert_tier: str         # "flash" | "priority" | "routine" | "none"
