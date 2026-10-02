import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

class NewsDocument(BaseModel):
    """
    Canonical normalized schema for ingested external news (e.g. GDELT).
    Isolates the ingestion layer from the generic downstream NLP pipeline.
    """
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    document_id: str = Field(description="Unique document ID (hash or assigned ID)")
    source: str = Field(description="Origin system, e.g., 'GDELT'")
    publisher: Optional[str] = Field(default=None, description="Publisher or domain name")
    title: str = Field(description="Article headline")
    body: Optional[str] = Field(default=None, description="Article body or snippet")
    url: str = Field(description="Article permalink/URL")
    published_at: datetime = Field(description="Publication timestamp (UTC)")
    language: str = Field(default="english", description="Language code")
    country: Optional[str] = Field(default=None, description="Country code")
    domain: Optional[str] = Field(default=None, description="Extracted domain")
    raw_metadata: Dict[str, Any] = Field(default_factory=dict, description="Original raw record")

    @field_validator("published_at", mode="before")
    @classmethod
    def parse_timestamp(cls, v: Any) -> datetime:
        if isinstance(v, datetime):
            return v if v.tzinfo is not None else v.replace(tzinfo=timezone.utc)
        if isinstance(v, (int, float)):
            return datetime.fromtimestamp(v, tz=timezone.utc)
        if isinstance(v, str):
            clean_str = v.strip().upper()
            if clean_str.endswith("Z"):
                clean_str = clean_str[:-1]
            elif clean_str.endswith("+00:00"):
                clean_str = clean_str[:-6]
            
            # GDELT formats usually like 20231015093000
            if len(clean_str) == 14 and clean_str.isdigit():
                try:
                    dt = datetime.strptime(clean_str, "%Y%m%d%H%M%S")
                    return dt.replace(tzinfo=timezone.utc)
                except ValueError:
                    pass
                    
            # Try ISO standard first
            try:
                dt = datetime.fromisoformat(clean_str)
                return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
            except ValueError:
                pass
                
            # Try common tabular date formats (e.g. YYYY-MM-DD HH:MM:SS)
            for fmt in (
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d",
                "%d/%m/%Y %H:%M:%S",
                "%d/%m/%Y",
                "%m/%d/%Y",
                "%Y/%m/%d",
            ):
                try:
                    dt = datetime.strptime(clean_str, fmt)
                    return dt.replace(tzinfo=timezone.utc)
                except ValueError:
                    continue
        raise ValueError(f"Unable to parse timestamp: {v!r}")
