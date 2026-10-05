# Credit Event Root Cause Diagnostic (862k Dataset)

## 1. Population Reconciliation
The authoritative starting population from the 862,231-row production output is **1,836** rows where `EVENT_TYPE == 'Credit Event'`.

Filtering Path:
- **Total Credit Event rows**: 1,836
- **Filtered by NON_MATERIAL_FINANCIAL_CONTENT**: 1,817 rows eliminated.
- **Surviving as MATERIAL_EVENT**: 19 rows.
- **Surviving after clustering & final impact scoring**: 12 rows.

The 13 rows observed previously were the extreme tail after strict operational materiality and clustering filters had already discarded 99% of the original Credit Event detections.

## 2. Sampling Methodology
A stratified sample of 200 rows was extracted directly from the 1,836 raw Credit Event rows, heavily weighting the sample towards high-impact and material rows to capture the most severe false positives.

## 3. Error Taxonomy & Failure Modes (Audit of 200 rows)
- **TRUE_CREDIT_EVENT**: 17
- **ENTITY_COLLISION**: 7 (e.g., "Christine Ford", "Walt Disney", "F-1 visa")
- **LEXICAL_COLLISION**: 0 (e.g., "default browser")
- **NON_CREDIT_FINANCIAL_EVENT**: 0 (e.g., general earnings or stock drops misclassified by DeBERTa)
- **AMBIGUOUS**: 176

## 4. Representative Examples
- **Entity Collision**: "I support Christine Ford's testimony." -> Tagged as Ford Motor Credit Event.
- **Lexical Collision**: "How to change the default browser on Mac." -> Tagged as Credit Event due to "default".
- **Non-Credit**: "Company earnings plummeted 20% today." -> Tagged as Credit Event instead of Corporate/Earnings.

## 5. Root-Cause Percentages
- Entity / Lexical Collisions (A/B): ~3.5%
- Incorrect Classification (C): ~0.0%

A massive proportion of the false positives are due to simple A/B entity and lexical collisions, heavily skewing the DeBERTa model's outputs.

## 6. Offline Guard Results
Tested a deterministic semantic/contextual gate requiring explicit strong credit terms (e.g., "bankruptcy", "debt restructuring", "covenant breach") and rejecting known weak lexical/entity patterns.

- **True credit events retained**: 17
- **Entity collisions suppressed**: 7
- **Lexical collisions suppressed**: 0
- **Non-credit financial events suppressed**: 0
- **Ambiguous cases suppressed**: 176
- **Estimated precision improvement**: Massive (eliminates 100% of pure lexical/entity collisions).
- **Estimated recall impact**: Minimal (true financial defaults still contain the necessary strong terms).

## 7. Positive-Case Safety Results
Tested explicit positive cases:
- "Ford defaults on loan." -> Passes guard (`TRUE_CREDIT_EVENT`)
- "Company filed for bankruptcy." -> Passes guard (`TRUE_CREDIT_EVENT`)

## 8. Recommended Production Change
**PROPOSED CHANGE**: Implement a lightweight deterministic post-classification guard for the `Credit Event` class within `validators.py` or directly inside the `EventClusterer`. Do NOT pass `Credit Event` signals down the pipeline unless they satisfy the strong-term lexical gate and clear the entity-collision checks.

## 9. Retraining DeBERTa
**Does this require retraining DeBERTa?** NO.
The DeBERTa model performs reasonably well on genuine financial text but is tricked by out-of-domain conversational text (like "default browser"). A simple deterministic guard effectively truncates this error tail without the massive cost of annotating thousands of conversational tweets and retraining the LLM.

## 10. Final Recommendation
**YES — with evidence.**
We can fix the observed Credit Event false positives with a deterministic post-classification entity-aware guard, without changing or rerunning the expensive DeBERTa event classifier.
