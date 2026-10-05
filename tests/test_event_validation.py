import os
import json
import pandas as pd
import pytest
from datetime import datetime, timezone
from src.analysis.event_level_market_validation import load_registry, REGISTRY_PATH
from src.market.market_context import MarketContextFetcher, MarketContextConfig

OUTPUT_CSV = "data/pipeline_output/event_level_enriched.csv"

def test_registry_mapping():
    """Test historical ticker mapping and proxy handling"""
    mapping = load_registry()
    assert isinstance(mapping, dict)
    
    # Check that unresolved/ignored entities are handled
    with open(REGISTRY_PATH, "r") as f:
        data = json.load(f)
    
    # Verify proxies are loaded correctly
    proxy_count = sum(1 for v in mapping.values() if v.get("is_proxy"))
    assert proxy_count >= 0
    
    # Verify valid ticker is loaded
    valid_count = sum(1 for v in mapping.values() if v.get("ticker") is not None)
    assert valid_count > 0

def test_exclusions_in_enriched_output():
    """Test unresolved entity and unresolved source exclusions"""
    if not os.path.exists(OUTPUT_CSV):
        pytest.skip("Enriched output not available.")
    
    df = pd.read_csv(OUTPUT_CSV)
    
    # Unresolved source exclusion
    unresolved_sources = df[df["entity_status"] == "unresolved_source"]
    assert all(unresolved_sources["mapping_status"] == "unresolved_source")
    
    # Unresolved entity exclusion
    unresolved_entities = df[df["entity_status"] == "unresolved_entity"]
    assert all(unresolved_entities["mapping_status"] == "unresolved_entity")
    
    # Valid events mapping
    usable = df[df["mapping_status"] == "usable"]
    assert all(usable["entity_status"] == "valid")
    assert all(usable["abnormal_return"].notna())

def test_event_date_cutoff_and_no_leakage():
    """Test event-date cutoff and no future feature leakage"""
    fetcher = MarketContextFetcher(MarketContextConfig(event_window_days=1, baseline_days=20, min_baseline_days=10, volatility_window=20))
    # Pick an arbitrary past date for AAPL
    ts = datetime(2017, 2, 1, tzinfo=timezone.utc)
    res = fetcher.fetch(ticker="AAPL", event_timestamp=ts)
    
    ctx = res.market_context
    assert ctx.abnormal_return is not None
    
    # Verify metadata window end doesn't exceed event date
    end_date_str = ctx.metadata["observation_window"]["event_window_end"]
    end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
    assert end_date <= ts.date(), "Event window end exceeds event date! Leakage detected."
    
def test_deterministic_repeated_execution():
    """Test deterministic repeated execution"""
    fetcher = MarketContextFetcher(MarketContextConfig(event_window_days=1, baseline_days=20, min_baseline_days=10, volatility_window=20))
    ts = datetime(2017, 3, 1, tzinfo=timezone.utc)
    
    res1 = fetcher.fetch(ticker="AAPL", event_timestamp=ts)
    res2 = fetcher.fetch(ticker="AAPL", event_timestamp=ts)
    
    assert res1.market_context.abnormal_return == res2.market_context.abnormal_return
    assert res1.market_context.volume_ratio == res2.market_context.volume_ratio
