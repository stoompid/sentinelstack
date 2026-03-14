"""
NOAA National Weather Service active alerts collector.

Source type: API (GeoJSON)
Parses areaDesc to match watchlist city names → assigns that city's
lat/lon from locations.json as event coordinates.
event_magnitude is always None.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple

import requests

from collector.sources.base import (
    BaseSource, RawArticle, SourceType,
    generate_article_id, generate_content_hash,
)
from collector.utils.logging import get_logger
from collector.utils.retry import retry_with_backoff

logger = get_logger(__name__)

LOCATIONS_PATH = Path(__file__).parents[2] / "config" / "locations.json"


def _load_us_cities() -> Dict[str, Dict]:
    """Return a mapping of lowercase city name → location record for US cities."""
    data = json.loads(LOCATIONS_PATH.read_text(encoding="utf-8"))
    return {
        loc["city"].lower(): loc
        for loc in data.get("locations", [])
        if loc.get("country") == "United States"
    }


def _match_city(area_desc: str, us_cities: Dict[str, Dict]) -> Optional[Tuple[float, float, str]]:
    """
    Search areaDesc for a watchlist city name.

    Returns (lat, lon, city_name) if found, else None.
    """
    area_lower = area_desc.lower()
    for city_name, loc in us_cities.items():
        if city_name in area_lower:
            return loc["latitude"], loc["longitude"], loc["city"]
    return None


class NWSSource(BaseSource):
    """Collector for NWS active weather alerts (US only)."""

    @property
    def source_type(self) -> SourceType:
        return SourceType.API

    @retry_with_backoff(max_retries=3, base_delay=2.0)
    def fetch(self) -> List[RawArticle]:
        base_url = self.config["base_url"]
        params = dict(self.config.get("params", {}))

        # NWS expects area as comma-joined string
        if isinstance(params.get("area"), list):
            params["area"] = ",".join(params["area"])
        if isinstance(params.get("severity"), list):
            params["severity"] = ",".join(params["severity"])

        headers = {"User-Agent": "SentinelStack/1.0 (security-monitor)"}
        logger.info("nws_fetch_start", url=base_url, params=params)
        resp = requests.get(base_url, params=params, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        us_cities = _load_us_cities()
        articles = []

        for feature in data.get("features", []):
            props = feature.get("properties", {})
            title = props.get("headline", props.get("event", "")).strip()
            area_desc = props.get("areaDesc", "")
            description = props.get("description", "").strip()
            summary = description[:500] if description else area_desc[:500]
            url = props.get("@id", "")

            published_at = None
            onset = props.get("onset") or props.get("effective")
            if onset:
                try:
                    published_at = datetime.fromisoformat(onset.replace("Z", "+00:00"))
                except ValueError:
                    pass

            # Try to assign coordinates from matching watchlist city
            event_latitude = event_longitude = None
            match = _match_city(area_desc, us_cities)
            if match:
                event_latitude, event_longitude, _ = match

            categories = []
            if props.get("event"):
                categories.append(props["event"])
            severity = props.get("severity", "")
            if severity:
                categories.append(severity)

            article_id = generate_article_id(url or title, title)
            content_hash = generate_content_hash(title, summary)

            articles.append(RawArticle(
                article_id=article_id,
                source_name=self.name,
                source_type=self.source_type,
                source_url=base_url,
                title=title,
                summary=summary,
                url=url,
                published_at=published_at,
                countries=["United States"],
                categories=categories,
                event_latitude=event_latitude,
                event_longitude=event_longitude,
                content_hash=content_hash,
                raw_data={
                    "nws_id": props.get("id"),
                    "area_desc": area_desc,
                    "severity": severity,
                    "certainty": props.get("certainty"),
                    "urgency": props.get("urgency"),
                },
            ))

        logger.info("nws_fetch_complete", count=len(articles))
        return articles

    def health_check(self) -> bool:
        try:
            headers = {"User-Agent": "SentinelStack/1.0 (security-monitor)"}
            resp = requests.get(
                self.config["base_url"],
                params={"status": "actual", "limit": 1},
                headers=headers,
                timeout=10,
            )
            return resp.status_code == 200
        except Exception as exc:
            logger.warning("nws_health_check_failed", error=str(exc))
            return False
