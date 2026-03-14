"""
JSON backup writer for raw articles.

Writes data/raw/json_backup/{source_key}_{YYYYMMDD_HHMMSS}.json
Each file is a JSON array of article.to_dict().
"""

import json
from datetime import datetime
from pathlib import Path
from typing import List

from collector.sources.base import RawArticle
from collector.utils.logging import get_logger

logger = get_logger(__name__)

BACKUP_DIR = Path(__file__).parents[2] / "data" / "raw" / "json_backup"


def write_backup(source_key: str, articles: List[RawArticle]) -> Path:
    """
    Write articles to a timestamped JSON file.

    Args:
        source_key: Short identifier for the source (e.g. "osac", "usgs")
        articles:   List of RawArticle objects to serialise

    Returns:
        Path of the written file.
    """
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"{source_key}_{timestamp}.json"
    path = BACKUP_DIR / filename

    data = [a.to_dict() for a in articles]
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    logger.info("json_backup_written", path=str(path), count=len(articles))
    return path
