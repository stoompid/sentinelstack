from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


def generate_article_id(url: str, title: str) -> str:
    """SHA256 of '{url}|{title}', truncated to 16 hex chars."""
    raw = f"{url}|{title}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def generate_content_hash(title: str, summary: str) -> str:
    """SHA256 of lowercased '{title}|{summary}'."""
    raw = f"{title}|{summary}".lower()
    return hashlib.sha256(raw.encode()).hexdigest()


@dataclass
class Article:
    article_id: str
    content_hash: str
    source: str                        # "osac" | "reliefweb" | "usgs" | "gdacs"
    title: str
    summary: str
    url: str
    published_at: Optional[datetime]
    collected_at: datetime
    country: str
    categories: List[str] = field(default_factory=list)
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    magnitude: Optional[float] = None  # seismic only


class BaseSource(ABC):
    """Abstract base class for all OSINT collectors."""

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Source identifier string."""

    @abstractmethod
    def fetch(self) -> List[Article]:
        """Fetch articles from the source. Never raises — log and return []."""

    @abstractmethod
    def health_check(self) -> bool:
        """Return True if the source endpoint is reachable."""


def build_source(name: str, config: dict) -> "BaseSource":
    """Factory: construct the appropriate BaseSource from a name and config dict."""
    if name == "usgs":
        from collector.usgs import USGSSource
        return USGSSource(config)
    if name == "gdacs":
        from collector.gdacs import GDACSSource
        return GDACSSource(config)
    if name == "nws":
        from collector.nws import NWSSource
        return NWSSource(config)
    from collector.rss import GenericRSSSource
    return GenericRSSSource(name, config)
