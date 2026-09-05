# 00 — Project Charter

Date: 2026-09-05. Status: approved plan (see `C:\Users\bhavy\.claude\plans\you-are-acting-as-snug-raven.md`). This charter is written before any market data is pulled and before any backtest is run.

## Objective

**Primary (user directive, 2026-09-05):** determine whether a market-neutral, short-horizon *residual reversal* strategy in liquid U.S. equities, re-engineered for execution an individual can actually perform (closing-auction and resting limit orders, days-long holding, volatility-regime scaling, a news filter that removes information-driven moves), earns **statistically and economically credible profit after realistic costs** on data that was never used to design it.

**Secondary:** produce a recruiting-grade research artifact for quantitative researcher / algorithm developer / quant trading roles (Hudson River Trading, Jane Street, Citadel / Citadel Securities, Susquehanna, Akuna Capital, Optiver, D. E. Shaw and peers) that demonstrates hypothesis formation, point-in-time data handling, leakage-free backtesting, cost and execution modelling, statistical inference under multiple testing, walk-forward validation, reproducible research, and production-style engineering in Python with one C++ component.

The objective is **not** "search until a high Sharpe appears." A rigorous negative result is acceptable; a fraudulent or overfit positive is not. Research choices are never altered merely to improve the final Sharpe ratio.

## Constraints

| Constraint | Value |
|---|---|
| Environment | Windows 11, Python 3.14.4; git 2.54; no local C++ compiler; WSL2/Docker unavailable (Hyper-V off). C++ via `pip install ziglang` (`python -m ziglang c++`), built as a standalone executable or C-ABI DLL loaded with ctypes. |
| Repo placement | Repo in the OneDrive working directory; venv, raw/processed data and heavy results at `C:\Users\bhavy\statarb_data\` (env `STATARB_DATA_DIR`). |
| Market data | Financial Modeling Prep (FMP) stable API with the user's key, read from `C:\Users\bhavy\.fmp_api_key` or env `FMP_API_KEY`; the key is never printed or committed. Premium-or-higher tier required (30-year daily history, 5-min intraday bars, delisted names). |
| News / events | SEC EDGAR 8-K filings (all years, acceptance timestamps, item codes), FMP stock-news articles (≈2012+, Eastern-time timestamps), cached headline/cause classifier; live Claude web search only in the forward test. |
| Capital scale | Primary $1,000,000 (retail-broker cost model); sensitivities at $100,000 and $10M / $100M. |
| Decision time | 15:40 ET (primary closing-auction model); 16:00 ET (daily-bar secondary). No information after the decision time is used at t. |
| Holdout | 2023-01-03 → 2026-08-31, locked; run once after freeze; never revised. |
| Trials | Every experiment is a registry row before it runs; failed rows are never deleted; candidate-trial count feeds the Deflated Sharpe Ratio. |

## Research principles

1. Hypothesis before code: H1–H8 and fallback B1 are pre-registered in `04_HYPOTHESIS_REGISTRY.csv` with falsification conditions on the development sample only.
2. Point-in-time everything: universe membership, prices, corporate actions, delistings, news, and earnings dates are all as-of the decision time; ex-ante masks are tested for invariance to later data.
3. Execution no earlier than the next realistically tradable observation; fills only where trades printed; halts and delistings resolved by pre-registered rules (M&A at last price; bankruptcy/receivership −100%; unknown −30%).
4. Costs are part of the strategy: commissions, fees, borrow, auction participation, impact, and range-based spread estimates; gross and net both reported, net is the headline; the break-even cost is a headline robustness statistic.
5. Chronological development → validation → locked holdout; purge and embargo at every boundary; no random K-fold; block bootstrap for uncertainty.
6. Simple models first; complexity must earn repeatable out-of-sample improvement.
7. Multiple-testing control: PSR, DSR, CSCV/PBO implemented only after verifying the formulas against the original papers, with simulation tests.
8. Try to destroy the strategy (kill tests) before believing it; an independent adversarial review precedes the final decision.
9. Reproducibility: configs not constants, seeded randomness, per-run manifests (git hash, config hash, data-snapshot hash, timestamp), a frozen data snapshot with SHA-256 manifest.
10. Honesty in reporting: uncertainty markers are mandatory information; unverified items are labelled `UNKNOWN — NOT VERIFIED`.

## Expected artifacts

`00_PROJECT_CHARTER.md`, `01_FIRM_RESEARCH.md`, `02_STRATEGY_SELECTION.md`, `03_LITERATURE_REVIEW.md`, `04_HYPOTHESIS_REGISTRY.csv`, `05_DATA_PROVENANCE.md`, `06_DATA_AUDIT.md`; `configs/*.yaml`; `data/security_master.csv`, `data/universe_pit.csv`, `data/partitions.csv`, snapshot manifest; `src/statarb/` (data, news, features, signals, portfolio, execution, backtest, statistics, reporting, cli); `tests/` (financially dangerous paths first, one hand-computed synthetic P&L test); `cpp/` component with parity test and `benchmark.md`; `results/{dev,validation,robustness,holdout,forward}`; `reports/QUANT_RESEARCH_REPORT.md`, `RED_TEAM_AUDIT.md`, `RESUME_BULLETS.md`, `INTERVIEW_BRIEF.md`, `FINAL_DECISION.md`, figures; `README.md`.

## Definitions of success and failure

Research gates, not optimisation targets, evaluated **once** on the locked holdout with the frozen configuration:

- **Strong:** net annualised Sharpe ≥ 1.50 with positive net return, Sharpe confidence interval materially above zero, PSR indicating strong evidence Sharpe > 0, reasonable DSR after the trial count, positive performance across multiple sub-periods, no severe P&L concentration, sensible turnover, market beta ≈ 0, stable neighbouring parameters, acceptable performance at 1.5× costs and no catastrophic failure at 2× costs.
- **Credible:** net Sharpe ≥ 1.20 with excellent robustness.
- **Failure:** anything below, or a result that only works in one year, one symbol, one exact parameter, before realistic costs, or because of one extreme event.
- Final classification is one of: A robust positive; B promising but unproven; C research-quality negative; D invalid backtest. It is never upgraded to make the project look better.
- If the first family fails: diagnose, write a post-mortem, pre-register a genuinely different hypothesis (B1), test it; at most three families before a full research audit.

## Decisions log

| Date | Decision |
|---|---|
| 2026-09-05 | Data source: FMP API key (user-provided). C++ toolchain: `ziglang`. |
| 2026-09-05 | Primary strategy committed to Family A (residual short-term reversal); no pre-selection bake-off. |
| 2026-09-05 | News layer is a core component: 8-K events (all years) + FMP articles (2012+) + cached classifier; cause-of-move labels from point-in-time archives; pre-earnings exclusion; live web search in the forward test only. |
| 2026-09-05 | Objective re-stated as real-life profitability at individual scale; Family A re-engineered: closing-auction execution primary (2013→2026 intraday sample), limit-order liquidity-provision variant, VIX gating, two sleeves; capital $1M primary. |
