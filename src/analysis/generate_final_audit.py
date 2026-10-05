import pandas as pd
import numpy as np
import os
import hashlib

from src.nlp.entity_normalizer import EntityNormalizer

def main():
    print("Loading impact_scored.csv for audit generation...")
    df = pd.read_csv("data/pipeline_output/impact_scored.csv")
    
    # We want a sample for the final audit artifact.
    # Let's say we sample 500 rows.
    np.random.seed(42)
    sample = df.sample(n=min(500, len(df))).copy()
    
    normalizer = EntityNormalizer()
    
    audit_rows = []
    
    for idx, row in sample.iterrows():
        cand = str(row.get("STOCK", ""))
        text = str(row.get("TWEET", ""))
        
        # Hash text for tweet_hash
        tweet_hash = hashlib.md5(text.encode('utf-8')).hexdigest()
        
        norm_res = normalizer.normalize(cand)
        
        audit_row = {
            "row_id": str(row.get("row_id", idx)),
            "tweet_hash": tweet_hash,
            "text": text,
            "candidate_entity": norm_res["candidate_entity"],
            "canonical_entity": norm_res["canonical_entity"],
            "entity_status": norm_res["entity_status"],
            "date": str(row.get("DATE", "")),
            "event_type": str(row.get("FINAL_EVENT_TYPE", row.get("EVENT_TYPE", "NO_EVENT"))),
            "materiality": str(row.get("EVENT_MATERIALITY", "NON_MATERIAL")),
            "sentiment_score": row.get("FINBERT_SCORE", 0.0),
            "impact_score": row.get("IMPACT_SCORE", 1.0)
        }
        # ensure no nan
        if pd.isna(audit_row["row_id"]) or audit_row["row_id"] == "nan":
            audit_row["row_id"] = str(idx)
        if pd.isna(audit_row["materiality"]) or audit_row["materiality"] == "nan":
            audit_row["materiality"] = "NON_MATERIAL"
            
        audit_rows.append(audit_row)
        
    audit_df = pd.DataFrame(audit_rows)
    os.makedirs("reports", exist_ok=True)
    audit_df.to_csv("reports/event_cluster_audit_samples_862k.csv", index=False)
    print("Created reports/event_cluster_audit_samples_862k.csv with full traceability fields.")

if __name__ == "__main__":
    main()
