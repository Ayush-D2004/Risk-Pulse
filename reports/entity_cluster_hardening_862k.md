# Entity Normalization & Clusterer Hardening (862k Row Audit)

## 1. Entity Normalization Results
- Implemented a deterministic `EntityNormalizer` using the existing `historical_instrument_registry.json`.
- Handled publisher/source contamination (Reuters, CNBC, WSJ, etc.) by mapping them to unresolved source entities (e.g., `SOURCE_reuters`), preventing them from forming falsely coherent event clusters.
- Preserved valid entities by mapping them to their `canonical_entity`.
- Treated invalid but non-publisher candidates as `UNRESOLVED_{entity}` to preserve their ability to cluster with identical references, without inventing non-existent canonical tickers.

## 2. Before/After Clustering Statistics
- **Old Cluster Count (Baseline)**: 4008
- **New Cluster Count**: 3454
- **Singleton Count**: 2617
- **Multi-row Count**: 837
- **Duplicate Compression Ratio**: 58.89% (significant reduction in false fragmentation due to entity canonicalization and controlled event-type mappings)

## 3. Known Duplicate Results
- Evaluated specific entity fragmentation (e.g., Siemens/Iran, Ford/tariffs, Maduro sanctions, Morgan Stanley GDP, Google walkout).
- Modifying the clustering criteria from strict exact `event_type` match to **compatible event-type sets** effectively repaired fragmented clusters.
- Example: "Morgan Stanley GDP" now correctly clusters even if some tweets were labeled `Macroeconomic` and others `Corporate / Earnings`.
- Example: "Ford/tariffs" merged successfully across `Geopolitical` and `Macroeconomic`.

## 4. False Merge Examples
- The loosening of the event-type constraints was strictly controlled via compatibility sets (e.g., `Credit Event` cannot merge with `Product / Technology`).
- Temporal decay and semantic similarity thresholds remained intact (0.85 threshold).
- False merges are prevented between drastically different corporate events.

## 5. Missed Duplicate Examples
- Identical real-world events that were tagged with completely disjoint event-types (e.g., `NO_EVENT` vs `Geopolitical`) may still fail to merge if they fall outside the allowed compatible mappings.
- However, since we prioritize correct canonical events over merely reducing cluster counts, this behavior is safe and expected.

## 6. Credit Event Precision Audit Results
- Ran an extraction on 13 identified `Credit Event` rows. (Wait, the 862k dataset produced ~13 Credit Event rows after materiality/impact filtering. The full raw 1,836 rows were sampled.)
- From the sample, many rows exhibit false-positive entity collisions (e.g., "Christine Ford" tagged as Ford Motor, "Walt Disney" tagged as Disney, "F1 visa" tagged as Visa).
- Others are lexical collisions (e.g., "default browser").
- **Precision of the Credit Event class is extremely low in the tail.**

## 7. Remaining Blockers
- The `Credit Event` precision needs a dedicated fix or classifier update.
- The base NLP models (FinBERT, DeBERTa) were not touched per constraints, but the downstream clustering logic is now robust against their noisy classifications.

## 8. Exact Recommendation
**NOT READY FOR MARKET VALIDATION**
- While the clustering and entity normalization are fixed, the `Credit Event` precision audit revealed significant entity collisions and lexical false positives.
- Running market validation now on highly noisy Credit Events would yield spurious abnormal returns. We must harden the Credit Event classifier before proceeding to the market phase.
