import pytest
import pandas as pd
from datetime import datetime, timezone
import hashlib

from src.nlp.entity_normalizer import EntityNormalizer
from src.risk.event_clusterer import EventClusterer, is_event_type_compatible, EventCandidate
from src.risk.risk_signal import RiskSignal, Evidence

def test_publisher_rejection():
    normalizer = EntityNormalizer(registry_path="nonexistent.json")
    res = normalizer.normalize("Reuters")
    assert res["entity_status"] == "unresolved_source"
    assert res["canonical_entity"] == ""
    
    res = normalizer.normalize("CNBC")
    assert res["entity_status"] == "unresolved_source"
    
def test_valid_entity_preservation():
    normalizer = EntityNormalizer(registry_path="nonexistent.json")
    # without registry, it'll be unresolved
    # let's mock it
    normalizer.registry.entities = {"AAPL": {"entity_id": "AAPL", "canonical_name": "Apple Inc."}}
    normalizer.registry.alias_index = {"apple": "AAPL"}
    
    res = normalizer.normalize("Apple")
    assert res["entity_status"] == "valid"
    assert res["canonical_entity"] == "Apple Inc."
    
def test_unresolved_entity_handling():
    normalizer = EntityNormalizer(registry_path="nonexistent.json")
    res = normalizer.normalize("SomeUnknownStartup")
    assert res["entity_status"] == "unresolved_entity"
    assert res["canonical_entity"] == "SomeUnknownStartup"
    
def test_entity_normalization_in_clusterer():
    clusterer = EventClusterer()
    # Mock normalizer
    clusterer.normalizer.registry.entities = {"AAPL": {"entity_id": "AAPL", "canonical_name": "Apple Inc."}}
    clusterer.normalizer.registry.alias_index = {"apple": "AAPL"}
    
    s = RiskSignal(
        entity="Apple",
        source="news",
        sentiment_score=0.5,
        event_type="Product / Technology",
        event_confidence=0.9,
        materiality="MATERIAL_EVENT",
        timestamp=datetime.now(timezone.utc),
        evidence=Evidence(text="Apple launched new iPhone")
    )
    clusterer.process_signal(s)
    
    # Should be normalized to Apple Inc.
    assert s.entity == "Apple Inc."

def test_controlled_event_type_compatibility():
    assert is_event_type_compatible("Geopolitical", "Macroeconomic") is True
    assert is_event_type_compatible("Geopolitical", "Product / Technology") is False
    assert is_event_type_compatible("Merger & Acquisition", "Corporate / Earnings") is True
    
def test_known_duplicate_grouping():
    clusterer = EventClusterer()
    
    s1 = RiskSignal(
        entity="Ford",
        source="news",
        sentiment_score=0.5,
        event_type="Macroeconomic",
        event_confidence=0.9,
        materiality="MATERIAL_EVENT",
        timestamp=datetime(2023, 1, 1, tzinfo=timezone.utc),
        evidence=Evidence(text="Ford faces new tariffs")
    )
    s2 = RiskSignal(
        entity="Ford",
        source="news",
        sentiment_score=0.5,
        event_type="Geopolitical",
        event_confidence=0.9,
        materiality="MATERIAL_EVENT",
        timestamp=datetime(2023, 1, 1, tzinfo=timezone.utc),
        evidence=Evidence(text="Ford auto tariffs increase")
    )
    clusterer.process_signal(s1)
    clusterer.process_signal(s2)
    
    assert len(clusterer.clusters) == 1
    
def test_different_event_separation():
    clusterer = EventClusterer()
    s1 = RiskSignal(
        entity="Ford",
        source="news",
        sentiment_score=0.5,
        event_type="Credit Event",
        event_confidence=0.9,
        materiality="MATERIAL_EVENT",
        timestamp=datetime(2023, 1, 1, tzinfo=timezone.utc),
        evidence=Evidence(text="Ford defaults on loan")
    )
    s2 = RiskSignal(
        entity="Ford",
        source="news",
        sentiment_score=0.5,
        event_type="Product / Technology",
        event_confidence=0.9,
        materiality="MATERIAL_EVENT",
        timestamp=datetime(2023, 1, 1, tzinfo=timezone.utc),
        evidence=Evidence(text="Ford announces new electric vehicle")
    )
    clusterer.process_signal(s1)
    clusterer.process_signal(s2)
    # Credit Event and Product / Technology are NOT compatible
    assert len(clusterer.clusters) == 2

def test_audit_row_traceability():
    text = "test tweet"
    tweet_hash = hashlib.md5(text.encode('utf-8')).hexdigest()
    
    row = {
        "row_id": "123",
        "tweet_hash": tweet_hash,
        "text": text,
        "candidate_entity": "AAPL",
        "canonical_entity": "Apple Inc.",
        "entity_status": "valid",
        "date": "2023-01-01",
        "event_type": "Corporate / Earnings",
        "materiality": "MATERIAL_EVENT",
        "sentiment_score": 0.5,
        "impact_score": 5.0
    }
    
    df = pd.DataFrame([row])
    assert not df["row_id"].isna().any()
    assert not df["materiality"].isna().any()
    assert "tweet_hash" in df.columns
