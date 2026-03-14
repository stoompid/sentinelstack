"""National Weather Service alerts collector for monitored US cities."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List

import requests

from collector.base import Article, BaseSource, generate_article_id, generate_content_hash

logger = logging.getLogger(__name__)

# Monitored US company sites
US_CITIES = {
    "New York, NY": (40.7128, -74.0060),
    "San Jose, CA": (37.3382, -121.8863),
    "Washington, DC": (38.9072, -77.0369),
    "Chicago, IL": (41.8781, -87.6298),
}

# Only collect alerts at these severity levels
SIGNIFICANT_SEVERITIES = {"Extreme", "Severe"}

USER_AGENT = "(SentinelStack GSOC, sentinelstack@example.com)"


class NWSSource(BaseSource):
    """Collects active weather alerts from the National Weather Service API."""

    def __init__(self, config: dict):
        self.timeout = config.get("timeout_seconds", 10)
        self.cities = config.get("cities", US_CITIES)
        self.min_severity = config.get("min_severity", SIGNIFICANT_SEVERITIES)

    @property
    def source_name(self) -> str:
        return "nws"

    def fetch(self) -> List[Article]:
        articles = []
        seen_ids = set()

        for city_name, (lat, lon) in self.cities.items():
            try:
                url = f"https://api.weather.gov/alerts/active?point={lat},{lon}"
                resp = requests.get(
                    url,
                    timeout=self.timeout,
                    headers={"User-Agent": USER_AGENT, "Accept": "application/geo+json"},
                )
                resp.raise_for_status()
                data = resp.json()

                for feature in data.get("features", []):
                    props = feature.get("properties", {})
                    severity = props.get("severity", "Unknown")
                    if severity not in self.min_severity:
                        continue

                    event = props.get("event", "Weather Alert")
                    headline = props.get("headline", event)
                    description = (props.get("description") or "")[:500]
                    alert_url = props.get("@id", "")
                    area = props.get("areaDesc", city_name)

                    onset = props.get("onset") or props.get("effective")
                    published_at = None
                    if onset:
                        try:
                            published_at = datetime.fromisoformat(onset)
                        except Exception:
                            pass

                    aid = generate_article_id(alert_url, headline)
                    if aid in seen_ids:
                        continue
                    seen_ids.add(aid)

                    articles.append(Article(
                        article_id=aid,
                        content_hash=generate_content_hash(headline, description),
                        source="nws",
                        title=f"[{severity.upper()}] {headline}",
                        summary=description,
                        url=alert_url,
                        published_at=published_at,
                        collected_at=datetime.now(tz=timezone.utc),
                        country="United States",
                        categories=["weather", event.lower()],
                        latitude=lat,
                        longitude=lon,
                    ))

            except Exception as e:
                logger.warning(f"[nws] {city_name} fetch failed: {e}")
                continue

        return articles

    def health_check(self) -> bool:
        try:
            resp = requests.get(
                "https://api.weather.gov/alerts/active?limit=1",
                timeout=self.timeout,
                headers={"User-Agent": USER_AGENT},
            )
            return resp.status_code < 500
        except Exception:
            return False
