# stat-arb-research — residual short-term reversal, engineered for real execution

**Status (2026-09-06): complete through the locked holdout, the independent red-team audit and the post-audit rerun. Classification: C — research-quality negative result.** The frozen residual-reversal strategy earned a net Sharpe of **0.16 on the locked 2023–2026 holdout** (gross 0.26). An independent audit then showed that the in-sample figures that had justified the holdout (development 0.89, validation 0.93) were produced by code with two critical defects; after repairing them and rerunning everything, no configuration that survives the pre-registered protocol shows an economically meaningful net edge under either institutional cost profile. Full story: `reports/PM_REPORT.html` (client-facing), `reports/QUANT_RESEARCH_REPORT.html` (complete), `reports/RED_TEAM_AUDIT.md`, `reports/FINAL_DECISION.md`.

## 1. Research question
Does company-specific ("residual") short-term price pressure in liquid U.S. stocks still reverse enough, after realistic institutional costs, to be traded profitably with closing-auction orders (market-on-close / limit-on-close), when moves caused by material company news are filtered out ex ante?

## 2. Hypothesis
Temporary liquidity demand pushes a stock away from its market- and sector-implied value; once the urgent trader is done the price drifts back over 1–5 days (Nagel 2012; Blitz et al. 2013). The effect should be concentrated in no-news, low-turnover moves and strongest in high-VIX regimes; news-driven moves should continue instead (Medhat & Schmeling 2022; Chan 2003). H1–H8 were registered in `04_HYPOTHESIS_REGISTRY.csv` before any data was pulled; the 140-candidate grid was registered in code immediately before it ran and extended once (STRAT-4/5) after early drift results, which the registry records.

## 3. Data
Financial Modeling Prep (point-in-time S&P 500 membership incl. delisted names, daily OHLCV with verified adjustment semantics, 15-minute bars from 2005 with coverage of the point-in-time universe rising from 65% in 2005 to 81% in 2014 and 98% in 2023), SEC EDGAR 8-K filings (acceptance timestamps to the second, item codes) and FMP news articles (2012+) for the news layer. Provenance and audit: `05_DATA_PROVENANCE.md`, `06_DATA_AUDIT.md` (including the survivorship gap: 16% of members without price history in 2005, 5.8% in 2013, 1.2% in 2018, 0% from 2020).

## 4. Strategy architecture
Rolling factor residualisation (250-day market + sector betas) → z-scored trailing residual including the partial day to 15:45 ET → ex-ante masks at 15:45 (8-K news flag, lagged daily eligibility, partial-day jump rule, intraday-reliability mask) → quantile ranking → dollar-neutral book with 2% name caps, sector neutralisation and 10% vol targeting → limit-on-close entries decided at 15:45 (fill at the official close only if it extends the move by δσ; exits MOC) → SPY beta hedge and net-exposure correction sized to the *filled* book and executed MOC (post-audit) → explicit cost model (exchange or prime-broker fee, NSCC clearing, SEC 31 and FINRA TAF, borrow, Almgren impact on closing-auction volume; no spread on auction fills) → pre-registered delisting rules (M&A / ticker change 0, bankruptcy −100%, unknown −30%; wired into research runs post-audit).

## 5. Backtest methodology
Chronological development → one-shot validation (2019-01-02 → 2022-12-15) → **locked holdout 2023-01-03 → 2026-08-31**, run once as a pre-declared batch of 30 backtests with a frozen config. Purge at boundaries, no random K-fold, hypothesis registry with trial types feeding the Deflated Sharpe Ratio, CSCV/PBO, block-bootstrap CIs, kill tests, an independent red-team review (`reports/RED_TEAM_AUDIT.md`) and a full post-audit rerun on the pre-registered development window (2013-10-23 → 2018-12-14) and on the 2005 window the pre-audit study had used.

## 6. Headline results
Locked holdout, frozen pre-audit pipeline (immutable; git 3f5d72b):

| Strategy (frozen config) | Pre-audit DEV net SR (2005–18) | Pre-audit VAL net SR (95% CI) | Holdout net SR (95% CI) | Holdout gross SR | Holdout net return / vol / max DD |
|---|---|---|---|---|---|
| Rank residual reversal (LOC δ=1, k=1, hold 3, quintiles) | 0.89 | 0.93 (−0.08..1.87) | **0.16 (−1.06..1.46)** | 0.26 | +0.6% / 4.3% / −8.4% |
| Event residual reversal (\|z\| ≥ 2, hold 3, LOC) | 0.72 | 0.50 (−0.54..1.50) | −0.02 | 0.06 | −0.1% / — / −8% |
| Earnings-8-K drift | 0.10 | 0.03 | −0.07 | 0.09 | −0.2% / — / −5% |

Post-audit rerun (repaired pipeline, exchange-member profile; the prime-brokered-fund profile is within 0.03 Sharpe of every cell). "2023–26" is a diagnostic run on the spent holdout window, not a holdout:

| Strategy | Selected on | DEV net SR | VAL net SR (95% CI) | 2023–26 net SR (95% CI) | 2023–26 net return / vol / max DD |
|---|---|---|---|---|---|
| Rank reversal | 2013-10-23 → 2018 (pre-registered) | 0.22 | 0.49 (−0.60..1.38) | −0.24 (−1.38..1.06) | −0.5% / 2.0% / −6.6% |
| Rank reversal | 2005 → 2018 (frozen config) | 1.27 | 1.59 (0.68..2.42) | 0.20 (−0.92..1.37) | +0.5% / 2.7% / −6.4% |
| Event reversal | 2013-10-23 → 2018 | 1.00 (2% gross book) | −0.42 (−1.18..0.72) | 0.45 (−0.69..1.39) | +0.5% / 1.0% / −1.5% |
| Event reversal | 2005 → 2018 (frozen config) | 1.02 | 0.95 (0.09..1.66) | 1.13 (0.22..1.96) | +3.9% / 3.4% / −2.4% |
| Earnings drift | either | 0.22–0.26 | −0.26 (−1.20..0.67) | 0.67 (−0.49..1.78) | +0.9% / 1.4% / −1.5% |

The pre-audit in-sample Sharpes are withdrawn: about half of their gross P&L was unhedged market exposure created by the fill rule (realized net-exposure std 0.20 of capital, now 0.04). The event-reversal cell at 1.13 was selected outside the pre-registered window and examined once on a spent window; it is a forward-test candidate, not evidence. Costs: capital $1M by the pre-specified capacity rule; 10% vol target, gross ≤ 3×, drawdown brake; LOC fill rate 19%, so effective gross exposure is 0.1–0.5 of capital and realized volatility 1–3%.

## 7. Robustness (post-audit, pre-registered window + validation, rank reversal)
Base net Sharpe 0.35 → costs ×1.5: 0.23; ×2: 0.10; +5 bp slippage: −2.56 (auction fills are essential); +1-day lag: 0.05; MOC instead of LOC: 0.05; neighbours 0.32–0.82; gross 2×/5×: 0.34/0.35; placebo (inverted signal): −0.25; top-250 universe: 0.81; pre-earnings exclusion on: 0.11. Yearly net Sharpe is positive mainly in 2008, 2011 and 2020–2021 in every configuration examined. Multiple testing: DSR 0.19 (pre-registered window) / 0.80 (2005 window) over the 72 rank candidates; the reviewer's pooled-N recomputation gives 0.51 at N=140 and 0.38 at N=300 for the 2005-window pick.

## 8. Technology
Python 3.14 (numpy, pandas, scipy, statsmodels, scikit-learn), 48 pytest tests (no-lookahead, ex-ante masks, hand-computed P&L, delisting, post-audit repairs), a C++ simulation engine compiled with `ziglang` (ctypes DLL, 1e-9 parity, 6.7× faster; `cpp/benchmark.md`), YAML configs, per-run manifests (git hash, config hash, data-snapshot hash), hypothesis registry with trial-type accounting.

## 9. Reproduction
```bash
python -m venv C:/Users/bhavy/statarb_data/venv
C:/Users/bhavy/statarb_data/venv/Scripts/python -m pip install -e ".[dev,cpp]"
C:/Users/bhavy/statarb_data/venv/Scripts/python -m pytest -q
# save your FMP key to %USERPROFILE%\.fmp_api_key (never committed), then:
C:/Users/bhavy/statarb_data/venv/Scripts/python -m statarb.cli probe
C:/Users/bhavy/statarb_data/venv/Scripts/python -m statarb.cli ingest --intraday --news
C:/Users/bhavy/statarb_data/venv/Scripts/python -m statarb.research.run_post_audit        # repaired pipeline, both windows
C:/Users/bhavy/statarb_data/venv/Scripts/python -m statarb.research.run_post_audit_full   # complete metrics set
C:/Users/bhavy/statarb_data/venv/Scripts/python -m statarb.reporting.html_report && C:/Users/bhavy/statarb_data/venv/Scripts/python -m statarb.reporting.pm_report
```
Bulk data and the venv live outside the repo in `STATARB_DATA_DIR` (default `C:\Users\bhavy\statarb_data`). The frozen holdout was produced by the pre-audit code (git 3f5d72b) on the pre-audit feature panels (kept as `processed/features_moc_preaudit`); current code reproduces the post-audit files.
