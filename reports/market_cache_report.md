# Historical Market Cache Report

## Acquisition Summary
| Metric | Value |
|---|---|
| Source/Provider | yfinance (v1.7.0) |
| Instruments Requested | 103 |
| Successfully Cached | 93 |
| Failed Downloads | 0 |
| Unavailable / No Data | 10 |
| Date Coverage Requested | 2016-12-15 to 2017-04-05 |
| Total Cached Rows | 7103 |

## Provider Limitations & Unavailable Instruments
The following historical and delisted tickers were completely unavailable or failed to return data from `yfinance` for the required 2017 date range. As instructed, they have **not** been silently substituted.

- `K`: No data returned / Unavailable
- `RDS-A`: No data returned / Unavailable
- `XLC`: No data returned / Unavailable
- `YHOO`: No data returned / Unavailable
- `FB`: No data returned / Unavailable
- `VIAB`: No data returned / Unavailable
- `CBS`: No data returned / Unavailable
- `PCLN`: No data returned / Unavailable
- `FOXA`: No data returned / Unavailable
- `RYA.L`: No data returned / Unavailable

## Smoke Test Results
The `MarketContextFetcher` was tested offline against the generated parquet cache. See execution logs for details.