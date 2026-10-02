import json
import os
import hashlib
from typing import List, Dict, Any
from datetime import datetime
import requests
from src.ingestion.models import NewsDocument

class GDELTClient:
    def __init__(self, raw_dir: str = "data/raw/gdelt", processed_dir: str = "data/processed/gdelt"):
        self.raw_dir = raw_dir
        self.processed_dir = processed_dir
        os.makedirs(self.raw_dir, exist_ok=True)
        os.makedirs(self.processed_dir, exist_ok=True)

    def fetch_live(self, query: str = "", max_records: int = 250) -> List[Dict[str, Any]]:
        """Fetch live records from GDELT 2.0 DOC API and save raw dump."""
        url = "https://api.gdeltproject.org/api/v2/doc/doc"
        params = {
            "query": query,
            "mode": "artlist",
            "format": "json",
            "maxrecords": max_records
        }
        
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        
        # Persist raw output for reproducibility
        timestamp_str = datetime.now().strftime("%Y%m%d%H%M%S")
        raw_filepath = os.path.join(self.raw_dir, f"gdelt_raw_{timestamp_str}.json")
        with open(raw_filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            
        return data.get("articles", [])
        
    def fetch_replay(self, filepath: str) -> List[Dict[str, Any]]:
        """Replay ingestion from a saved raw GDELT dump."""
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Handle cases where it's a list or a dict containing "articles"
        if isinstance(data, dict):
            return data.get("articles", [])
        elif isinstance(data, list):
            return data
        return []
        
    def normalize(self, raw_articles: List[Dict[str, Any]]) -> List[NewsDocument]:
        """Normalize GDELT specific schema to the generic NewsDocument schema."""
        docs = []
        for article in raw_articles:
            url = article.get("url", "")
            if not url:
                continue
                
            title = article.get("title", "")
            if not title:
                title = "Untitled"
                
            domain = article.get("domain", "")
            # GDELT time format: 20231015093000Z or similar
            seendate = article.get("seendate", "") 
            if not seendate:
                # If completely missing, skip or mock
                continue
                
            language = article.get("language", "English")
            country = article.get("sourcecountry", "")
            
            # Create deterministic ID
            doc_id = hashlib.sha256((url + title).encode("utf-8")).hexdigest()
            
            try:
                doc = NewsDocument(
                    document_id=doc_id,
                    source="GDELT",
                    publisher=domain,
                    title=title,
                    url=url,
                    published_at=seendate,
                    language=language.lower(),
                    country=country,
                    domain=domain,
                    raw_metadata=article
                )
                docs.append(doc)
            except Exception as e:
                print(f"Skipping article due to normalization error: {e}")
                # Silently drop malformed records (e.g. unparseable timestamp)
                continue
                
        return docs
