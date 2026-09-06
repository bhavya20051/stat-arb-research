# Interview brief — concise answers grounded in the frozen and post-audit results (revised 2026-09-06)

**Why should this alpha exist?** Temporary liquidity demand (redemptions, index rebalancing, dealer hedging) pushes a stock away from its factor-implied value; whoever absorbs the trade is paid a premium realised when the pressure ends. Nagel (2012) shows short-term reversal returns behave like the returns to liquidity provision and scale with VIX; we found the same: the no-news decile spread is ≈3.6 bp/day in low-VIX regimes vs ≈9 bp/day in mid/high VIX, and net Sharpe by VIX tercile was 0.52 / 0.97 / 1.11 on the pre-audit 2005–2022 sample.

**Why hasn't it been arbitraged away?** At this horizon in this universe it largely has. Every configuration we examined earns its Sharpe in 2005–2011 and 2020–2021; on the pre-registered 2013–2018 development window the best rank configuration has a net Sharpe of 0.22, and the locked 2023–2026 holdout returned 0.16. What remains is a stress-regime premium harvested at shorter horizons by faster participants.

**What did the audit find and what did you do about it?** An independent fresh-context reviewer found two critical defects: the SPY hedge and net-exposure correction were gated by the limit-on-close fill rule, so the realized book carried ±20% of capital in unhedged market exposure and about half of the in-sample gross P&L was that exposure times the next day's market return; and the development grid ran from 2005 although the pre-registered rule set the start at 2013-10-23. Plus: end-of-day information in the 15:40 eligibility mask, cancelled LOC entries degrading into MOC fills, delisting rules never wired in, mis-scaled dividends. I verified each finding with my own scripts, fixed the code (six new tests), rewrote the documents, reran everything on both windows and withdrew the in-sample numbers. Net-exposure standard deviation is now 0.04 of capital. The classification stayed C; the story changed from "the edge decayed" to "the in-sample edge was partly an artefact and the real edge was never large".

**How did you avoid lookahead bias?** A single decision time (15:45 ET, the close of the 15:30–15:45 bar) enforced everywhere: betas, volatilities, VIX, expected earnings and the drawdown state lagged one day; 8-K flags by acceptance timestamp with a 15:40 cutoff; article flags by ET publication time; after the audit, the daily eligibility panel is used lagged one day plus an ex-ante partial-day jump rule. Tests: a perfect-foresight signal earns nothing under the engine's lag, past outputs are invariant to future prices, an after-hours filing flags the next day, the 15:45 eligibility is invariant to the close.

**How did you avoid survivorship bias?** Point-in-time S&P 500 membership from the change list (1,525 events), delisted names' prices pulled explicitly (112 of 948 members had no vendor history; the gap is 16% in 2005, 5.8% in 2013, 1.2% in 2018, 0% from 2020 and is reported with every result), pre-registered delisting rules (M&A and ticker changes 0, bankruptcy −100%, unknown −30%) now applied in every research run, fills only where trades printed. The audit's point that the 2008 failures are among the missing names is one reason the 2005–2013 years are not used for selection any more.

**How were transaction costs modelled?** Two institutional profiles from primary fee schedules: exchange member (closing-auction fee $0.0008/share, NSCC clearing $2.60 per $1M, SEC 31 and FINRA TAF on sales, 0.3% borrow) and prime-brokered fund ($0.0012/share all-in, same regulatory and clearing fees, no rebates); Almgren power-law impact (β = 0.6, η = 0.142) on closing-auction volume; no spread on auction fills. Stress: ×1.5, ×2, +5 bp slippage. The pre-registered sqrt/k=1 impact was a 14× error corrected before validation and logged; the two profiles differ by ≈0.07 bp/day and ≈0.03 in Sharpe.

**Why this holding period?** From the signal-decay curve, not from a Sharpe search: 6.8 bp on day one, 1.7 bp/day after; {1, 2, 3} were registered. The pre-registered window picked hold 1; the 2005 window picked hold 3.

**Why these features?** Residual return (market + sector betas, 250-day window after showing 120-day betas were too noisy), residual volatility, abnormal turnover, VIX, news flags. Each maps to a mechanism in the literature and to a registered hypothesis.

**Why this model?** Linear and rank-based; the model ladder (ridge, boosting) was never reached because the simple signal's out-of-sample behaviour was the question, not its functional form.

**What happened on the untouched holdout?** Rank reversal: net Sharpe 0.16 (95% CI −1.06 .. 1.46), gross 0.26, +0.6%/yr, max drawdown −8.4%. Event reversal −0.02; earnings drift −0.07. The audit showed the defects were neutral-to-negative in that window, so the direction stands.

**Is there anything left worth trading?** One cell: the event-reversal configuration (|z| ≥ 2, hold 3, LOC) selected on the 2005 window earned a net Sharpe of 1.13 on 2023–2026 (+3.9%/yr at 3.4% vol) after the repairs, against −0.02 for the same configuration on the frozen holdout. That is one of six cells, selected outside the pre-registered window, examined once on a spent sample after four simultaneous code changes. It is a forward-test candidate, not evidence.

**How many hypotheses did you test?** 8 pre-registered hypotheses, 140 candidate configurations across three families, plus ~15 registered diagnostics and ~30 preview runs; all in the registry, none deleted.

**How did you account for multiple testing?** Deflated Sharpe Ratio per family (72 / 48 / 20 candidates): 0.19 for the pre-registered-window rank pick, 0.80 for the 2005-window pick, and 0.51 / 0.38 when the reviewer pooled 140 / 300 effective trials; CSCV probability of backtest overfitting 0.42 pre-audit; one-shot validation; single holdout.

**What is the strategy's capacity?** Under closing-auction impact, net Sharpe falls monotonically with capital in every configuration and profile (post-audit rank reversal: 0.22 at $1M, 0.07 at $5M, negative from $20M); the binding cost is impact against closing-auction volume, and the participation caps are charged but not enforced, so the curve is an extrapolation.

**What regime hurts it?** Calm, low-VIX markets, and any implementation that pays a spread (+5 bp slippage turns every window negative). The limit-on-close filter also leaves the book under-invested (19% fill rate), so realized volatility runs at a third of target.

**What would make you stop trading it?** Trailing 12-month net Sharpe below zero, a drawdown beyond 10% (the brake halves exposure), or evidence that the closing-auction fill assumption no longer holds.

**What would you improve with institutional data?** Real NBBO and auction imbalance feeds to replace the volume proxy, a point-in-time sector history, a vendor earnings calendar with announcement times, full delisted-name coverage before 2012, and vol targeting on the filled rather than the targeted book.

**What would you change for HFT?** Move the horizon inside the day: the reversal premium now lives in minutes, not days; that requires order-book data, queue-position modelling and colocated execution, none of which this project has.

**What part would you move to C++?** The simulation engine (done: 6.7× faster, 1e-9 parity); next the CSCV combinatorics and the rolling residualisation.

**What did you learn from failed experiments?** Resting limit orders lose the day-one bounce and suffer adverse selection; hysteresis does not reduce turnover for a one-day signal; range-based spread estimators are unusable for large caps; the pre-earnings exclusion costs more edge than it saves; a hedge that shares the entry's fill condition is not a hedge; a null in a config file silently became 2005; and a validation window containing one stress episode can confirm an edge that a calm holdout then refutes.
