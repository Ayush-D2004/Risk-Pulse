# Historical Instrument Registry (Jan-Mar 2017)

## Validation Summary

| Status | Count |
|---|---|
| `USABLE_HISTORICAL_INSTRUMENT` | 90 |
| `EXPLICITLY_UNRESOLVED_AMBIGUOUS` | 1 |
| `DOCUMENTED_PARENT_PROXY` | 1 |
| `DOCUMENTED_NO_EQUITY_INSTRUMENT` | 1 |

**Validation Result**: ✅ PASSED - Every unique STOCK in the evaluation sample maps to exactly one permitted, strictly defined status.

## Exceptional Mappings

| Entity | Historical Ticker | Exchange | Type | Status | Proxy? | Usable 2017? | Rationale |
|---|---|---|---|---|---|---|---|
| 21CF | `FOXA` | NASDAQ | common_stock | `USABLE_HISTORICAL_INSTRUMENT` | False | True | Twenty-First Century Fox traded as FOXA (Class A) in 2017 before the Disney acquisition. |
| Audi | None | Xetra | common_stock | `EXPLICITLY_UNRESOLVED_AMBIGUOUS` | False | False | Ambiguous whether tweets target the listed subsidiary (NSU.DE) or the parent Volkswagen Group (VOW3.DE). Left explicitly unresolved. |
| CBS | `CBS` | NYSE | common_stock | `USABLE_HISTORICAL_INSTRUMENT` | False | True | CBS Corporation traded as CBS in 2017 prior to merging with Viacom (now PARA). |
| Facebook | `FB` | NASDAQ | common_stock | `USABLE_HISTORICAL_INSTRUMENT` | False | True | Facebook traded as FB in 2017 before renaming to META. |
| Gillette | `PG` | NYSE | common_stock | `DOCUMENTED_PARENT_PROXY` | True | True | Gillette is a brand owned by Procter & Gamble (PG). PG is used as an explicit parent-company proxy. |
| Reuters | None | None | None | `DOCUMENTED_NO_EQUITY_INSTRUMENT` | False | False | Reuters is a news agency. The parent company is Thomson Reuters (TRI), but we retain no-equity status as instructed. |
| Shell | `RDS-A` | NYSE | adr | `USABLE_HISTORICAL_INSTRUMENT` | False | True | Royal Dutch Shell traded as RDS-A (ADR) in the US during 2017 before unifying its shares to SHEL in 2022. |
| Viacom | `VIAB` | NASDAQ | common_stock | `USABLE_HISTORICAL_INSTRUMENT` | False | True | Viacom traded as VIAB (Class B) in 2017 before merging with CBS (now PARA). |
| Yahoo | `YHOO` | NASDAQ | common_stock | `USABLE_HISTORICAL_INSTRUMENT` | False | True | Yahoo! Inc. traded as YHOO in early 2017 before the Verizon acquisition and Altaba restructuring. |
| bookingcom | `PCLN` | NASDAQ | common_stock | `USABLE_HISTORICAL_INSTRUMENT` | False | True | The Priceline Group traded as PCLN in early 2017 before renaming to Booking Holdings (BKNG) in 2018. |

## Standard Mappings (USABLE_HISTORICAL_INSTRUMENT)

<details><summary>Click to view all standard mappings</summary>

| Entity | Historical Ticker | Exchange | Type | Usable 2017? |
|---|---|---|---|---|
| ASOS | `ASC.L` | LSE | common_stock | True |
| AT&T | `T` | US | common_stock | True |
| Adobe | `ADBE` | US | common_stock | True |
| Allianz | `ALV.DE` | Xetra | common_stock | True |
| Amazon | `AMZN` | US | common_stock | True |
| American Express | `AXP` | US | common_stock | True |
| Apple | `AAPL` | US | common_stock | True |
| AstraZeneca | `AZN` | US | common_stock | True |
| BMW | `BMW.DE` | Xetra | common_stock | True |
| BP | `BP` | US | common_stock | True |
| Bank of America | `BAC` | US | common_stock | True |
| Bayer | `BAYN.DE` | Xetra | common_stock | True |
| BlackRock | `BLK` | US | common_stock | True |
| Boeing | `BA` | US | common_stock | True |
| Burberry | `BRBY.L` | LSE | common_stock | True |
| Carrefour | `CA.PA` | Euronext Paris | common_stock | True |
| Chevron | `CVX` | US | common_stock | True |
| Cisco | `CSCO` | US | common_stock | True |
| Citigroup | `C` | US | common_stock | True |
| CocaCola | `KO` | US | common_stock | True |
| Comcast | `CMCSA` | US | common_stock | True |
| Costco | `COST` | US | common_stock | True |
| Deutsche Bank | `DB` | US | common_stock | True |
| Disney | `DIS` | US | common_stock | True |
| Expedia | `EXPE` | US | common_stock | True |
| Exxon | `XOM` | US | common_stock | True |
| FedEx | `FDX` | US | common_stock | True |
| Ford | `F` | US | common_stock | True |
| GSK | `GSK` | US | common_stock | True |
| General Electric | `GE` | US | common_stock | True |
| Goldman Sachs | `GS` | US | common_stock | True |
| Google | `GOOGL` | US | common_stock | True |
| Groupon | `GRPN` | US | common_stock | True |
| H&M | `HM-B.ST` | US | common_stock | True |
| HP | `HPQ` | US | common_stock | True |
| HSBC | `HSBC` | US | common_stock | True |
| Heineken | `HEIA.AS` | Euronext Amsterdam | common_stock | True |
| Home Depot | `HD` | US | common_stock | True |
| Honda | `HMC` | US | common_stock | True |
| Hyundai | `005380.KS` | KRX | common_stock | True |
| IBM | `IBM` | US | common_stock | True |
| Intel | `INTC` | US | common_stock | True |
| JPMorgan | `JPM` | US | common_stock | True |
| John Deere | `DE` | US | common_stock | True |
| Kellogg's | `K` | US | common_stock | True |
| Kroger | `KR` | US | common_stock | True |
| L'Oreal | `OR.PA` | Euronext Paris | common_stock | True |
| Mastercard | `MA` | US | common_stock | True |
| McDonald's | `MCD` | US | common_stock | True |
| Microsoft | `MSFT` | US | common_stock | True |
| Morgan Stanley | `MS` | US | common_stock | True |
| Nestle | `NESN.SW` | SIX Swiss | common_stock | True |
| Netflix | `NFLX` | US | common_stock | True |
| Next | `NXT.L` | LSE | common_stock | True |
| Nike | `NKE` | US | common_stock | True |
| Nissan | `7201.T` | Tokyo | common_stock | True |
| Oracle | `ORCL` | US | common_stock | True |
| PayPal | `PYPL` | US | common_stock | True |
| Pepsi | `PEP` | US | common_stock | True |
| Pfizer | `PFE` | US | common_stock | True |
| Ryanair | `RYA.L` | LSE | common_stock | True |
| SAP | `SAP` | US | common_stock | True |
| Samsung | `005930.KS` | KRX | common_stock | True |
| Santander | `SAN` | US | common_stock | True |
| Siemens | `SIE.DE` | Xetra | common_stock | True |
| Sony | `SONY` | US | common_stock | True |
| Starbucks | `SBUX` | US | common_stock | True |
| TMobile | `TMUS` | US | common_stock | True |
| Tesco | `TSCO.L` | LSE | common_stock | True |
| Thales | `HO.PA` | Euronext Paris | common_stock | True |
| Toyota | `TM` | US | common_stock | True |
| TripAdvisor | `TRIP` | US | common_stock | True |
| UPS | `UPS` | US | common_stock | True |
| Verizon | `VZ` | US | common_stock | True |
| Visa | `V` | US | common_stock | True |
| Vodafone | `VOD` | US | common_stock | True |
| Volkswagen | `VWAGY` | US | common_stock | True |
| Walmart | `WMT` | US | common_stock | True |
| Wells Fargo | `WFC` | US | common_stock | True |
| adidas | `ADS.DE` | Xetra | common_stock | True |
| eBay | `EBAY` | US | common_stock | True |
| easyJet | `EZJ.L` | LSE | common_stock | True |
| salesforce.com | `CRM` | US | common_stock | True |

</details>
