"""
GDACS — Global Disaster Alert and Coordination System RSS collector.

Source type: RSS (feedparser)
feedparser auto-parses georss:point into entry.geo_lat / entry.geo_long.
event_magnitude is None; gdacs:severity is stored in categories.
"""

from datetime import datetime
from typing import List

import feedparser

from collector.sources.base import (
    BaseSource, RawArticle, SourceType,
    generate_article_id, generate_content_hash,
)
from collector.utils.logging import get_logger
from collector.utils.retry import retry_with_backoff

logger = get_logger(__name__)


class GDACSSource(BaseSource):
    """Collector for GDACS global disaster RSS feed."""

    @property
    def source_type(self) -> SourceType:
        return SourceType.RSS

    @retry_with_backoff(max_retries=3, base_delay=2.0)
    def fetch(self) -> List[RawArticle]:
        url = self.config["url"]
        logger.info("gdacs_fetch_start", url=url)

        feed = feedparser.parse(url)
        if feed.bozo and not feed.entries:
            raise ValueError(f"feedparser error: {feed.bozo_exception}")

        articles = []
        for entry in feed.entries:
            title = entry.get("title", "").strip()
            summary = entry.get("summary", entry.get("description", "")).strip()
            link = entry.get("link", "")

            published_at = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                published_at = datetime(*entry.published_parsed[:6])

            # feedparser maps georss:point → entry.geo_lat / entry.geo_long
            event_latitude = None
            event_longitude = None
            try:
                if hasattr(entry, "geo_lat") and entry.geo_lat:
                    event_latitude = float(entry.geo_lat)
                if hasattr(entry, "geo_long") and entry.geo_long:
                    event_longitude = float(entry.geo_long)
            except (ValueError, TypeError):
                pass

            # Collect severity/event type from GDACS-specific tags
            categories = []
            for tag in entry.get("tags", []):
                term = tag.get("term", "").strip()
                if term:
                    categories.append(term)

            # gdacs:severity may appear as a namespaced attribute
            severity = entry.get("gdacs_severity") or entry.get("severity")
            if severity:
                categories.append(str(severity).strip())

            event_type = entry.get("gdacs_eventtype") or entry.get("eventtype")
            if event_type and event_type not in categories:
                categories.append(str(event_type).strip())

            article_id = generate_article_id(link or title, title)
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
                categories=categories,
                event_latitude=event_latitude,
                event_longitude=event_longitude,
                content_hash=content_hash,
                raw_data={"gdacs_id": entry.get("id", "")},
            ))

        logger.info("gdacs_fetch_complete", count=len(articles))
        return articles

    def health_check(self) -> bool:
        try:
            feed = feedparser.parse(self.config["url"])
            return not feed.bozo or bool(feed.entries)
        except Exception as exc:
            logger.warning("gdacs_health_check_failed", error=str(exc))
            return False
