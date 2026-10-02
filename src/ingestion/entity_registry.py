import json
import re
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from pathlib import Path

@dataclass
class ResolvedEntity:
    entity_id: str
    canonical_name: str
    ticker: Optional[str]
    confidence: float
    resolution_method: str

class EntityRegistry:
    def __init__(self):
        # Database of entities: entity_id -> metadata
        self.entities: Dict[str, Dict[str, Any]] = {}
        # Inverted index: normalized_alias -> entity_id
        self.alias_index: Dict[str, str] = {}
        
        # Regex for dropping common corporate suffixes
        self.suffix_regex = re.compile(r'\b(inc|corp|corporation|llc|plc|ltd|company|co)\.?$', re.IGNORECASE)

    def load_from_file(self, filepath: str):
        path = Path(filepath)
        if not path.exists():
            return
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            for entity in data:
                self.add_entity(entity)

    def add_entity(self, entity_data: Dict[str, Any]):
        entity_id = entity_data['entity_id']
        self.entities[entity_id] = entity_data
        
        # Index canonical name
        canonical = entity_data.get('canonical_name', '').lower()
        if canonical:
            self.alias_index[canonical] = entity_id
            
        # Index ticker
        ticker = entity_data.get('ticker')
        if ticker:
            self.alias_index[ticker.lower()] = entity_id
            
        # Index aliases
        for alias in entity_data.get('aliases', []):
            self.alias_index[alias.lower()] = entity_id

    def normalize_string(self, text: str) -> str:
        text = text.lower().strip()
        # Remove suffixes like " inc.", " corp"
        text = self.suffix_regex.sub('', text).strip()
        # Remove punctuation
        text = re.sub(r'[^\w\s]', '', text)
        return text.strip()

    def resolve(self, surface_form: str, context: Optional[str] = None) -> Optional[ResolvedEntity]:
        """Resolve a string to a known entity using multiple retrieval methods."""
        # 1. Exact Match (case insensitive)
        exact_lower = surface_form.lower().strip()
        if exact_lower in self.alias_index:
            entity_id = self.alias_index[exact_lower]
            return self._build_resolved(entity_id, 1.0, "exact_match")
            
        # 2. Normalized Match (remove suffixes, punctuation)
        norm_text = self.normalize_string(surface_form)
        if norm_text and norm_text in self.alias_index:
            entity_id = self.alias_index[norm_text]
            return self._build_resolved(entity_id, 0.85, "normalized_match")
            
        # Fallback / Unresolved
        return None
        
    def _build_resolved(self, entity_id: str, confidence: float, method: str) -> ResolvedEntity:
        entity = self.entities[entity_id]
        return ResolvedEntity(
            entity_id=entity_id,
            canonical_name=entity.get('canonical_name', ''),
            ticker=entity.get('ticker'),
            confidence=confidence,
            resolution_method=method
        )
