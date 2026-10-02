#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Validation Script for Event Clusterer
======================================
Validates the EventClusterer on a subset of the historical data.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from datetime import datetime, timezone

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
import numpy as np

from src.risk.risk_signal import RiskSignal, Evidence
from src.risk.event_clusterer import EventClusterer

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("data/processed/impact_scored_baseline.csv"))
    parser.add_argument("--n-rows", type=int, default=1000)
    args = parser.parse_args()

    df = pd.read_csv(args.input, on_bad_lines="skip")
    # Take a subset, prioritize MATERIAL_EVENT to have dense clusters
    material_df = df[df["EVENT_MATERIALITY"] == "MATERIAL_EVENT"].copy()
    if len(material_df) > args.n_rows:
        subset = material_df.head(args.n_rows)
    else:
        # Fill rest with non-material
        rest = df[df["EVENT_MATERIALITY"] != "MATERIAL_EVENT"].head(args.n_rows - len(material_df))
        subset = pd.concat([material_df, rest])

    # Synthetic Edge Cases Injection
    edge_cases = pd.DataFrame([
        # Case 1: Exact Duplicates
        {"DATE": "2023-10-01", "STOCK": "AAPL", "TWEET": "Apple announces new iPhone 15 Pro with titanium body.", "FINAL_EVENT_TYPE": "Product / Technology", "EVENT_MATERIALITY": "MATERIAL_EVENT"},
        {"DATE": "2023-10-01", "STOCK": "AAPL", "TWEET": "Apple announces new iPhone 15 Pro with titanium body.", "FINAL_EVENT_TYPE": "Product / Technology", "EVENT_MATERIALITY": "MATERIAL_EVENT"},
        
        # Case 2: Near-duplicates (Retweet/Slight modification)
        {"DATE": "2023-10-01", "STOCK": "AAPL", "TWEET": "RT @tech Apple just announced the new iPhone 15 Pro featuring a titanium body!", "FINAL_EVENT_TYPE": "Product / Technology", "EVENT_MATERIALITY": "MATERIAL_EVENT"},
        
        # Case 3: Same event / different wording
        {"DATE": "2023-10-01", "STOCK": "AAPL", "TWEET": "The tech giant from Cupertino has finally unveiled the titanium-clad iPhone 15 Pro.", "FINAL_EVENT_TYPE": "Product / Technology", "EVENT_MATERIALITY": "MATERIAL_EVENT"},
        
        # Case 4: Same entity / different events (Should NOT cluster)
        {"DATE": "2023-10-01", "STOCK": "AAPL", "TWEET": "Apple CEO Tim Cook to testify in Epic Games antitrust trial today.", "FINAL_EVENT_TYPE": "Regulatory / Legal", "EVENT_MATERIALITY": "MATERIAL_EVENT"},
        {"DATE": "2023-10-02", "STOCK": "AAPL", "TWEET": "Apple acquires AI startup for $200 million to boost Siri capabilities.", "FINAL_EVENT_TYPE": "Merger & Acquisition", "EVENT_MATERIALITY": "MATERIAL_EVENT"},
        
        # Case 5: Cross-source / Temporally spaced (Same event, reported next day)
        {"DATE": "2023-10-02", "STOCK": "AAPL", "TWEET": "New WSJ report confirms the iPhone 15 Pro's titanium chassis reduces weight significantly.", "FINAL_EVENT_TYPE": "Product / Technology", "EVENT_MATERIALITY": "MATERIAL_EVENT"}
    ])
    subset = pd.concat([edge_cases, subset], ignore_index=True)

    print(f"Loaded {len(subset)} rows for clustering validation (including 7 injected edge cases).")

    clusterer = EventClusterer()
    
    signals = []
    
    # We need some timestamps. Let's assume the rows don't have timestamp, or we mock them.
    # We can use row index to space them out by 1 hour.
    base_time = datetime(2023, 1, 1, tzinfo=timezone.utc)

    print("Processing signals into EventClusterer...")
    for idx, (_, row) in enumerate(subset.iterrows()):
        # Use actual DATE column
        date_str = str(row.get("DATE", "2023-01-01"))
        
        # Build RiskSignal
        # We need to map dataframe columns to RiskSignal fields
        entity = str(row.get("STOCK", "UNKNOWN"))
        text = str(row.get("TWEET", ""))
        event_type = str(row.get("FINAL_EVENT_TYPE", "NO_EVENT"))
        materiality = str(row.get("EVENT_MATERIALITY", "NO_EVENT"))
        confidence = float(row.get("EVENT_CONFIDENCE", 0.5))
        if pd.isna(confidence): confidence = 0.5
        sentiment = float(row.get("FINBERT_SCORE", 0.0))
        if pd.isna(sentiment): sentiment = 0.0
        
        signal = RiskSignal(
            entity=entity,
            source="twitter",
            sentiment_score=sentiment,
            event_type=event_type,
            event_confidence=confidence,
            materiality=materiality,
            timestamp=date_str,
            evidence=Evidence(text=text, url=f"mock://{row.get('row_id', idx)}")
        )
        
        clusterer.process_signal(signal)
        signals.append(signal)
        
        if (idx + 1) % 100 == 0:
            print(f"Processed {idx + 1} signals...")

    clusters = clusterer.clusters
    print(f"\nClustering complete. Formed {len(clusters)} clusters from {len(subset)} signals.")
    
    # Diagnostics
    sizes = [c.size for c in clusters]
    print(f"\nCluster Sizes:")
    print(f"  Mean: {np.mean(sizes):.2f}")
    print(f"  Max:  {np.max(sizes)}")
    print(f"  Singletons (size=1): {sum(1 for s in sizes if s == 1)}")
    print(f"  Multiple (size>1): {sum(1 for s in sizes if s > 1)}")
    
    print("\nTop 5 Largest Clusters:")
    largest = sorted(clusters, key=lambda c: c.size, reverse=True)[:5]
    for i, c in enumerate(largest, 1):
        print(f"\n--- Cluster {i} (Size: {c.size}) ---")
        print(f"Entity: {c.entity} | Event Type: {c.event_type}")
        print("Candidates:")
        for cand in c.candidates[:5]:
            print(f"  - (Novelty: {cand.signal.novelty:.2f}) {cand.text_for_embedding[:80]}...")
        if c.size > 5:
            print(f"  ... and {c.size - 5} more")

if __name__ == "__main__":
    main()
