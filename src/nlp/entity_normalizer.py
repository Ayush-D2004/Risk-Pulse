import pandas as pd
from typing import Dict, Any, Optional
import os

from src.ingestion.entity_registry import EntityRegistry

class EntityNormalizer:
    def __init__(self, registry_path: str = "data/processed/historical_instrument_registry.json"):
        self.registry = EntityRegistry()
        if os.path.exists(registry_path):
            import json
            with open(registry_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if "registry" in data:
                for entry in data["registry"]:
                    # map historical_instrument_registry fields to EntityRegistry fields
                    entity = {
                        "entity_id": entry.get("historical_ticker") or entry.get("source_entity_name"),
                        "canonical_name": entry.get("source_entity_name"),
                        "ticker": entry.get("historical_ticker"),
                        "aliases": [entry.get("source_entity_name")]
                    }
                    if entity["entity_id"]:
                        self.registry.add_entity(entity)
            else:
                self.registry.load_from_file(registry_path)
            
        self.publishers = {
            "reuters", "cnbc", "wsj", "cnn", "bloomberg", "ap", 
            "associated press", "fox news", "ft", "financial times", "nytimes"
        }

    def normalize(self, candidate_stock: str) -> Dict[str, Any]:
        cand = str(candidate_stock).strip() if pd.notna(candidate_stock) else ""
        cand_lower = cand.lower()
        
        if not cand:
            return {
                "candidate_entity": cand,
                "canonical_entity": "",
                "entity_status": "unresolved_entity",
                "entity_confidence": 0.0
            }
            
        if cand_lower in self.publishers:
            return {
                "candidate_entity": cand,
                "canonical_entity": "",
                "entity_status": "unresolved_source",
                "entity_confidence": 0.0
            }
            
        resolved = self.registry.resolve(cand)
        if resolved:
            return {
                "candidate_entity": cand,
                "canonical_entity": resolved.canonical_name or cand,
                "entity_status": "valid",
                "entity_confidence": resolved.confidence
            }
            
        return {
            "candidate_entity": cand,
            "canonical_entity": cand, # fallback to cand so it can still cluster if they are identical unresolved entities
            "entity_status": "unresolved_entity",
            "entity_confidence": 0.0
        }
