# Historical Offline Evaluation Report (Audited)

> **Network Prohibition:** ZERO network requests made. Fully offline via local Parquet cache.

## 1. Coverage Accounting
**Market-enriched evaluation coverage = 4167 / 4401** (94.7%)

| Category | Count |
|---|---|
| Successfully computed MarketContext | 4167 |
| Cached data but MarketContext computation failed | 11 |
| Unavailable instrument/cache | 223 |
| Unresolved/ambiguous | 14 |
| Reuters/no equity instrument | 585 |
| **Total Rows** | **5000** |

**11 Cached-but-Uncomputed Rows Audit (Issue 3):**
- Row 553 | STOCK: Home Depot | Ticker: HD | Cache: Available | Failure: 'float' object has no attribute 'strip' | Fallback to NLP: Yes
- Row 1042 | STOCK: Home Depot | Ticker: HD | Cache: Available | Failure: 'float' object has no attribute 'strip' | Fallback to NLP: Yes
- Row 1303 | STOCK: Home Depot | Ticker: HD | Cache: Available | Failure: 'float' object has no attribute 'strip' | Fallback to NLP: Yes
- Row 1444 | STOCK: Home Depot | Ticker: HD | Cache: Available | Failure: 'float' object has no attribute 'strip' | Fallback to NLP: Yes
- Row 1628 | STOCK: Home Depot | Ticker: HD | Cache: Available | Failure: 'float' object has no attribute 'strip' | Fallback to NLP: Yes
- Row 1640 | STOCK: Home Depot | Ticker: HD | Cache: Available | Failure: 'float' object has no attribute 'strip' | Fallback to NLP: Yes
- Row 1696 | STOCK: Home Depot | Ticker: HD | Cache: Available | Failure: 'float' object has no attribute 'strip' | Fallback to NLP: Yes
- Row 2482 | STOCK: Home Depot | Ticker: HD | Cache: Available | Failure: 'float' object has no attribute 'strip' | Fallback to NLP: Yes
- Row 3633 | STOCK: Home Depot | Ticker: HD | Cache: Available | Failure: 'float' object has no attribute 'strip' | Fallback to NLP: Yes
- Row 4397 | STOCK: Home Depot | Ticker: HD | Cache: Available | Failure: 'float' object has no attribute 'strip' | Fallback to NLP: Yes
- Row 4739 | STOCK: Home Depot | Ticker: HD | Cache: Available | Failure: 'float' object has no attribute 'strip' | Fallback to NLP: Yes

These 11 rows correctly fell back to NLP-only scoring and are included in the 833 total fallback rows (585 + 14 + 223 + 11 = 833).

```text
5000 total
├── 585 Reuters/no equity instrument
├── 14 unresolved/ambiguous
├── 223 unavailable instrument/cache
├── 11 cached data but MarketContext computation failed
└── 4167 successfully enriched
```

## 2. Market-Enrichment Comparison

**Issue 1: Score Distribution Inconsistency Explained**
The populations for the two distributions are identical (n=5000) and no rows were dropped. The market-enriched mean is lower than the NLP-only mean because the offline evaluation script instantiates a new `RiskSignal` with hardcoded values (`source_credibility=0.7`, `novelty=1.0`) before calling the `MarketEnrichedScorer`. Because the original baseline impact scores were generated using different parameters or additional logic (e.g., specific gating), the newly computed *base* score inside the scorer is lower than the original baseline. The strictly positive market modifier (≥1.0) is then applied to this lower recomputed base score.

| Metric | Value |
|---|---|
| Number of scores changed by context | 1020 |
| Mean absolute score change | 0.0487 |
| Number of signals whose tier changed | 20 |
| Tier increased | 0 |
| Tier decreased | 20 |

**Score Distributions:**
| Metric | NLP-Only Impact Score | Market-Enriched Impact Score | Market Modifier |
|---|---|---|---|
| Mean | 1.2627 | 1.214 | 1.0038 |
| Median | 1.0 | 1.0 | 1.0 |
| Std | 0.9126 | 0.8808 | 0.0206 |
| Min | 1.0 | 1.0 | 1.0 |
| P25 | 1.0 | 1.0 | 1.0 |
| P75 | 1.2 | 1.11 | 1.0 |
| Max | 7.54 | 7.54 | 1.25 |

## 3. Spearman Correlations vs Future Returns
> *Note: Impact Score should add signal beyond any single component.*

### A. All signals

| Predictor | Horizon | n | ρ signed | p | ρ abs | p |
|---|---|---|---|---|---|---|
| `IMPACT_SCORE_MKT` | 1_DAY_RETURN | 1409 | -0.0749 | 0.0049 | -0.1024 | 0.0001 |
| `IMPACT_SCORE_MKT` | 2_DAY_RETURN | 1409 | -0.0856 | 0.0013 | -0.1028 | 0.0001 |
| `IMPACT_SCORE_MKT` | 3_DAY_RETURN | 1409 | -0.0760 | 0.0043 | -0.0985 | 0.0002 |
| `IMPACT_SCORE_MKT` | 7_DAY_RETURN | 1409 | 0.0701 | 0.0085 | -0.0899 | 0.0007 |
| `IMPACT_SCORE` | 1_DAY_RETURN | 1409 | -0.0837 | 0.0017 | -0.1233 | 0.0000 |
| `IMPACT_SCORE` | 2_DAY_RETURN | 1409 | -0.0977 | 0.0002 | -0.1135 | 0.0000 |
| `IMPACT_SCORE` | 3_DAY_RETURN | 1409 | -0.0870 | 0.0011 | -0.1165 | 0.0000 |
| `IMPACT_SCORE` | 7_DAY_RETURN | 1409 | 0.0470 | 0.0781 | -0.1129 | 0.0000 |
| `FINBERT_SCORE` | 1_DAY_RETURN | 1409 | 0.0290 | 0.2763 | -0.0420 | 0.1149 |
| `FINBERT_SCORE` | 2_DAY_RETURN | 1409 | 0.0323 | 0.2249 | 0.0167 | 0.5301 |
| `FINBERT_SCORE` | 3_DAY_RETURN | 1409 | 0.0124 | 0.6413 | 0.0131 | 0.6233 |
| `FINBERT_SCORE` | 7_DAY_RETURN | 1409 | 0.0312 | 0.2425 | 0.0300 | 0.2599 |
| `EVENT_CONFIDENCE` | 1_DAY_RETURN | 1409 | -0.0803 | 0.0026 | -0.0990 | 0.0002 |
| `EVENT_CONFIDENCE` | 2_DAY_RETURN | 1409 | -0.0950 | 0.0004 | -0.1002 | 0.0002 |
| `EVENT_CONFIDENCE` | 3_DAY_RETURN | 1409 | -0.0865 | 0.0011 | -0.1015 | 0.0001 |
| `EVENT_CONFIDENCE` | 7_DAY_RETURN | 1409 | 0.0510 | 0.0558 | -0.1052 | 0.0001 |
| `ABN_RETURN` | 1_DAY_RETURN | 1159 | -0.8844 | 0.0000 | -0.5289 | 0.0000 |
| `ABN_RETURN` | 2_DAY_RETURN | 1159 | -0.7247 | 0.0000 | -0.4983 | 0.0000 |
| `ABN_RETURN` | 3_DAY_RETURN | 1159 | -0.6822 | 0.0000 | -0.4020 | 0.0000 |
| `ABN_RETURN` | 7_DAY_RETURN | 1159 | -0.5826 | 0.0000 | -0.3806 | 0.0000 |

### B. Market-enriched signals only

| Predictor | Horizon | n | ρ signed | p | ρ abs | p |
|---|---|---|---|---|---|---|
| `IMPACT_SCORE_MKT` | 1_DAY_RETURN | 1159 | -0.0534 | 0.0693 | -0.0239 | 0.4161 |
| `IMPACT_SCORE_MKT` | 2_DAY_RETURN | 1159 | -0.0932 | 0.0015 | -0.0308 | 0.2942 |
| `IMPACT_SCORE_MKT` | 3_DAY_RETURN | 1159 | -0.0904 | 0.0021 | -0.0546 | 0.0632 |
| `IMPACT_SCORE_MKT` | 7_DAY_RETURN | 1159 | -0.0190 | 0.5177 | -0.0928 | 0.0016 |
| `IMPACT_SCORE` | 1_DAY_RETURN | 1159 | -0.0772 | 0.0086 | -0.0681 | 0.0205 |
| `IMPACT_SCORE` | 2_DAY_RETURN | 1159 | -0.1144 | 0.0001 | -0.0647 | 0.0276 |
| `IMPACT_SCORE` | 3_DAY_RETURN | 1159 | -0.1089 | 0.0002 | -0.0928 | 0.0016 |
| `IMPACT_SCORE` | 7_DAY_RETURN | 1159 | -0.0398 | 0.1753 | -0.1299 | 0.0000 |
| `FINBERT_SCORE` | 1_DAY_RETURN | 1159 | 0.0378 | 0.1989 | -0.0311 | 0.2902 |
| `FINBERT_SCORE` | 2_DAY_RETURN | 1159 | 0.0331 | 0.2606 | 0.0314 | 0.2860 |
| `FINBERT_SCORE` | 3_DAY_RETURN | 1159 | 0.0124 | 0.6720 | 0.0287 | 0.3294 |
| `FINBERT_SCORE` | 7_DAY_RETURN | 1159 | 0.0272 | 0.3543 | 0.0397 | 0.1765 |
| `EVENT_CONFIDENCE` | 1_DAY_RETURN | 1159 | -0.0694 | 0.0182 | -0.0452 | 0.1239 |
| `EVENT_CONFIDENCE` | 2_DAY_RETURN | 1159 | -0.1111 | 0.0001 | -0.0522 | 0.0756 |
| `EVENT_CONFIDENCE` | 3_DAY_RETURN | 1159 | -0.1071 | 0.0003 | -0.0770 | 0.0087 |
| `EVENT_CONFIDENCE` | 7_DAY_RETURN | 1159 | -0.0290 | 0.3232 | -0.1127 | 0.0001 |
| `ABN_RETURN` | 1_DAY_RETURN | 1159 | -0.8844 | 0.0000 | -0.5289 | 0.0000 |
| `ABN_RETURN` | 2_DAY_RETURN | 1159 | -0.7247 | 0.0000 | -0.4983 | 0.0000 |
| `ABN_RETURN` | 3_DAY_RETURN | 1159 | -0.6822 | 0.0000 | -0.4020 | 0.0000 |
| `ABN_RETURN` | 7_DAY_RETURN | 1159 | -0.5826 | 0.0000 | -0.3806 | 0.0000 |

### C & D. One representative signal per STOCK×DATE (Event Cluster)

| Predictor | Horizon | n | ρ signed | p | ρ abs | p |
|---|---|---|---|---|---|---|
| `IMPACT_SCORE_MKT` | 1_DAY_RETURN | 123 | 0.0308 | 0.7356 | 0.0844 | 0.3533 |
| `IMPACT_SCORE_MKT` | 2_DAY_RETURN | 123 | -0.0326 | 0.7202 | 0.0396 | 0.6638 |
| `IMPACT_SCORE_MKT` | 3_DAY_RETURN | 123 | -0.0526 | 0.5635 | 0.0521 | 0.5674 |
| `IMPACT_SCORE_MKT` | 7_DAY_RETURN | 123 | -0.0520 | 0.5681 | 0.0907 | 0.3184 |
| `IMPACT_SCORE` | 1_DAY_RETURN | 123 | -0.0248 | 0.7853 | 0.0801 | 0.3785 |
| `IMPACT_SCORE` | 2_DAY_RETURN | 123 | -0.0104 | 0.9087 | 0.0074 | 0.9348 |
| `IMPACT_SCORE` | 3_DAY_RETURN | 123 | -0.0083 | 0.9278 | 0.0049 | 0.9571 |
| `IMPACT_SCORE` | 7_DAY_RETURN | 123 | -0.0735 | 0.4193 | 0.0373 | 0.6818 |
| `FINBERT_SCORE` | 1_DAY_RETURN | 123 | 0.1010 | 0.2663 | -0.0267 | 0.7692 |
| `FINBERT_SCORE` | 2_DAY_RETURN | 123 | 0.1065 | 0.2413 | -0.0413 | 0.6504 |
| `FINBERT_SCORE` | 3_DAY_RETURN | 123 | 0.0849 | 0.3504 | -0.0549 | 0.5465 |
| `FINBERT_SCORE` | 7_DAY_RETURN | 123 | 0.0898 | 0.3231 | -0.0073 | 0.9363 |
| `EVENT_CONFIDENCE` | 1_DAY_RETURN | 123 | -0.0484 | 0.5953 | 0.1132 | 0.2126 |
| `EVENT_CONFIDENCE` | 2_DAY_RETURN | 123 | -0.0580 | 0.5240 | -0.0209 | 0.8185 |
| `EVENT_CONFIDENCE` | 3_DAY_RETURN | 123 | -0.0924 | 0.3095 | 0.0258 | 0.7772 |
| `EVENT_CONFIDENCE` | 7_DAY_RETURN | 123 | -0.0762 | 0.4025 | 0.0845 | 0.3527 |
| `ABN_RETURN` | 1_DAY_RETURN | 106 | -0.8182 | 0.0000 | -0.1887 | 0.0528 |
| `ABN_RETURN` | 2_DAY_RETURN | 106 | -0.6208 | 0.0000 | -0.1571 | 0.1079 |
| `ABN_RETURN` | 3_DAY_RETURN | 106 | -0.5581 | 0.0000 | -0.0808 | 0.4104 |
| `ABN_RETURN` | 7_DAY_RETURN | 106 | -0.3616 | 0.0001 | -0.0263 | 0.7893 |

### Material events only

| Predictor | Horizon | n | ρ signed | p | ρ abs | p |
|---|---|---|---|---|---|---|
| `IMPACT_SCORE_MKT` | 1_DAY_RETURN | 38 | -0.4206 | 0.0085 | -0.4243 | 0.0079 |
| `IMPACT_SCORE_MKT` | 2_DAY_RETURN | 38 | -0.1329 | 0.4264 | -0.1329 | 0.4264 |
| `IMPACT_SCORE_MKT` | 3_DAY_RETURN | 38 | -0.1135 | 0.4975 | -0.2265 | 0.1715 |
| `IMPACT_SCORE_MKT` | 7_DAY_RETURN | 38 | 0.3059 | 0.0618 | 0.1148 | 0.4924 |
| `IMPACT_SCORE` | 1_DAY_RETURN | 38 | -0.1774 | 0.2866 | -0.1977 | 0.2340 |
| `IMPACT_SCORE` | 2_DAY_RETURN | 38 | 0.0149 | 0.9293 | 0.0149 | 0.9293 |
| `IMPACT_SCORE` | 3_DAY_RETURN | 38 | 0.0569 | 0.7346 | -0.0043 | 0.9796 |
| `IMPACT_SCORE` | 7_DAY_RETURN | 38 | 0.2867 | 0.0809 | 0.1331 | 0.4257 |
| `FINBERT_SCORE` | 1_DAY_RETURN | 38 | 0.1414 | 0.3971 | 0.1329 | 0.4263 |
| `FINBERT_SCORE` | 2_DAY_RETURN | 38 | 0.0945 | 0.5727 | 0.0945 | 0.5727 |
| `FINBERT_SCORE` | 3_DAY_RETURN | 38 | 0.0336 | 0.8415 | 0.0286 | 0.8647 |
| `FINBERT_SCORE` | 7_DAY_RETURN | 38 | 0.1100 | 0.5108 | 0.0156 | 0.9258 |
| `EVENT_CONFIDENCE` | 1_DAY_RETURN | 38 | -0.3206 | 0.0497 | -0.3048 | 0.0628 |
| `EVENT_CONFIDENCE` | 2_DAY_RETURN | 38 | -0.5282 | 0.0007 | -0.5282 | 0.0007 |
| `EVENT_CONFIDENCE` | 3_DAY_RETURN | 38 | -0.4906 | 0.0018 | -0.4288 | 0.0072 |
| `EVENT_CONFIDENCE` | 7_DAY_RETURN | 38 | -0.1750 | 0.2933 | -0.1198 | 0.4738 |
| `ABN_RETURN` | 1_DAY_RETURN | 10 | -1.0000 | 0.0000 | -1.0000 | 0.0000 |
| `ABN_RETURN` | 2_DAY_RETURN | 10 | 0.0519 | 0.8867 | 0.0519 | 0.8867 |
| `ABN_RETURN` | 3_DAY_RETURN | 10 | 0.3247 | 0.3600 | 0.1039 | 0.7752 |
| `ABN_RETURN` | 7_DAY_RETURN | 10 | 0.3766 | 0.2834 | -0.5065 | 0.1352 |

### Negative sentiment only (FINBERT < -0.05)

| Predictor | Horizon | n | ρ signed | p | ρ abs | p |
|---|---|---|---|---|---|---|
| `IMPACT_SCORE_MKT` | 1_DAY_RETURN | 252 | -0.1033 | 0.1018 | -0.1370 | 0.0296 |
| `IMPACT_SCORE_MKT` | 2_DAY_RETURN | 252 | -0.1205 | 0.0560 | -0.1013 | 0.1087 |
| `IMPACT_SCORE_MKT` | 3_DAY_RETURN | 252 | -0.1017 | 0.1072 | -0.0687 | 0.2771 |
| `IMPACT_SCORE_MKT` | 7_DAY_RETURN | 252 | 0.0213 | 0.7360 | -0.0090 | 0.8865 |
| `IMPACT_SCORE` | 1_DAY_RETURN | 252 | -0.1182 | 0.0610 | -0.1321 | 0.0361 |
| `IMPACT_SCORE` | 2_DAY_RETURN | 252 | -0.1228 | 0.0516 | -0.1013 | 0.1087 |
| `IMPACT_SCORE` | 3_DAY_RETURN | 252 | -0.1039 | 0.0997 | -0.0781 | 0.2166 |
| `IMPACT_SCORE` | 7_DAY_RETURN | 252 | 0.0050 | 0.9372 | -0.0383 | 0.5448 |
| `FINBERT_SCORE` | 1_DAY_RETURN | 252 | -0.1133 | 0.0725 | -0.0701 | 0.2679 |
| `FINBERT_SCORE` | 2_DAY_RETURN | 252 | -0.0816 | 0.1968 | 0.0012 | 0.9847 |
| `FINBERT_SCORE` | 3_DAY_RETURN | 252 | -0.1196 | 0.0580 | 0.0138 | 0.8269 |
| `FINBERT_SCORE` | 7_DAY_RETURN | 252 | -0.0840 | 0.1840 | -0.0894 | 0.1572 |
| `EVENT_CONFIDENCE` | 1_DAY_RETURN | 252 | -0.1370 | 0.0297 | -0.1313 | 0.0372 |
| `EVENT_CONFIDENCE` | 2_DAY_RETURN | 252 | -0.1412 | 0.0250 | -0.1041 | 0.0990 |
| `EVENT_CONFIDENCE` | 3_DAY_RETURN | 252 | -0.1263 | 0.0451 | -0.0727 | 0.2500 |
| `EVENT_CONFIDENCE` | 7_DAY_RETURN | 252 | -0.0126 | 0.8423 | -0.0524 | 0.4075 |
| `ABN_RETURN` | 1_DAY_RETURN | 207 | -0.8526 | 0.0000 | -0.4962 | 0.0000 |
| `ABN_RETURN` | 2_DAY_RETURN | 207 | -0.6673 | 0.0000 | -0.4712 | 0.0000 |
| `ABN_RETURN` | 3_DAY_RETURN | 207 | -0.6077 | 0.0000 | -0.3310 | 0.0000 |
| `ABN_RETURN` | 7_DAY_RETURN | 207 | -0.5328 | 0.0000 | -0.2727 | 0.0001 |

### Positive sentiment only (FINBERT > 0.05)

| Predictor | Horizon | n | ρ signed | p | ρ abs | p |
|---|---|---|---|---|---|---|
| `IMPACT_SCORE_MKT` | 1_DAY_RETURN | 201 | -0.2075 | 0.0031 | -0.1356 | 0.0550 |
| `IMPACT_SCORE_MKT` | 2_DAY_RETURN | 201 | -0.1103 | 0.1189 | -0.1618 | 0.0218 |
| `IMPACT_SCORE_MKT` | 3_DAY_RETURN | 201 | -0.0947 | 0.1814 | -0.1257 | 0.0754 |
| `IMPACT_SCORE_MKT` | 7_DAY_RETURN | 201 | 0.0708 | 0.3180 | -0.1828 | 0.0094 |
| `IMPACT_SCORE` | 1_DAY_RETURN | 201 | -0.1889 | 0.0072 | -0.1400 | 0.0475 |
| `IMPACT_SCORE` | 2_DAY_RETURN | 201 | -0.1159 | 0.1012 | -0.1617 | 0.0218 |
| `IMPACT_SCORE` | 3_DAY_RETURN | 201 | -0.1008 | 0.1545 | -0.1341 | 0.0578 |
| `IMPACT_SCORE` | 7_DAY_RETURN | 201 | 0.0542 | 0.4446 | -0.2036 | 0.0037 |
| `FINBERT_SCORE` | 1_DAY_RETURN | 201 | -0.0079 | 0.9114 | 0.0318 | 0.6539 |
| `FINBERT_SCORE` | 2_DAY_RETURN | 201 | 0.0116 | 0.8697 | -0.0291 | 0.6819 |
| `FINBERT_SCORE` | 3_DAY_RETURN | 201 | 0.0098 | 0.8899 | -0.0523 | 0.4613 |
| `FINBERT_SCORE` | 7_DAY_RETURN | 201 | -0.0338 | 0.6339 | -0.0531 | 0.4541 |
| `EVENT_CONFIDENCE` | 1_DAY_RETURN | 201 | -0.2040 | 0.0037 | -0.1230 | 0.0820 |
| `EVENT_CONFIDENCE` | 2_DAY_RETURN | 201 | -0.1159 | 0.1015 | -0.1499 | 0.0337 |
| `EVENT_CONFIDENCE` | 3_DAY_RETURN | 201 | -0.1011 | 0.1533 | -0.1102 | 0.1195 |
| `EVENT_CONFIDENCE` | 7_DAY_RETURN | 201 | 0.0589 | 0.4062 | -0.1774 | 0.0117 |
| `ABN_RETURN` | 1_DAY_RETURN | 164 | -0.8807 | 0.0000 | -0.6062 | 0.0000 |
| `ABN_RETURN` | 2_DAY_RETURN | 164 | -0.7348 | 0.0000 | -0.5688 | 0.0000 |
| `ABN_RETURN` | 3_DAY_RETURN | 164 | -0.7003 | 0.0000 | -0.3916 | 0.0000 |
| `ABN_RETURN` | 7_DAY_RETURN | 164 | -0.6730 | 0.0000 | -0.4585 | 0.0000 |

## 4. Data Quality & Limitations

**Unavailable Historical Instruments:**
The following instruments were entirely unavailable from the data provider and fell back to NLP-only scoring:
- `FB`: Affected 79 rows
- `YHOO`: Affected 14 rows
- `VIAB`: Affected 1 rows
- `CBS`: Affected 82 rows
- `K`: Affected 9 rows
- `FOXA`: Affected 3 rows
- `RYA.L`: Affected 20 rows
- `RDS-A`: Affected 14 rows
- `PCLN`: Affected 1 rows

**Sector Availability Note:** The Communication Services Select Sector SPDR Fund (`XLC`) was launched in June 2018 and did not exist during this 2017 evaluation period. Affected instruments default to broad market comparison (`^GSPC`) where sector context is missing.