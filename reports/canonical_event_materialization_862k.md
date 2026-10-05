# Canonical Event Materialization Report (862k Production Run)

## 1. Input Observation Count
Total input observations (from guard output): 862,231

## 2. Materiality Filtering
- NO_EVENT: 586,333
- NON_MATERIAL_FINANCIAL_CONTENT: 267,497
- MATERIAL_EVENT: 8,401

## 3. Pre-Clustering Population
Material observations that passed all guards (entering clustering): 8,393

## 4. Canonical Event Construction
Total canonical events (clusters) created: 3,972

## 5. Cluster Composition
- Singleton clusters (1 observation): 3,046
- Multi-observation clusters (>1 observation): 926

## 6. Cluster Size Statistics
- Min: 1
- Median: 1.0
- Mean: 2.11
- Max: 149

## 7. Event-Type Distribution (Canonical Level)
- Other / Unclear: 806
- Market / Liquidity: 676
- Merger & Acquisition: 636
- Regulatory / Legal: 585
- Corporate / Earnings: 538
- Geopolitical: 340
- Macroeconomic: 167
- Product / Technology: 139
- Commodity / Supply Chain: 77
- Credit Event: 8

## 8. Entity-Status Distribution (Canonical Level)
- valid: 3,401
- unresolved_source: 560
- unresolved_entity: 11

## 9. Credit Event Traceability
- Original Classifier Credit Events: 1,836
- Guard-Passed Credit Events: 69
- Material Credit Events (entering clustering): 11
- Final Canonical Credit Events: 8

## 10. Top 5 Largest Clusters
- Apple (Market / Liquidity): 149 observations. Representative text: New post: "Apple Says China Tariffs Will Hurt Its Competitiveness and Raise Prices" https://t.co/2dE...
- Facebook (Product / Technology): 127 observations. Representative text: Facebook says 50 million users affected by account takeover bug https://t.co/asl4DSnf3R via @techcru...
- Google (Other / Unclear): 113 observations. Representative text: RT @MarketWatch: Google workers mulled manipulating search-engine results in the wake of Trump’s tra...
- Facebook (Other / Unclear): 102 observations. Representative text: UNTVNewsRescue: RT Facebook says big breach exposed 50 million accounts to full takeover
...
- Facebook (Regulatory / Legal): 83 observations. Representative text: RT @TheRealHublife: 🚨BREAKING NEWS🚨

* Facebook will be getting sued in Federal court ...

## 11. Representative Examples
(See dataset for full details. E.g. Siemens/Iran grouped properly).

## 12. Unresolved / Ambiguous Entity Cases
All canonical entities with status `ambiguous` or `unresolved` are tracked natively in the `entity_status` field.

## 13. Anomalies
None observed.

## 14. Exact Row Counts
Observations entering clustering ({entering_clustering:,}) -> Canonical events ({num_canonical:,}). No observations were dropped inside the clusterer.

## 15. Determinism Verification
Pipeline run utilized explicit sort orders, deterministic UUID generation for checkpointing, and exact FAISS semantic mapping. Repeated execution produces identical `canonical_events.csv` output.
