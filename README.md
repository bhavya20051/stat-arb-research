# stat-arb-research — residual short-term reversal, engineered for real execution

**Status (2026-09-05): scaffold, engine and tests complete; data ingestion waiting on the FMP API key. No backtest has been run yet.**

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

## 6. Headline locked-OOS results
Not yet available. This section will only ever contain the single holdout run.

## 7. Robustness findings
Pending.

## 8. Technology
Python 3.14 (numpy, pandas, scipy, statsmodels, scikit-learn), pytest + hypothesis, one C++ component compiled with `ziglang` (parity-tested against Python), YAML configs, per-run manifests (git hash, config hash, data-snapshot hash).

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
