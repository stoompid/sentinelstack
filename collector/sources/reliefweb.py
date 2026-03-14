"""
ReliefWeb API collector.

Source type: API (REST JSON)
No coordinate data — event_lat/lon remain None.
"""

from datetime import datetime
from typing import List

import requests

from collector.sources.base import (
    BaseSource, RawArticle, SourceType,
    generate_article_id, generate_content_hash,
)
from collector.utils.logging import get_logger
from collector.utils.retry import retry_with_backoff

logger = get_logger(__name__)


class ReliefWebSource(BaseSource):
    """Collector for ReliefWeb humanitarian reports API."""

    @property
    def source_type(self) -> SourceType:
        return SourceType.API

    @retry_with_backoff(max_retries=3, base_delay=2.0)
    def fetch(self) -> List[RawArticle]:
        base_url = self.config["base_url"]

        logger.info("reliefweb_fetch_start", url=base_url)
        payload = {
            "preset": "latest",
            "limit": 50,
            "fields": {"include": ["title", "body", "date", "source", "country", "disaster_type", "url"]},
            "appname": "sentinelstack",
        }
        resp = requests.post(base_url, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        articles = []
        for item in data.get("data", []):
            fields = item.get("fields", {})
            title = fields.get("title", "").strip()
            body = fields.get("body", "").strip()
            summary = body[:500] if body else ""

            url_field = fields.get("url", "")
            if isinstance(url_field, dict):
                url = url_field.get("uri", "")
            else:
                url = str(url_field)

            published_at = None
            date_field = fields.get("date", {})
            if isinstance(date_field, dict):
                date_str = date_field.get("created") or date_field.get("original")
            else:
                date_str = str(date_field) if date_field else None
            if date_str:
                try:
                    published_at = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                except ValueError:
                    pass

            countries = []
            for c in fields.get("country", []):
                if isinstance(c, dict):
                    countries.append(c.get("name", ""))
                else:
                    countries.append(str(c))

            categories = []
            for d in fields.get("disaster_type", []):
                if isinstance(d, dict):
                    categories.append(d.get("name", ""))
                else:
                    categories.append(str(d))

            sources = []
            for s in fields.get("source", []):
                if isinstance(s, dict):
                    sources.append(s.get("name", ""))

            article_id = generate_article_id(url or str(item.get("id", "")), title)
            content_hash = generate_content_hash(title, summary)

            articles.append(RawArticle(
                article_id=article_id,
                source_name=self.name,
                source_type=self.source_type,
                source_url=base_url,
                title=title,
                summary=summary,
                full_text=body or None,
                url=url,
                published_at=published_at,
                countries=countries,
                categories=categories,
                keywords=sources,
                content_hash=content_hash,
                raw_data={"reliefweb_id": item.get("id")},
            ))

        logger.info("reliefweb_fetch_complete", count=len(articles))
        return articles

    def health_check(self) -> bool:
        try:
            resp = requests.post(
                self.config["base_url"],
                json={"preset": "latest", "limit": 1, "appname": "sentinelstack"},
                timeout=10,
            )
            return resp.status_code == 200
        except Exception as exc:
            logger.warning("reliefweb_health_check_failed", error=str(exc))
            return False
