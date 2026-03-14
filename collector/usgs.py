from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import List

import requests

from collector.base import Article, BaseSource, generate_article_id, generate_content_hash

logger = logging.getLogger(__name__)


class USGSSource(BaseSource):
    """USGS significant earthquake feed (GeoJSON)."""

    def __init__(self, config: dict):
        self.url = config["url"]
        self.min_magnitude = config.get("min_magnitude", 5.0)
        self.timeout = config.get("timeout_seconds", 10)

    @property
    def source_name(self) -> str:
        return "usgs"

    def fetch(self) -> List[Article]:
        try:
            resp = requests.get(self.url, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning(f"[usgs] fetch failed: {e}")
            return []

        articles = []
        for feature in data.get("features", []):
            try:
                props = feature.get("properties", {})
                coords = feature.get("geometry", {}).get("coordinates", [])

                mag = props.get("mag")
                if mag is None or mag < self.min_magnitude:
                    continue

                place = props.get("place", "Unknown location")
                title = f"M{mag} Earthquake — {place}"
                summary = (
                    f"Magnitude {mag} earthquake reported at {place}. "
                    f"Depth: {coords[2] if len(coords) > 2 else 'unknown'} km. "
                    f"Alert: {props.get('alert', 'none')}."
                )
                url = props.get("url", "")
                time_ms = props.get("time")
                published_at = (
                    datetime.fromtimestamp(time_ms / 1000, tz=timezone.utc)
                    if time_ms
                    else None
                )

                # coords order: [longitude, latitude, depth]
                lon = coords[0] if len(coords) > 0 else None
                lat = coords[1] if len(coords) > 1 else None

                article = Article(
                    article_id=generate_article_id(url, title),
                    content_hash=generate_content_hash(title, summary),
                    source=self.source_name,
                    title=title,
                    summary=summary,
                    url=url,
                    published_at=published_at,
                    collected_at=datetime.now(tz=timezone.utc),
                    country=self._extract_country(place),
                    categories=["earthquake"],
                    latitude=lat,
                    longitude=lon,
                    magnitude=mag,
                )
                articles.append(article)
            except Exception as e:
                logger.warning(f"[usgs] skipping feature: {e}")
                continue

        return articles

    def health_check(self) -> bool:
        try:
            resp = requests.head(self.url, timeout=self.timeout)
            return resp.status_code < 500
        except Exception:
            return False

    def _extract_country(self, place: str) -> str:
        """Best-effort country extraction from USGS place string (e.g. '10km NE of Tokyo, Japan')."""
        if "," in place:
            return place.split(",")[-1].strip()
        return place.strip()
