from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List

import feedparser
import requests

from collector.base import Article, BaseSource, generate_article_id, generate_content_hash

logger = logging.getLogger(__name__)

GDACS_CATEGORY_MAP = {
    "TC": "cyclone",
    "EQ": "earthquake",
    "FL": "flood",
    "VO": "volcano",
    "DR": "drought",
    "WF": "wildfire",
    "TS": "tsunami",
}


class GDACSSource(BaseSource):
    """GDACS global disaster GeoRSS feed — Orange/Red alerts only."""

    def __init__(self, config: dict):
        self.url = config["url"]
        self.alert_levels = [a.lower() for a in config.get("alert_levels", ["orange", "red"])]
        self.timeout = config.get("timeout_seconds", 10)

    @property
    def source_name(self) -> str:
        return "gdacs"

    def fetch(self) -> List[Article]:
        try:
            resp = requests.get(self.url, timeout=self.timeout)
            resp.raise_for_status()
            feed = feedparser.parse(resp.text)
        except Exception as e:
            logger.warning(f"[gdacs] fetch failed: {e}")
            return []

        articles = []
        for entry in feed.entries:
            try:
                alert_level = self._get_tag(entry, "alertlevel", "").lower()
                if alert_level not in self.alert_levels:
                    continue

                title = entry.get("title", "").strip()
                summary = entry.get("summary", "").strip()
                url = entry.get("link", "")
                published_at = self._parse_date(entry)
                country = self._get_tag(entry, "country", "")
                event_type_code = self._get_tag(entry, "eventtype", "")
                category = GDACS_CATEGORY_MAP.get(event_type_code, event_type_code.lower() or "disaster")

                lat = self._get_geo(entry, "lat")
                lon = self._get_geo(entry, "long")

                if not title:
                    continue

                article = Article(
                    article_id=generate_article_id(url, title),
                    content_hash=generate_content_hash(title, summary),
                    source=self.source_name,
                    title=title,
                    summary=summary,
                    url=url,
                    published_at=published_at,
                    collected_at=datetime.now(tz=timezone.utc),
                    country=country,
                    categories=[category],
                    latitude=lat,
                    longitude=lon,
                    magnitude=None,
                )
                articles.append(article)
            except Exception as e:
                logger.warning(f"[gdacs] skipping entry: {e}")
                continue

        return articles

    def health_check(self) -> bool:
        try:
            resp = requests.head(self.url, timeout=self.timeout)
            return resp.status_code < 500
        except Exception:
            return False

    def _get_tag(self, entry, tag: str, default: str = "") -> str:
        """Extract a GDACS-namespaced tag value from a feedparser entry."""
        for key, val in entry.items():
            if key.endswith(f"_{tag}") or key == tag:
                if isinstance(val, str):
                    return val
        return default

    def _get_geo(self, entry, attr: str) -> float | None:
        """Extract geo coordinates from GeoRSS tags."""
        point = getattr(entry, "geo_point", None) or entry.get("geo_point")
        if point:
            parts = str(point).split()
            if len(parts) == 2:
                try:
                    lat, lon = float(parts[0]), float(parts[1])
                    return lat if attr == "lat" else lon
                except ValueError:
                    pass
        # Try direct geo tags
        val = entry.get(f"geo_{attr}") or entry.get(attr)
        if val:
            try:
                return float(val)
            except (ValueError, TypeError):
                pass
        return None

    def _parse_date(self, entry) -> datetime | None:
        published = entry.get("published_parsed") or entry.get("updated_parsed")
        if published:
            try:
                return datetime(*published[:6], tzinfo=timezone.utc)
            except Exception:
                pass
        return None
