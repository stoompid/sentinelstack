from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List

import feedparser
import requests
from dateutil import parser as dateparser

from collector.base import Article, BaseSource, generate_article_id, generate_content_hash

logger = logging.getLogger(__name__)


class OSACSource(BaseSource):
    """OSAC (US State Dept Overseas Security Advisory Council) RSS feed."""

    def __init__(self, config: dict):
        self.url = config["url"]
        self.timeout = config.get("timeout_seconds", 10)

    @property
    def source_name(self) -> str:
        return "osac"

    def fetch(self) -> List[Article]:
        try:
            resp = requests.get(self.url, timeout=self.timeout)
            resp.raise_for_status()
            feed = feedparser.parse(resp.text)
        except Exception as e:
            logger.warning(f"[osac] fetch failed: {e}")
            return []

        articles = []
        for entry in feed.entries:
            try:
                title = entry.get("title", "").strip()
                if not title:
                    continue

                summary = entry.get("summary", entry.get("description", "")).strip()
                url = entry.get("link", "")
                published_at = self._parse_date(entry)
                country = self._extract_country(entry, title)
                categories = self._extract_categories(entry)

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
                    categories=categories,
                )
                articles.append(article)
            except Exception as e:
                logger.warning(f"[osac] skipping entry: {e}")
                continue

        return articles

    def health_check(self) -> bool:
        try:
            resp = requests.head(self.url, timeout=self.timeout)
            return resp.status_code < 500
        except Exception:
            return False

    def _parse_date(self, entry) -> datetime | None:
        # Try structured time tuple first
        for field in ("published_parsed", "updated_parsed"):
            t = entry.get(field)
            if t:
                try:
                    return datetime(*t[:6], tzinfo=timezone.utc)
                except Exception:
                    pass
        # Fall back to string parsing
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
        # OSAC tags sometimes include category/country
        tags = entry.get("tags", [])
        for tag in tags:
            term = tag.get("term", "")
            if term and term not in ("Security Alert", "Security Message", "Travel Advisory"):
                return term
        # Try to grab from title — OSAC titles often start with "Country Name —"
        if " - " in title:
            return title.split(" - ")[0].strip()
        if "\u2014" in title:
            return title.split("\u2014")[0].strip()
        return ""

    def _extract_categories(self, entry) -> List[str]:
        tags = entry.get("tags", [])
        cats = []
        for tag in tags:
            term = tag.get("term", "").lower()
            if term:
                cats.append(term)
        return cats if cats else ["security advisory"]
