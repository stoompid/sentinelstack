from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import List

import feedparser
import requests
from dateutil import parser as dateparser

from collector.base import Article, BaseSource, generate_article_id, generate_content_hash

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": "SentinelStack/1.0 (GSOC threat intelligence; +https://github.com/sentinelstack)",
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}


class GenericRSSSource(BaseSource):
    """Generic RSS/Atom feed collector for any news source."""

    def __init__(self, name: str, config: dict):
        self._name = name
        self.url = config["url"]
        self.timeout = config.get("timeout_seconds", 15)
        self.default_category = config.get("default_category", "news")

    @property
    def source_name(self) -> str:
        return self._name

    def fetch(self) -> List[Article]:
        try:
            resp = requests.get(self.url, timeout=self.timeout, headers=_HEADERS)
            resp.raise_for_status()
            feed = feedparser.parse(resp.text)
        except Exception as e:
            logger.warning(f"[{self._name}] fetch failed: {e}")
            return []

        articles = []
        for entry in feed.entries:
            try:
                title = entry.get("title", "").strip()
                if not title:
                    continue

                summary = entry.get("summary", entry.get("description", "")).strip()
                summary = re.sub(r"<[^>]+>", " ", summary)[:500]

                url = entry.get("link", "")
                published_at = self._parse_date(entry)
                country = self._extract_country(entry, title)
                categories = self._extract_categories(entry)

                articles.append(Article(
                    article_id=generate_article_id(url, title),
                    content_hash=generate_content_hash(title, summary),
                    source=self._name,
                    title=title,
                    summary=summary,
                    url=url,
                    published_at=published_at,
                    collected_at=datetime.now(tz=timezone.utc),
                    country=country,
                    categories=categories,
                ))
            except Exception as e:
                logger.warning(f"[{self._name}] skipping entry: {e}")
                continue

        return articles

    def health_check(self) -> bool:
        try:
            resp = requests.get(self.url, timeout=self.timeout, headers=_HEADERS, stream=True)
            resp.close()
            return resp.status_code < 400
        except Exception:
            return False

    def _parse_date(self, entry) -> datetime | None:
        for field in ("published_parsed", "updated_parsed"):
            t = entry.get(field)
            if t:
                try:
                    return datetime(*t[:6], tzinfo=timezone.utc)
                except Exception:
                    pass
        for field in ("published", "updated", "dc_date"):
            s = entry.get(field)
            if s:
                try:
                    dt = dateparser.parse(s)
                    if dt and dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    return dt
                except Exception:
                    pass
        return None

    def _extract_country(self, entry, title: str) -> str:
        for tag in entry.get("tags", []):
            term = tag.get("term", "").strip()
            if term and len(term) > 2:
                return term
        return ""

    def _extract_categories(self, entry) -> List[str]:
        cats = []
        for tag in entry.get("tags", []):
            term = tag.get("term", "").lower().strip()
            if term:
                cats.append(term)
        return cats if cats else [self.default_category]
