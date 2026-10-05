import pandas as pd
import sys
from pathlib import Path
from collections import Counter
import numpy as np

from src.risk.risk_signal import RiskSignal, Evidence
from src.risk.event_clusterer import EventClusterer

def main():
    print("Loading data...")
    # Load the file containing material rows. 
    # Try impact_scored.csv or impact_scored_baseline.csv
    try:
        df = pd.read_csv("data/pipeline_output/impact_scored.csv")
    except Exception:
        df = pd.read_csv("data/processed/impact_scored_baseline.csv")
        
    material_df = df[df["EVENT_MATERIALITY"] == "MATERIAL_EVENT"].copy()
    if len(material_df) == 0:
        # try another col
        material_df = df[df["materiality_label"] == "MATERIAL"].copy() if "materiality_label" in df.columns else df
    
    print(f"Loaded {len(material_df)} material rows.")

    clusterer = EventClusterer()
    
    for idx, row in material_df.iterrows():
        entity = str(row.get("STOCK", ""))
        text = str(row.get("TWEET", ""))
        event_type = str(row.get("FINAL_EVENT_TYPE", "NO_EVENT"))
        if event_type == "nan" or not event_type:
            event_type = "NO_EVENT"
        materiality = str(row.get("EVENT_MATERIALITY", "MATERIAL_EVENT"))
        date_str = str(row.get("DATE", "2023-01-01"))
        
        signal = RiskSignal(
            entity=entity,
            source="twitter",
            sentiment_score=0.0,
            event_type=event_type,
            event_confidence=1.0,
            materiality=materiality,
            timestamp=date_str,
            evidence=Evidence(text=text, url=f"mock://{row.get('row_id', idx)}")
        )
        
        clusterer.process_signal(signal)
        
    clusters = clusterer.clusters
    print(f"New cluster count: {len(clusters)}")
    sizes = [c.size for c in clusters]
    singletons = sum(1 for s in sizes if s == 1)
    multi = sum(1 for s in sizes if s > 1)
    
    print(f"Singleton count: {singletons}")
    print(f"Multi-row count: {multi}")
    print(f"Duplicate compression ratio: {1.0 - len(clusters) / len(material_df):.4f}")
    
    dist = Counter(sizes)
    print("Cluster-size distribution:", dict(dist))
    
    # Save a report for manual audit
    with open("reports/recluster_audit.txt", "w") as f:
        f.write(f"Old Cluster Count Baseline: 4008\n")
        f.write(f"New Cluster Count: {len(clusters)}\n")
        f.write(f"Singleton Count: {singletons}\n")
        f.write(f"Multi-row Count: {multi}\n")
        
    # We will test specific entities: Siemens, Ford, Maduro, Morgan Stanley, Google
    print("Checking specific audits:")
    for c in clusters:
        ents = c.entity.lower()
        if "siemens" in ents or "ford" in ents or "maduro" in ents or "morgan stanley" in ents or "google" in ents:
            if c.size > 1:
                print(f"Cluster: {c.entity} | Type: {c.event_type} | Size: {c.size}")

if __name__ == "__main__":
    main()
