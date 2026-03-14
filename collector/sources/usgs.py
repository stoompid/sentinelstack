"""
USGS Earthquake Hazards GeoJSON collector.

Source type: API (GeoJSON)
Coordinate order in GeoJSON is [lon, lat, depth].
Populates event_latitude, event_longitude, event_magnitude.
"""

from datetime import datetime, timezone
from typing import List

import requests

from collector.sources.base import (
    BaseSource, RawArticle, SourceType,
    generate_article_id, generate_content_hash,
)
from collector.utils.logging import get_logger
from collector.utils.retry import retry_with_backoff

logger = get_logger(__name__)


class USGSSource(BaseSource):
    """Collector for USGS significant earthquake GeoJSON feed."""

    @property
    def source_type(self) -> SourceType:
        return SourceType.API

    @retry_with_backoff(max_retries=3, base_delay=2.0)
    def fetch(self) -> List[RawArticle]:
        base_url = self.config["base_url"]
        feed = self.config.get("feed", "significant_week")
        url = f"{base_url}{feed}.geojson"

        logger.info("usgs_fetch_start", url=url)
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        geojson = resp.json()

        articles = []
        for feature in geojson.get("features", []):
            props = feature.get("properties", {})
            coords = feature.get("geometry", {}).get("coordinates", [None, None, None])

            title = props.get("title", "").strip()
            place = props.get("place", "").strip()
            summary = place or title
            link = props.get("url", "")

            # Unix milliseconds → datetime
            time_ms = props.get("time")
            published_at = None
            if time_ms is not None:
                published_at = datetime.fromtimestamp(time_ms / 1000.0, tz=timezone.utc)

            # GeoJSON coordinate order: [longitude, latitude, depth]
            event_longitude = coords[0] if len(coords) > 0 else None
            event_latitude = coords[1] if len(coords) > 1 else None
            event_magnitude = props.get("mag")

            article_id = generate_article_id(link or str(props.get("ids", title)), title)
            content_hash = generate_content_hash(title, summary)

            articles.append(RawArticle(
                article_id=article_id,
                source_name=self.name,
                source_type=self.source_type,
                source_url=url,
                title=title,
                summary=summary,
                url=link,
                published_at=published_at,
                categories=["earthquake"],
                event_latitude=event_latitude,
                event_longitude=event_longitude,
                event_magnitude=event_magnitude,
                content_hash=content_hash,
                raw_data={
                    "usgs_id": feature.get("id"),
                    "depth_km": coords[2] if len(coords) > 2 else None,
                    "alert": props.get("alert"),
                    "tsunami": props.get("tsunami"),
                },
            ))

        logger.info("usgs_fetch_complete", count=len(articles))
        return articles

    def health_check(self) -> bool:
        try:
            base_url = self.config["base_url"]
            feed = self.config.get("feed", "significant_week")
            resp = requests.get(f"{base_url}{feed}.geojson", timeout=10)
            return resp.status_code == 200
        except Exception as exc:
            logger.warning("usgs_health_check_failed", error=str(exc))
            return False
