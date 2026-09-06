# stat-arb-research — residual short-term reversal, engineered for real execution

**Status (2026-09-06): complete through the locked holdout. Classification: C — research-quality negative result.** The pre-registered residual-reversal strategy earned a net Sharpe of 0.93 on the 2019–2022 validation window and **0.16 on the locked 2023–2026 holdout** (gross 0.26); two further strategy variants (event-style reversal, earnings-8-K drift) were at or below zero. Full report: `reports/QUANT_RESEARCH_REPORT.html`; decision memo: `reports/FINAL_DECISION.md`.

## 1. Research question
Does company-specific ("residual") short-term price pressure in liquid U.S. stocks still reverse enough, after realistic retail-broker costs, to be traded profitably with orders an individual can place (market-on-close and resting limit orders), when moves caused by material company news are filtered out ex ante?

## 2. Hypothesis
Temporary liquidity demand pushes a stock away from its market- and sector-implied value; once the urgent trader is done the price drifts back over 1–5 days (Nagel 2012; Blitz et al. 2013). The effect should be concentrated in no-news, low-turnover moves and strongest in high-VIX regimes; news-driven moves should continue instead (Medhat & Schmeling 2022; Chan 2003). Pre-registered as H1–H8 in `04_HYPOTHESIS_REGISTRY.csv` before any data was pulled.

## 3. Data
Financial Modeling Prep (point-in-time S&P 500 membership incl. delisted names, daily OHLCV with recomputed adjustments, 5-minute bars from 2013), SEC EDGAR 8-K filings (acceptance timestamps to the second, item codes) and FMP news articles (2012+) for the news layer. Provenance and audit: `05_DATA_PROVENANCE.md`, `06_DATA_AUDIT.md`.

## 4. Strategy architecture
Rolling factor residualisation → z-scored trailing residual → ex-ante masks (news, jump, pre-earnings, liquidity) → decile ranking → dollar-, sector- and beta-neutral book with caps and vol targeting → market-on-close execution at 15:40 decision time (limit-order variant) → explicit cost model (commissions, fees, borrow, auction impact, range-based spreads).

## 5. Backtest methodology
Chronological DEV (≈2013–2018) → one-shot VAL (2019–2022) → **locked holdout 2023-01-03 → 2026-08-31** run once with a frozen config. Purge/embargo at boundaries, no random K-fold, hypothesis registry with trial types feeding the Deflated Sharpe Ratio, CSCV/PBO, block-bootstrap CIs, kill tests, independent red-team review.

## 6. Headline locked-OOS results (single run, frozen config, git 3f5d72b)
| Strategy | DEV net SR | VAL net SR (95% CI) | Holdout net SR (95% CI) | Holdout gross SR | Holdout net return / vol / max DD |
|---|---|---|---|---|---|
| Rank residual reversal (LOC δ=1, k=1, hold 3, quintiles) | 0.89 | 0.93 (−0.08..1.87) | **0.16 (−1.06..1.46)** | 0.26 | +0.6% / 4.3% / −8.4% |
| Event residual reversal (|z| ≥ 2, hold 3, LOC) | 0.72 | 0.50 (−0.54..1.50) | −0.02 | 0.06 | −0.1% / — / −8% |
| Earnings-8-K drift | 0.10 | 0.03 | −0.07 | 0.09 | −0.2% / — / −5% |

Costs: exchange-member profile (auction fee, clearing, SEC 31, FINRA TAF, 0.3% borrow, Almgren impact on closing-auction volume); capital $1M by the pre-specified capacity rule; 10% vol target, gross ≤ 3×, drawdown brake.

## 7. Robustness findings (development + validation, 2005–2022, rank reversal)
Base net Sharpe 0.86 → costs ×1.5: 0.77; ×2: 0.67; +5 bp slippage: −0.10 (auction fills are essential); +1-day lag: 0.72; MOC instead of LOC: 0.44; parameter neighbours 0.50–0.84; gross 2×/5×: 0.83/0.94; placebo (inverted signal): −0.17; top-250 universe: 0.84; VIX terciles low/mid/high: 0.52/0.97/1.11; drop best month: 0.77. Yearly net Sharpe: strong in 2006–2008, 2011, 2020–2021; ≤ 0.5 or negative in most calm years since 2012 — the decay the holdout confirmed. DSR 0.62, CSCV PBO 0.42 over 72 candidates.

## 8. Technology
Python 3.14 (numpy, pandas, scipy, statsmodels, scikit-learn), 42 pytest tests, a C++ simulation engine compiled with `ziglang` (ctypes DLL, 1e-9 parity, 6.7× faster; `cpp/benchmark.md`), YAML configs, per-run manifests (git hash, config hash, data-snapshot hash), hypothesis registry with trial-type accounting.

## 9. Reproduction
```bash
python -m venv C:/Users/bhavy/statarb_data/venv
C:/Users/bhavy/statarb_data/venv/Scripts/python -m pip install -e ".[dev,cpp]"
C:/Users/bhavy/statarb_data/venv/Scripts/python -m pytest -q
# save your FMP key to %USERPROFILE%\.fmp_api_key (never committed), then:
C:/Users/bhavy/statarb_data/venv/Scripts/python -m statarb.cli probe
C:/Users/bhavy/statarb_data/venv/Scripts/python -m statarb.cli ingest --intraday --news
```
Bulk data and the venv live outside the repo in `STATARB_DATA_DIR` (default `C:\Users\bhavy\statarb_data`).
