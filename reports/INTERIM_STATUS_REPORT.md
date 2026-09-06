# Interim status report — data collected and results to date

Date: 2026-09-05, 22:10 ET. **Status: development-sample (in-sample) evidence only, mostly on a 444-of-949-name preview panel while the intraday pull completes. No validation or holdout result exists yet. Nothing here is a final performance claim.**

## 1. Data collected

| Dataset | Coverage | Source / verification |
|---|---|---|
| Point-in-time S&P 500 membership | 1,525 change records (1957→2026); 948 symbols with membership overlapping 2005-01-03 onward | FMP `historical-sp500-constituent`; cross-check vs Wikipedia pending |
| Daily bars (raw, split-adjusted, total-return) | 848 symbols, 3.78M rows, 2005-01-03 → 2026-08-31, 5,449 trading days | FMP, pulled in 4-year windows (5,000-row cap discovered); endpoint semantics verified on AAPL 4:1 (2020-08-31) |
| Dividends, splits | per symbol | FMP |
| 15-minute intraday bars | ~800 of 949 symbols done (pull in progress), 2005 → 2026, ~30 trading days per request | FMP; on a mixed price basis (split-adjusted for some names, spin-off-unadjusted for others) → handled by computing partial-day returns inside the intraday series and by an ex-ante reliability mask |
| SEC 8-K filings | 255,058 filings, 902 of 956 symbols, acceptance timestamps to the second, item codes | EDGAR submissions API; 149 delisted-name CIKs resolved by name (126 high / 23 medium confidence), 17 unresolved |
| FMP news articles | queued after intraday | coverage begins ≈2012 (verified empty in 2006/2009) |
| VIX | 5,472 days | FMP `^VIX` |
| Fee schedules and market-maker cost economics | NYSE/Nasdaq price lists, SEC 31, FINRA TAF, NSCC, Virtu 10-K | `reports/market_maker_cost_research.md` (primary sources with quotes) |
| Literature | 13 citations checked: 10 confirmed, 2 partly (wording corrected), 1 unverifiable (Chan 2003) | `reports/literature_verification.csv` |

### Data-quality findings (06_DATA_AUDIT.md)
- No duplicate or impossible bars; 0.31% zero-volume symbol-days; 360 symbol-days with |return| > 50% (to be cross-checked against events).
- **Survivorship gap**: 112 membership symbols have no FMP price history; 16% of active members in 2005 falling to 5.8% in 2013, 1.2% in 2018 and 0% from 2020. Reported with every DEV result.
- **Intraday ticker splicing**: 23 of 227 preview tickers had intraday histories disagreeing with daily returns (reused tickers such as AET, CZR, BBBY, CB); an ex-ante 60-day agreement mask (≥ 95%) removes them and lifted the 15:45 signal from 2.8 to 4.7 bp/day.
- **Range-based spread estimators** (Corwin–Schultz, Abdi–Ranaldo) imply ~50 bp median spreads for S&P 500 names, ~10× quoted; rejected as a cost basis (registry COST-2). Primary executions are auction fills that pay no spread.
- Open items: 29% of adjustment-ratio jumps unmatched to a dividend/split date (likely ex- vs record-date convention); FMP daily `open` provenance; SEC 31 historical rates by year.

## 2. Hypothesis tests on the development sample (2005-01 → 2018-12-14; registry 04_HYPOTHESIS_REGISTRY.csv)

| ID | Result | Status |
|---|---|---|
| H1 core reversal | Fama–MacBeth slope of next-day return on the residual reversal score t = 5.5 (3,434 dates); decile spread 5.4 bp (1 d), 9.6 bp (3 d), 12.6 bp (10 d) | not falsified |
| H2 turnover | slope by abnormal-turnover tercile: low 3.4e-4 (t 5.5), mid 2.6e-4 (t 5.3), high 1.6e-4 (t 3.7) | partially supported (monotone, no sign flip at daily horizon) |
| H3 VIX | no-news decile spread 3.6 bp/day in low-VIX tercile vs 9.5 / 9.1 in mid / high; +18.7 bp per log-VIX unit (t 3.6) | supported |
| H4 residual vs raw | residual score t 5.5 vs raw 4.0 at 1 day; similar at 3–5 days | provisional |
| H6 horizon | reversal is front-loaded: 6.8 bp on day 1, 1.7 bp/day after; holding candidates {1,2,3} | not falsified; horizon narrowed |
| H7 news vs no-news | no-news: +6.8 bp/day (t 6.4); 8-K news days: −15.4 bp/day (t −3.8) | supported (Tier 1) |
| H8 post-news drift | earnings-8-K movers continue (t −2.3); non-earnings 8-K movers no drift | supported for earnings only |
| RES-1 residualization | 120-day two-factor betas too noisy (corr 0.48 with in-window residual); 250-day SPY+sector betas recover the full spread (5.5 bp, t 4.2) | applied |
| COST-1 impact | pre-registered sqrt/k=1 impact overstated by ~14× vs Almgren et al. (2005; verified β = 0.600, η = 0.142); corrected before any VAL/holdout run | applied |
| COST-3 / CAP-1 | cost profile set to market maker (exchange member) per deployment context; capital chosen from the DEV capacity curve | applied |
| EXEC-1 resting limit next session | gross SR −0.49: forfeits day-1 reversal, adverse selection | falsified |
| EXEC-2 limit-on-close | net SR 0.42–0.47 vs MOC 0.26 (retail, $1M) at lower turnover | supported; added to grid |

## 3. Strategy variants (preview panel, DEV, in-sample; annualized)

Best net results by cost profile, limit-on-close entries (δ = 1.0), k = 1, hold 3, quintiles:

| Capital | Retail net SR | Institutional net SR | Market-maker net SR | Impact bp/day |
|---|---|---|---|---|
| $0.1M | −0.22 | — | — | 0.02 |
| $1M | 0.47 | 0.84 | 0.89 | 0.08 |
| $5M | 0.45 | 0.78 | 0.83 | 0.21 |
| $20M | 0.32 | 0.65 | pending | 0.48 |
| $50M | — | 0.49 | pending | 0.83 |
| $100M | −0.04 | 0.29 | pending | 1.25 |

Gross Sharpe is 1.11 at every size (gross return 6.0%/yr at ~0.9× gross exposure, ~5.4% volatility). Cost per day: retail 1.4 bp, institutional 0.6 bp, market maker 0.5 bp at $1M; impact dominates above ≈$20M and caps capacity.

Other constructions (retail, $1M): MOC k1 h3 gross 1.29 / net 0.26; MOC k1 h2 1.24 / 0.21; hysteresis and VIX-gated MOC variants gross 1.1–1.2 but net ≤ 0.15 because turnover rises; full daily rebalance (h = 1) net −0.36. Full table: `results/dev/all_preview_runs.csv`.

## 4. What is being run now
- Ablation of the four pre-registered construction elements (beta hedge, sector neutrality, ex-ante pre-earnings exclusion, auction-volume participation) at $5M and $50M under the market-maker profile.
- Market-maker capacity curve $20M–$200M.
- Intraday pull completion → full-panel feature rebuild → registered 72-candidate DEV grid → fixed selection rule → one-shot validation (2019–2022) → robustness suite → locked holdout (2023-01-03 → 2026-08-31), single run.

## 5. Interim assessment
The edge exists and is stable gross of costs (Sharpe 1.1–1.3, day-one, no-news, stronger in stress). Net performance is a cost-and-capacity problem: retail costs consume most of it; exchange-member costs leave ≈0.8–0.9 net in-sample at ≤ $5M, fading with impact above ≈$20M. The effect has weakened over time (2005–2010 spreads 2–3× those of 2011–2018), so validation and the holdout are expected to come in below these in-sample figures. Current expectation: classification B (promising but unproven) or C; class A would require the full panel to add meaningfully to the gross edge and the holdout to hold up.
