from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import List

import requests
from dateutil import parser as dateparser

from collector.base import Article, BaseSource, generate_article_id, generate_content_hash

logger = logging.getLogger(__name__)


class ReliefWebSource(BaseSource):
    """ReliefWeb UN humanitarian reports REST API."""

    def __init__(self, config: dict):
        self.url = config["url"]
        self.params = config.get("params", {})
        self.timeout = config.get("timeout_seconds", 15)

    @property
    def source_name(self) -> str:
        return "reliefweb"

    def fetch(self) -> List[Article]:
        payload = {
            "appname": self.params.get("appname", "sentinelstack"),
            "limit": self.params.get("limit", 50),
            "filter": {"field": "status", "value": "published"},
            "fields": {
                "include": ["title", "body-html", "url", "date", "country", "theme", "source"]
            },
            "sort": ["date.created:desc"],
        }

        try:
            resp = requests.post(self.url, json=payload, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning(f"[reliefweb] fetch failed: {e}")
            return []

        articles = []
        for item in data.get("data", []):
            try:
                fields = item.get("fields", {})
                title = fields.get("title", "").strip()
                if not title:
                    continue

                body_html = fields.get("body-html", "")
                summary = self._strip_html(body_html)[:500]

                url = fields.get("url", "")
                date_info = fields.get("date", {})
                published_at = self._parse_date(date_info.get("created"))

                countries = fields.get("country", [])
                country = countries[0].get("name", "") if countries else ""

                themes = fields.get("theme", [])
                categories = [t.get("name", "").lower() for t in themes if t.get("name")]
                if not categories:
                    categories = ["humanitarian"]

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
                logger.warning(f"[reliefweb] skipping item: {e}")
                continue

        return articles

    def health_check(self) -> bool:
        try:
            resp = requests.post(
                self.url,
                json={"appname": "sentinelstack", "limit": 1},
                timeout=self.timeout,
            )
            return resp.status_code < 500
        except Exception:
            return False

    def _strip_html(self, html: str) -> str:
        return re.sub(r"<[^>]+>", " ", html).strip()

    def _parse_date(self, date_str: str | None) -> datetime | None:
        if not date_str:
            return None
        try:
            dt = dateparser.parse(date_str)
            if dt and dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            return None
