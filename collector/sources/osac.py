"""
OSAC — Overseas Security Advisory Council RSS collector.

Source type: RSS
OSAC's feed often contains malformed XML that feedparser cannot parse. This
implementation fetches raw bytes via requests and uses lxml in recover mode
to extract <item> elements, falling back to feedparser when lxml finds nothing.
"""

from datetime import datetime
from typing import List, Dict, Any

import requests
import feedparser
import lxml.etree as etree

from collector.sources.base import (
    BaseSource, RawArticle, SourceType,
    generate_article_id, generate_content_hash,
)
from collector.utils.logging import get_logger
from collector.utils.retry import retry_with_backoff

logger = get_logger(__name__)

_HEADERS = {"User-Agent": "SentinelStack/1.0"}


def _text(el: etree._Element, tag: str) -> str:
    """Return the stripped text of the first matching child element, or ''."""
    child = el.find(tag)
    if child is not None and child.text:
        return child.text.strip()
    return ""


def _parse_items_lxml(content: bytes) -> List[Dict[str, Any]]:
    """Parse raw XML bytes with lxml in recover mode and extract <item> dicts."""
    parser = etree.XMLParser(recover=True, encoding="utf-8")
    try:
        root = etree.fromstring(content, parser=parser)
    except Exception as exc:
        logger.debug("osac_lxml_parse_error", error=str(exc))
        return []

    # <item> elements may be directly under <channel> or anywhere in the tree.
    items = root.findall(".//item")
    results = []
    for item in items:
        results.append({
            "title": _text(item, "title"),
            "link": _text(item, "link"),
            "description": _text(item, "description"),
            "pubDate": _text(item, "pubDate"),
            "guid": _text(item, "guid"),
            "tags": [c.get("domain", "") for c in item.findall("category")],
        })
    return results


def _parse_pubdate(date_str: str) -> datetime | None:
    """Try to parse an RFC-2822 pubDate string into a datetime."""
    if not date_str:
        return None
    # feedparser's date parser handles most RSS date formats
    parsed = feedparser._parse_date(date_str)  # type: ignore[attr-defined]
    if parsed:
        try:
            return datetime(*parsed[:6])
        except Exception:
            pass
    return None


class OSACSource(BaseSource):
    """Collector for the OSAC RSS security advisory feed."""

    @property
    def source_type(self) -> SourceType:
        return SourceType.RSS

    @retry_with_backoff(max_retries=3, base_delay=2.0)
    def fetch(self) -> List[RawArticle]:
        url = self.config["url"]
        logger.info("osac_fetch_start", url=url)

        # --- primary path: lxml recover mode ---
        resp = requests.get(url, headers=_HEADERS, timeout=30)
        resp.raise_for_status()
        raw_items = _parse_items_lxml(resp.content)

        if raw_items:
            articles = self._items_to_articles(raw_items, url)
            logger.info("osac_fetch_complete_lxml", count=len(articles))
            return articles

        # --- fallback path: feedparser ---
        logger.debug("osac_lxml_found_no_items_falling_back_to_feedparser")
        feed = feedparser.parse(resp.content)
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
            tags = [t.get("term", "") for t in entry.get("tags", [])]
            article_id = generate_article_id(link, title)
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
                categories=tags,
                content_hash=content_hash,
                raw_data={"feed_id": entry.get("id", "")},
            ))

        logger.info("osac_fetch_complete_feedparser", count=len(articles))
        return articles

    def _items_to_articles(self, raw_items: List[Dict[str, Any]], source_url: str) -> List[RawArticle]:
        articles = []
        for item in raw_items:
            title = item["title"]
            summary = item["description"]
            link = item["link"]
            published_at = _parse_pubdate(item["pubDate"])
            article_id = generate_article_id(link, title)
            content_hash = generate_content_hash(title, summary)
            articles.append(RawArticle(
                article_id=article_id,
                source_name=self.name,
                source_type=self.source_type,
                source_url=source_url,
                title=title,
                summary=summary,
                url=link,
                published_at=published_at,
                categories=item["tags"],
                content_hash=content_hash,
                raw_data={"guid": item["guid"]},
            ))
        return articles

    def health_check(self) -> bool:
        try:
            resp = requests.get(self.config["url"], headers=_HEADERS, timeout=10)
            return resp.status_code == 200
        except Exception as exc:
            logger.warning("osac_health_check_failed", error=str(exc))
            return False
