# Risk Engine Output Audit - 862k Run
**Total Rows Processed:** 862,231

## 1. Materiality Distribution
- **NO_EVENT**: 586,333 (68.0%)
- **NON_MATERIAL_FINANCIAL_CONTENT**: 267,497 (31.0%)
- **MATERIAL_EVENT**: 8,401 (1.0%)

## 2. Event Type Distribution
- **NO_EVENT**: 586,333 (68.0%)
- **Other / Unclear**: 120,943 (14.0%)
- **Market / Liquidity**: 54,031 (6.3%)
- **Corporate / Earnings**: 33,092 (3.8%)
- **Geopolitical**: 23,703 (2.7%)
- **Product / Technology**: 18,528 (2.1%)
- **Regulatory / Legal**: 11,060 (1.3%)
- **Merger & Acquisition**: 6,796 (0.8%)
- **Macroeconomic**: 3,376 (0.4%)
- **Commodity / Supply Chain**: 2,533 (0.3%)
- **Credit Event**: 1,836 (0.2%)

## 3. Sentiment Distribution
- **neutral**: 737,013 (85.5%)
- **negative**: 92,555 (10.7%)
- **positive**: 32,663 (3.8%)

## 4. Impact Tier Distribution
- **Minimal Impact**: 853,830 (99.03%)
- **Moderate Impact**: 5,699 (0.66%)
- **High Impact**: 1,495 (0.17%)
- **Low Impact**: 1,169 (0.14%)
- **Critical Impact**: 38 (0.00%)

## 5. Impact Score Statistics
- **Mean**: 1.10
- **Std**: 0.52
- **Min**: 1.00
- **Max**: 9.49
- **25%**: 1.00
- **50%**: 1.00
- **75%**: 1.16

## 6. Score Stats by Materiality
| Materiality | Count | Mean | Std | Min | Max |
|-------------|-------|------|-----|-----|-----|
| MATERIAL_EVENT | 8,401 | 6.22 | 0.95 | 3.82 | 9.49 |
| NON_MATERIAL_FINANCIAL_CONTENT | 267,497 | 1.17 | 0.02 | 1.15 | 1.26 |
| NO_EVENT | 586,333 | 1.00 | 0.00 | 1.00 | 1.00 |

## 7. Score Stats by Event Type
| Event Type | Count | Mean | Std | Min | Max |
|------------|-------|------|-----|-----|-----|
| Commodity / Supply Chain | 2,533 | 1.39 | 1.03 | 1.15 | 8.00 |
| Corporate / Earnings | 33,092 | 1.32 | 0.88 | 1.15 | 8.54 |
| Credit Event | 1,836 | 1.24 | 0.68 | 1.15 | 9.49 |
| Geopolitical | 23,703 | 1.36 | 1.04 | 1.15 | 8.86 |
| Macroeconomic | 3,376 | 1.53 | 1.40 | 1.15 | 8.63 |
| Market / Liquidity | 54,031 | 1.31 | 0.84 | 1.15 | 8.34 |
| Merger & Acquisition | 6,796 | 2.11 | 2.04 | 1.15 | 7.89 |
| NO_EVENT | 586,333 | 1.00 | 0.00 | 1.00 | 1.00 |
| Other / Unclear | 120,943 | 1.24 | 0.56 | 1.15 | 8.21 |
| Product / Technology | 18,528 | 1.24 | 0.51 | 1.15 | 6.93 |
| Regulatory / Legal | 11,060 | 1.89 | 1.80 | 1.15 | 8.10 |

## 8. High-Impact Tail (>= 8.0)
Rows with impact >= 8.0: 207

### Duplicate/Concentration check in Top 500 signals
Most repeated exact tweet texts in the top 500:
- (27x) RT @RichardGrenell: Siemens has told me they are pulling out of Iran to comply with US sanctions. #s...
- (14x) RT @kylegriffin1: Steel and aluminum tariffs imposed by the Trump admin have cost Ford Motor Co. abo...
- (13x) RT @Reuters: BREAKING NEWS: U.S. Treasury Department sanctions Venezuelan President Maduro...
- (13x) RT @MorganStanley: Morgan Stanley’s Chief U.S. Economist says U.S. GDP growth will likely hit 3.0% i...
- (10x) RT @ajplus: Google employees in 8 offices around the globe just staged a walkout over Trump's execut...
- (8x) RT @Reuters: MORE: Under sanctions, all of Maduro's assets subject to U.S. jurisdiction are frozen, ...
- (7x) RT @CBCAlerts: Ford CEO James Hackett says Trump administration's steel and aluminum tariffs 'took a...
- (5x) RT @Reuters: BREAKING: Russia, China block bid by western powers to impose U.N. sanctions on Syria o...
- (5x) RT @CNN: JUST IN: Comcast drops its $65 billion bid for 21st Century Fox, ceding a major bidding war...
- (4x) RT @real_IPOBUSA: People are deeply concerned by Intel community silent of the impending doom in Nig...

### Top 10 Stocks by High-Impact Count
- **Reuters**: 90
- **Ford**: 28
- **Siemens**: 27
- **Intel**: 20
- **Next**: 8
- **Apple**: 7
- **Amazon**: 6
- **Facebook**: 5
- **JPMorgan**: 2
- **Nike**: 2

## 9. Stratified Audit Samples
Exported 601 rows to `data/pipeline_output/audit_samples_862k.csv` for human review.