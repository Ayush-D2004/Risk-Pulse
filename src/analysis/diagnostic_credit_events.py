import pandas as pd
import numpy as np
import os
import hashlib
from src.nlp.entity_normalizer import EntityNormalizer

def main():
    print("Loading data...")
    try:
        df = pd.read_csv("data/pipeline_output/impact_scored.csv")
    except Exception:
        df = pd.read_csv("data/processed/impact_scored_baseline.csv")
        
    print(f"Total rows in dataset: {len(df)}")
    
    # Reconcile Credit Event Populations
    # The authoritative starting population is 1,836 rows where EVENT_TYPE == 'Credit Event'
    ce_df = df[df["EVENT_TYPE"] == "Credit Event"].copy()
    
    total_ce = len(ce_df)
    ce_no_event = len(ce_df[ce_df["EVENT_MATERIALITY"] == "NO_EVENT"])
    ce_non_material = len(ce_df[ce_df["EVENT_MATERIALITY"] == "NON_MATERIAL_FINANCIAL_CONTENT"])
    ce_material = len(ce_df[ce_df["EVENT_MATERIALITY"] == "MATERIAL_EVENT"])
    ce_impact_8 = len(ce_df[ce_df["IMPACT_SCORE"] >= 8.0])
    ce_impact_7 = len(ce_df[ce_df["IMPACT_SCORE"] >= 7.0])
    ce_final_ce = len(ce_df[ce_df["FINAL_EVENT_TYPE"] == "Credit Event"])
    
    # 13 rows were left in FINAL_EVENT_TYPE. Let's trace it.
    ce_final_and_material = len(ce_df[(ce_df["FINAL_EVENT_TYPE"] == "Credit Event") & (ce_df["EVENT_MATERIALITY"] == "MATERIAL_EVENT")])
    
    reconciliation = f"""
1. RECONCILE THE CREDIT EVENT POPULATIONS
==================================================
Total Credit Event rows (EVENT_TYPE == 'Credit Event'): {total_ce}
Credit Event + NO_EVENT (materiality): {ce_no_event}
Credit Event + NON_MATERIAL_FINANCIAL_CONTENT (materiality): {ce_non_material}
Credit Event + MATERIAL_EVENT: {ce_material}
Credit Event + impact >= 8: {ce_impact_8}
Credit Event + impact >= 7: {ce_impact_7}
Credit Event surviving as FINAL_EVENT_TYPE == 'Credit Event': {ce_final_ce}
Credit Event surviving as FINAL_EVENT_TYPE == 'Credit Event' AND MATERIAL_EVENT: {ce_final_and_material}
"""
    print(reconciliation)
    with open("reports/reconciliation.txt", "w") as f:
        f.write(reconciliation)

    # 2. BUILD A FULL CREDIT ERROR TAXONOMY
    # Stratified audit sample of 200 rows.
    np.random.seed(42)
    
    # We want to stratify. Let's just group by materiality and impact tier and sample proportionally, ensuring high-impact are included.
    high_impact = ce_df[ce_df["IMPACT_SCORE"] >= 7.0]
    others = ce_df[ce_df["IMPACT_SCORE"] < 7.0]
    
    sample_size = min(200, total_ce)
    hi_count = len(high_impact)
    other_count = sample_size - hi_count
    
    if other_count > 0:
        other_sample = others.sample(n=min(other_count, len(others)))
        audit_sample = pd.concat([high_impact, other_sample])
    else:
        audit_sample = high_impact.sample(n=sample_size)
        
    normalizer = EntityNormalizer()
    audit_rows = []
    
    for idx, row in audit_sample.iterrows():
        cand = str(row.get("STOCK", ""))
        text = str(row.get("TWEET", ""))
        tweet_hash = hashlib.md5(text.encode('utf-8')).hexdigest()
        
        norm_res = normalizer.normalize(cand)
        
        audit_rows.append({
            "row_id": str(row.get("row_id", idx)),
            "tweet_hash": tweet_hash,
            "text": text,
            "candidate_entity": norm_res["candidate_entity"],
            "canonical_entity": norm_res["canonical_entity"],
            "entity_status": norm_res["entity_status"],
            "date": str(row.get("DATE", "")),
            "event_type": row.get("EVENT_TYPE", ""),
            "materiality": row.get("EVENT_MATERIALITY", ""),
            "impact_score": row.get("IMPACT_SCORE", 0.0),
            "sentiment": row.get("FINBERT_SCORE", 0.0),
            "source_author": str(row.get("AUTHOR", "")) # if available
        })
        
    audit_df = pd.DataFrame(audit_rows)
    os.makedirs("reports", exist_ok=True)
    audit_df.to_csv("reports/credit_event_audit_200.csv", index=False)
    print("Created reports/credit_event_audit_200.csv")
    
if __name__ == "__main__":
    main()
