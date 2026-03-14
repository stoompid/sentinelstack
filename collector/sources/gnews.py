"""
Google News RSS collector.

Source type: RSS (no API key required)
URL pattern: https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en

Reads a list of `queries` from the source config, fetches each as an RSS feed,
deduplicates by article_id across queries, and returns the combined list.
"""

from datetime import datetime
from typing import List, Set
from urllib.parse import urlencode

import feedparser
import requests

from collector.sources.base import (
    BaseSource, RawArticle, SourceType,
    generate_article_id, generate_content_hash,
)
from collector.utils.logging import get_logger
from collector.utils.retry import retry_with_backoff

logger = get_logger(__name__)

_BASE_URL = "https://news.google.com/rss/search"
_PARAMS_SUFFIX = "&hl=en-US&gl=US&ceid=US:en"


def _build_url(query: str) -> str:
    """Build a Google News RSS URL for the given query string."""
    # urlencode replaces spaces with '+', which Google News accepts
    encoded = urlencode({"q": query})
    return f"{_BASE_URL}?{encoded}{_PARAMS_SUFFIX}"


class GNewsSource(BaseSource):
    """Collector for Google News RSS search feeds."""

    @property
    def source_type(self) -> SourceType:
        return SourceType.RSS

    def fetch(self) -> List[RawArticle]:
        queries: List[str] = self.config.get("queries", [])
        if not queries:
            logger.warning("gnews_no_queries_configured")
            return []

        logger.info("gnews_fetch_start", query_count=len(queries))
        all_articles: List[RawArticle] = []
        seen_ids: Set[str] = set()

        for query in queries:
            try:
                batch = self._fetch_query(query)
                added = 0
                for article in batch:
                    if article.article_id not in seen_ids:
                        seen_ids.add(article.article_id)
                        all_articles.append(article)
                        added += 1
                logger.debug("gnews_query_complete", query=query, fetched=len(batch), added=added)
            except Exception as exc:
                # Log and continue — don't let one bad query kill the whole run
                logger.warning("gnews_query_failed", query=query, error=str(exc))

        logger.info("gnews_fetch_complete", total=len(all_articles))
        return all_articles

    @retry_with_backoff(max_retries=3, base_delay=2.0)
    def _fetch_query(self, query: str) -> List[RawArticle]:
        """Fetch and parse a single Google News RSS query."""
        url = _build_url(query)
        # Use requests to fetch raw bytes — avoids feedparser's URL handler
        # misinterpreting the colon in ceid=US:en as a URL scheme.
        headers = {"User-Agent": "Mozilla/5.0 (compatible; SentinelStack/1.0)"}
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)

        if feed.bozo and not feed.entries:
            raise ValueError(f"feedparser error for query '{query}': {feed.bozo_exception}")

        articles = []
        for entry in feed.entries:
            title = entry.get("title", "").strip()
            summary = entry.get("summary", entry.get("description", "")).strip()
            link = entry.get("link", "")

            published_at = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                try:
                    published_at = datetime(*entry.published_parsed[:6])
                except Exception:
                    pass

            # Google News source name is embedded in the title as "... - Source Name"
            source_suffix = ""
            if " - " in title:
                source_suffix = title.rsplit(" - ", 1)[-1]

            article_id = generate_article_id(link, title)
            content_hash = generate_content_hash(title, summary)

            articles.append(RawArticle(
                article_id=article_id,
                source_name=self.name,
                source_type=self.source_type,
                source_url=_BASE_URL,
                title=title,
                summary=summary,
                url=link,
                published_at=published_at,
                keywords=[query],
                content_hash=content_hash,
                raw_data={
                    "gnews_query": query,
                    "feed_id": entry.get("id", ""),
                    "outlet": source_suffix,
                },
            ))

        return articles

    def health_check(self) -> bool:
        """Check that at least one query returns results."""
        queries: List[str] = self.config.get("queries", [])
        if not queries:
            return False
        try:
            test_url = _build_url(queries[0])
            headers = {"User-Agent": "Mozilla/5.0 (compatible; SentinelStack/1.0)"}
            resp = requests.get(test_url, headers=headers, timeout=10)
            feed = feedparser.parse(resp.content)
            return bool(feed.entries)
        except Exception as exc:
            logger.warning("gnews_health_check_failed", error=str(exc))
            return False
