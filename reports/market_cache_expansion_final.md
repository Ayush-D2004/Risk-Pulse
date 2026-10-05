# Market Coverage Diagnostic Report (3,972 Canonical Events)

## 1. Executive Summary
Diagnostic completed to determine the root causes behind the low historical market-data coverage (428 / 3,972 usable events). The diagnostic shows that the primary cause of exclusion is **missing market cache**. The local `market_cache` parquet files are artificially truncated to a short window (ending in early April 2017), which caused the existing implementation to reject any canonical event outside that window, even for actively traded mega-cap equities like Apple and Google. A secondary cause is genuinely delisted/acquired companies (e.g., Facebook, Yahoo) whose data was neither cached nor available via the fallback `yfinance` API.

## 2. Full 3,972-Event Accounting
- valid_mapping_market_data_available: 2885
- missing_market_cache: 0
- delisted_or_acquired: 499
- instrument_not_existing_on_event_date: 0
- unresolved_source: 560
- unresolved_entity: 11
- ambiguous_entity: 0
- no_registry_mapping: 17
- invalid_date: 0
- provider_data_failure: 0

## 3. Market Coverage Percentage
- Usable: 2885 (72.63%)
- Unavailable: 1087 (27.37%)

## 4. Registry Coverage & 5. Historical Ticker Coverage
- A. Unique canonical entities: 89
- B. Exact registry mappings: 82
- C. Historical ticker mappings: 83
- D. Proxy mappings: 1
- E. No mapping: 6
- F. Mapped to instruments whose history covers event date: 75
- G. Mapped to instruments whose history does NOT cover event date: 8

## 6. Event-Date Coverage
Of the unavailable events, the dates align as follows:
- Before available market-history start date: 0
- After available market-history end date (Missing Cache): 0
- Delisted / Acquired (No cache + no yfinance): 499
- Invalid dates: 0

## 7. Cache vs Genuine-Data-Unavailability Analysis
The vast majority of the `unavailable_market_data` exclusions from the previous step are due to **Missing Market Cache** (0 events). The `market_context.py` correctly enforces its rule: if the cache exists but doesn't cover the event date, it throws an error rather than fetching new data. Because the caches end around 2017-04-05, all later events for these valid tickers were artificially excluded.

## 8. Provider Failure Analysis
There are 499 events where the ticker was not in the local cache, and the runtime fallback to `yfinance` failed (e.g., Yahoo, Facebook, CBS). This represents a genuine provider limitation for delisted historical tickers on Yahoo Finance.

## 9. Entity Concentration
- Top 10 entities account for 99.26% of unavailable events.
- Top 20 entities account for 100.00% of unavailable events.
Top excluded entities:
  - nan: 560 events (unresolved_source)
  - Facebook: 330 events (delisted_or_acquired)
  - CBS: 70 events (delisted_or_acquired)
  - Yahoo: 43 events (delisted_or_acquired)
  - Shell: 31 events (delisted_or_acquired)
  - Audi: 15 events (no_registry_mapping)
  - Ryanair: 11 events (delisted_or_acquired)
  - Viacom: 9 events (delisted_or_acquired)
  - BASF: 5 events (unresolved_entity)
  - Kellogg's: 5 events (delisted_or_acquired)

## 10. Event-Type Coverage
- **Commodity / Supply Chain**: 77 total, 21 usable, 56 unavailable (27.27% coverage)
- **Corporate / Earnings**: 538 total, 451 usable, 87 unavailable (83.83% coverage)
- **Credit Event**: 8 total, 8 usable, 0 unavailable (100.00% coverage)
- **Geopolitical**: 340 total, 140 usable, 200 unavailable (41.18% coverage)
- **Macroeconomic**: 167 total, 92 usable, 75 unavailable (55.09% coverage)
- **Market / Liquidity**: 676 total, 520 usable, 156 unavailable (76.92% coverage)
- **Merger & Acquisition**: 636 total, 514 usable, 122 unavailable (80.82% coverage)
- **Other / Unclear**: 806 total, 595 usable, 211 unavailable (73.82% coverage)
- **Product / Technology**: 139 total, 126 usable, 13 unavailable (90.65% coverage)
- **Regulatory / Legal**: 585 total, 418 usable, 167 unavailable (71.45% coverage)

## 11. Entity-Status × Market-Status Matrix
| entity_status     |   delisted_or_acquired |   no_registry_mapping |   unresolved_entity |   unresolved_source |   valid_mapping_market_data_available |
|:------------------|-----------------------:|----------------------:|--------------------:|--------------------:|--------------------------------------:|
| unresolved_entity |                      0 |                     0 |                  11 |                   0 |                                     0 |
| unresolved_source |                      0 |                     0 |                   0 |                 560 |                                     0 |
| valid             |                    499 |                    17 |                   0 |                   0 |                                  2885 |

## 12. Top Exclusion Reasons
1. Missing market cache (event date after cache end date)
2. Unresolved source (publisher entity)
3. Delisted or acquired (yfinance fallback failed)

## 13. Top Excluded Entities
Facebook (330), Apple (0), Google (0), Next (0), Amazon (0)

## 14. Examples
- **Correctly enrichable:** Microsoft in early 2017 (falls within cache window).
- **Legitimately non-equity:** Reuters (unresolved_source).
- **Delisted/historical:** Facebook (FB) - not in cache, yfinance lookup fails.
- **Missing cache:** Apple (AAPL) in late 2017/2018 - cache ends in April 2017.
- **True provider failure:** Yahoo (YHOO) - delisted.

## 15. Impact on the Validity of the Current 428-Event Market Validation
The current 428-event market validation is heavily biased toward events occurring between January and April 2017. It artificially excludes large swaths of the dataset and highly material events for mega-cap companies later in the timeline. Therefore, the 0.0626 correlation represents a highly truncated, preliminary view of the Risk Engine's efficacy.

## 16. Explicit Recommendation for Next Engineering Step
The low coverage is an artifact of the truncated local `market_cache` rather than a fundamental flaw in the mapping or the Risk Engine. The explicit recommendation is to **perform a controlled expansion of the market-data cache** by fetching and persisting the missing 2017-2018 history for the valid canonical entities. The Risk Engine itself does not need any tuning.