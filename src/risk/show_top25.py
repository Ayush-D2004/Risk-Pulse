# -*- coding: utf-8 -*-
import pandas as pd

df = pd.read_csv("data/processed/impact_scored_baseline.csv")
top25 = df.sort_values(by=["IMPACT_SCORE", "RAW_COMPOSITE"], ascending=[False, False]).head(25)

print(f"{'#':<3} {'Row':<5} {'Score':<6} {'Tier':<16} {'Event Type':<22} {'Stock':<10} {'Conf':<5} {'Sent':<6} {'Tweet Snippet'}")
print("-" * 120)
for i, (_, r) in enumerate(top25.iterrows(), 1):
    clean_txt = str(r["TWEET"]).replace("\n", " ")[:65]
    print(f"{i:<3} {r['row_id']:<5} {r['IMPACT_SCORE']:<6.2f} {r['IMPACT_TIER']:<16} {r['FINAL_EVENT_TYPE']:<22} {r['STOCK']:<10} {r['EVENT_CONFIDENCE']:<5.2f} {r['FINBERT_SCORE']:<+6.2f} {clean_txt}...")

print("\nTOP 15 NON-GEOPOLITICAL MATERIAL EVENTS:")
print("-" * 120)
non_geo = df[(df["EVENT_MATERIALITY"] == "MATERIAL_EVENT") & (df["FINAL_EVENT_TYPE"] != "Geopolitical")]
top_non_geo = non_geo.sort_values(by=["IMPACT_SCORE", "RAW_COMPOSITE"], ascending=[False, False]).head(15)
for i, (_, r) in enumerate(top_non_geo.iterrows(), 1):
    clean_txt = str(r["TWEET"]).replace("\n", " ")[:65]
    print(f"{i:<3} {r['row_id']:<5} {r['IMPACT_SCORE']:<6.2f} {r['IMPACT_TIER']:<16} {r['FINAL_EVENT_TYPE']:<22} {r['STOCK']:<10} {r['EVENT_CONFIDENCE']:<5.2f} {r['FINBERT_SCORE']:<+6.2f} {clean_txt}...")
