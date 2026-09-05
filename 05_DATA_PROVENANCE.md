# 05 — Data provenance

Ingestion date: 2026-09-05 (first pull). Everything below is reproducible with `python -m statarb.cli ingest --intraday --news` given the same FMP key tier and a fresh raw cache; vendor restatements are the reason the processed snapshot is hashed (`data/snapshot_manifest.json`).

## Vendor and access
- **Financial Modeling Prep (FMP) stable API**, user's own key (Premium-or-higher: tier probe on 2026-09-05 returned 30-year daily history, delisted TWTR bars, 5-min SPY bars on 2013-01-03, 1,525 S&P 500 constituent-change rows). Client: `src/statarb/data/fmp.py` (700 calls/min ceiling, retries, raw JSON cached under `STATARB_DATA_DIR/raw/fmp/`). Key stored in `%USERPROFILE%\.fmp_api_key`, never logged or committed.
- **SEC EDGAR** submissions API (`data.sec.gov/submissions/CIK##########.json` plus paginated history files), declared User-Agent, ≤ 8 req/s. Client: `src/statarb/news/edgar.py`. Verified live: Apple, 236 8-K filings since 1996 with `acceptanceDateTime` to the second and item codes.

## Endpoints and fields
| Dataset | Endpoint | Fields kept | Window |
|---|---|---|---|
| Point-in-time S&P 500 membership | `historical-sp500-constituent` (+ `sp500-constituent` for current members) | date, symbol (added), removedTicker, reason | full list (oldest change 1957-03-03); memberships overlapping 2005-01-03 onward are used → 948 symbols |
| Security master | `profile`, `symbol-change`, `delisted-companies` | companyName, cik, isin, exchange, sector, industry, ipoDate, isActivelyTrading, old/new symbol + date, delistedDate | all |
| Daily bars | `historical-price-eod/full` (fields date, open, high, low, close, adjClose, volume, vwap, change) and `historical-price-eod/non-split-adjusted` | all | 2005-01-03 → 2026-08-31 |
| Corporate actions | `dividends`, `splits` per symbol | date, dividend/adjDividend, numerator/denominator | all |
| Intraday | `historical-chart/15min` (one request returns ≤ ~30 trading days; pulled in 28-day windows) | date, open, high, low, close, volume | 2005-01-01 → 2026-08-31; the 15:30 bar (closing 15:45) is the decision-time price; 5-min bars exist from 2008 and will be added for the limit-order robustness check when the 50 GB/30-day bandwidth cap allows |
| News articles | `news/stock` per symbol, paged | symbol, publishedDate (US Eastern, verified against Apple's 2016-01-26 16:30 ET earnings release), publisher, site, title, url | 2010-01-01 → 2026-08-31 (coverage begins ≈2012; per-symbol start recorded in the audit) |
| Factors | SPY and SPDR sector ETFs XLB XLE XLF XLI XLK XLP XLU XLV XLY XLRE XLC (daily) | as daily bars | 2005+ (XLRE from 2015-10, XLC from 2018-06) |
| 8-K events | EDGAR submissions per CIK | accessionNumber, form, filingDate, acceptanceDateTime, items | all years |

## Known limitations (disclosed)
- No historical quote (bid/ask) data: continuous-session spreads are estimated with Corwin–Schultz / Abdi–Ranaldo; auction fills assume the official closing print with a participation-cost term.
- FMP daily `open` may be the consolidated first trade rather than the primary-exchange auction print (UNVERIFIED) — only affects the secondary next-open model.
- FMP's `delisted-companies` list is global; delisting *reason* is inferred from the constituent-change `reason` text and the security master, then mapped to the pre-registered delisting rules.
- Sector labels come from today's profile; sector history is not point-in-time (documented bias: pre-2016 real-estate and pre-2018 communication-services names are mapped to their pre-split sector ETFs by inception date).
- Alternative free sources evaluated and rejected: Yahoo (no delisted names, intraday only last 60 days), Stooq (bot challenge), Finviz (no historical intraday), Massive free tier (2 years), Databento (US equities from 2023).
