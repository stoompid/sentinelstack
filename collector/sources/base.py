"""
Base source class for all collectors.

Defines the interface that OSAC, ReliefWeb, GDELT, and RSS collectors implement.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional
from enum import Enum
import hashlib


class SourceType(Enum):
    """Type of data source."""
    RSS = "rss"
    API = "api"
    SCRAPER = "scraper"
    TELEGRAM = "telegram"


@dataclass
class RawArticle:
    """
    Standardized article/report structure from any source.
    
    This is the common format that all collectors output,
    regardless of the upstream source format.
    """
    # Unique identifier (hash of url + title)
    article_id: str
    
    # Source metadata
    source_name: str
    source_type: SourceType
    source_url: str
    
    # Content
    title: str
    summary: str
    full_text: Optional[str] = None
    url: str = ""
    
    # Temporal
    published_at: Optional[datetime] = None
    collected_at: datetime = field(default_factory=datetime.utcnow)
    
    # Geographic (extracted by source if available)
    countries: List[str] = field(default_factory=list)
    regions: List[str] = field(default_factory=list)
    
    # Classification hints (source-provided, not analyst-assigned)
    categories: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)

    # Geospatial coordinates (populated by sources that provide them)
    event_latitude: Optional[float] = None
    event_longitude: Optional[float] = None
    event_magnitude: Optional[float] = None  # USGS only; None for NWS/GDACS

    # Deduplication hash — SHA256 of lowercased title+summary
    content_hash: Optional[str] = None

    # Raw data for debugging/reprocessing
    raw_data: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "article_id": self.article_id,
            "source_name": self.source_name,
            "source_type": self.source_type.value,
            "source_url": self.source_url,
            "title": self.title,
            "summary": self.summary,
            "full_text": self.full_text,
            "url": self.url,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "collected_at": self.collected_at.isoformat(),
            "countries": self.countries,
            "regions": self.regions,
            "categories": self.categories,
            "keywords": self.keywords,
            "event_latitude": self.event_latitude,
            "event_longitude": self.event_longitude,
            "event_magnitude": self.event_magnitude,
            "content_hash": self.content_hash,
            "raw_data": self.raw_data,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RawArticle":
        """Reconstruct from dictionary."""
        return cls(
            article_id=data["article_id"],
            source_name=data["source_name"],
            source_type=SourceType(data["source_type"]),
            source_url=data["source_url"],
            title=data["title"],
            summary=data["summary"],
            full_text=data.get("full_text"),
            url=data.get("url", ""),
            published_at=datetime.fromisoformat(data["published_at"]) if data.get("published_at") else None,
            collected_at=datetime.fromisoformat(data["collected_at"]),
            countries=data.get("countries", []),
            regions=data.get("regions", []),
            categories=data.get("categories", []),
            keywords=data.get("keywords", []),
            event_latitude=data.get("event_latitude"),
            event_longitude=data.get("event_longitude"),
            event_magnitude=data.get("event_magnitude"),
            content_hash=data.get("content_hash"),
            raw_data=data.get("raw_data", {}),
        )


def generate_article_id(url: str, title: str) -> str:
    """Generate a unique, deterministic ID for an article."""
    content = f"{url}|{title}".encode("utf-8")
    return hashlib.sha256(content).hexdigest()[:16]


def generate_content_hash(title: str, summary: str) -> str:
    """Generate SHA256 hash of lowercased title+summary for deduplication."""
    content = f"{title.lower()}|{summary.lower()}".encode("utf-8")
    return hashlib.sha256(content).hexdigest()


class BaseSource(ABC):
    """
    Abstract base class for all data sources.
    
    Each source type (OSAC, ReliefWeb, etc.) implements this interface.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the source.
        
        Args:
            config: Source-specific configuration from sources.json
        """
        self.config = config
        self.name = config.get("name", self.__class__.__name__)
        self.enabled = config.get("enabled", True)
        self.priority = config.get("priority", 99)
    
    @property
    @abstractmethod
    def source_type(self) -> SourceType:
        """Return the type of this source."""
        pass
    
    @abstractmethod
    def fetch(self) -> List[RawArticle]:
        """
        Fetch articles from this source.
        
        Returns:
            List of RawArticle objects
        
        Raises:
            RetryExhausted: If all retry attempts fail
        """
        pass
    
    @abstractmethod
    def health_check(self) -> bool:
        """
        Check if the source is accessible.
        
        Returns:
            True if source is healthy, False otherwise
        """
        pass
    
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(name={self.name}, enabled={self.enabled})>"
