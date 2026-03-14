"""
GDELT Project DOC 2.0 API collector.

Source type: API (JSON artlist)
No coordinate data — event_lat/lon remain None.
Lowest priority source; high volume, lowest signal.
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


class GDELTSource(BaseSource):
    """Collector for GDELT DOC 2.0 article list API."""

    @property
    def source_type(self) -> SourceType:
        return SourceType.API

    @retry_with_backoff(max_retries=3, base_delay=2.0)
    def fetch(self) -> List[RawArticle]:
        base_url = self.config["base_url"]
        params = dict(self.config.get("params", {}))

        logger.info("gdelt_fetch_start", url=base_url)
        resp = requests.get(base_url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        articles = []
        for item in data.get("articles", []):
            title = item.get("title", "").strip()
            url = item.get("url", "")
            seendate = item.get("seendate", "")
            domain = item.get("domain", "")
            # GDELT artlist has no body; use title as summary
            summary = title

            published_at = None
            if seendate:
                try:
                    # Format: YYYYMMDDTHHMMSSZ
                    published_at = datetime.strptime(seendate, "%Y%m%dT%H%M%SZ")
                except ValueError:
                    pass

            article_id = generate_article_id(url, title)
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
                content_hash=content_hash,
                raw_data={"domain": domain, "language": item.get("language", "")},
            ))

        logger.info("gdelt_fetch_complete", count=len(articles))
        return articles

    def health_check(self) -> bool:
        try:
            params = dict(self.config.get("params", {}))
            params["maxrecords"] = 1
            resp = requests.get(self.config["base_url"], params=params, timeout=10)
            return resp.status_code == 200
        except Exception as exc:
            logger.warning("gdelt_health_check_failed", error=str(exc))
            return False
