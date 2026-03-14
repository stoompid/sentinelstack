"""
Regional RSS bundle collector.

Reads the `feeds` dict from sources.json and iterates all 16 feeds
(4 regions × 4 feeds). Sets `regions` from the feed's `region` key.
No coordinate data.
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


class RegionalRSSSource(BaseSource):
    """Collector that aggregates multiple regional RSS feeds."""

    @property
    def source_type(self) -> SourceType:
        return SourceType.RSS

    def fetch(self) -> List[RawArticle]:
        feeds_config = self.config.get("feeds", {})
        all_articles: List[RawArticle] = []

        for _region_key, feed_list in feeds_config.items():
            for feed_cfg in feed_list:
                try:
                    articles = self._fetch_feed(feed_cfg)
                    all_articles.extend(articles)
                except Exception as exc:
                    logger.warning(
                        "regional_rss_feed_error",
                        feed_name=feed_cfg.get("name"),
                        error=str(exc),
                    )

        logger.info("regional_rss_fetch_complete", count=len(all_articles))
        return all_articles

    @retry_with_backoff(max_retries=2, base_delay=1.0)
    def _fetch_feed(self, feed_cfg: dict) -> List[RawArticle]:
        url = feed_cfg["url"]
        region = feed_cfg.get("region", "")
        feed_name = feed_cfg.get("name", url)
        focus = feed_cfg.get("focus", [])

        feed = feedparser.parse(url)
        if feed.bozo and not feed.entries:
            raise ValueError(f"feedparser bozo: {feed.bozo_exception}")

        articles = []
        for entry in feed.entries:
            title = entry.get("title", "").strip()
            summary = entry.get("summary", entry.get("description", "")).strip()
            link = entry.get("link", "")

            published_at = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                published_at = datetime(*entry.published_parsed[:6])

            article_id = generate_article_id(link, title)
            content_hash = generate_content_hash(title, summary)
            tags = [t.get("term", "") for t in entry.get("tags", [])]

            articles.append(RawArticle(
                article_id=article_id,
                source_name=feed_name,
                source_type=self.source_type,
                source_url=url,
                title=title,
                summary=summary,
                url=link,
                published_at=published_at,
                regions=[region] if region else [],
                countries=focus,
                categories=tags,
                content_hash=content_hash,
                raw_data={"feed_name": feed_name},
            ))

        return articles

    def health_check(self) -> bool:
        feeds_config = self.config.get("feeds", {})
        for _region_key, feed_list in feeds_config.items():
            for feed_cfg in feed_list:
                try:
                    feed = feedparser.parse(feed_cfg["url"])
                    if feed.entries:
                        return True
                except Exception:
                    pass
        return False
