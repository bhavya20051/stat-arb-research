# Interview brief — concise answers grounded in the frozen results

**Why should this alpha exist?** Temporary liquidity demand (redemptions, index rebalancing, dealer hedging) pushes a stock away from its factor-implied value; whoever absorbs the trade is paid a premium that is realised when the pressure ends. Nagel (2012) shows short-term reversal returns behave like the returns to liquidity provision and scale with VIX; we found the same: no-news decile spread 3.6 bp/day in low-VIX regimes vs ≈9 bp/day in mid/high VIX, and the strategy's net Sharpe 0.52 / 0.97 / 1.11 by VIX tercile.

**Why hasn't it been arbitraged away?** It largely has, at this horizon and in this universe. The premium migrated to shorter horizons harvested by market makers; our own data show yearly net Sharpes of 1.6–3.4 in 2006–2011, mostly ≤ 0.5 after 2012 outside the 2020–2021 stress period, and 0.16 on the 2023–2026 holdout. What remains is a stress-regime premium, not a steady edge.

**How did you avoid lookahead bias?** A single decision time (15:40 ET) enforced everywhere: signal from the 15:30 bar (complete 15:45), betas and volatilities lagged one day, 8-K flags by acceptance timestamp with a cutoff rule, article flags by ET publication time, expected-earnings windows built from last year's filings, drawdown brake on realized returns through t−1. Tests: a perfect-foresight signal earns nothing under the engine's lag, past outputs are invariant to future prices, an after-hours filing flags the next day.

**How did you avoid survivorship bias?** Point-in-time S&P 500 membership from the change list (1,525 events), delisted names' prices pulled explicitly (112 of 948 members had no vendor history; the gap is 16% in 2005, 0% from 2020 and reported with every result), delisting rules (M&A at last price, failure −100%, unknown −30%), fills only where trades printed, halted names carried then closed at the delisting return.

**How were transaction costs modelled?** Exchange-member profile from primary fee schedules: closing-auction fee $0.0008/share, NSCC clearing $2.60 per $1M, SEC 31 and FINRA TAF on sales, 0.3% borrow, Almgren power-law impact (β = 0.6, η = 0.142) on closing-auction volume; no spread on auction fills. Stress: ×1.5, ×2, +5 bp slippage, prime-brokered profile. The pre-registered sqrt/k=1 impact was a 14× error and was corrected before validation; the correction is logged.

**Why this holding period?** From the signal-decay curve, not from a Sharpe search: 6.8 bp on day one, 1.7 bp/day after; the candidates {1,2,3} were registered and 3 days with overlapping tranches won on development net Sharpe.

**Why these features?** Residual return (market + sector betas, 250-day window after showing 120-day betas were too noisy), residual volatility, abnormal turnover, VIX, news flags. Each maps to a mechanism in the literature and to a registered hypothesis.

**Why this model?** Linear and rank-based; the model ladder (ridge, boosting) was never reached because the simple signal's out-of-sample behaviour was the question, not its functional form.

**What happened on the untouched holdout?** Rank reversal: net Sharpe 0.16 (95% CI −1.06..1.46), gross 0.26, +0.6%/yr, max drawdown −8.4%. Event reversal −0.02; earnings drift −0.07. Classification C.

**How many hypotheses did you test?** 8 pre-registered hypotheses, 140 candidate configurations across five strategy variants, plus ~15 registered diagnostics; all in the registry, none deleted.

**How did you account for multiple testing?** Deflated Sharpe Ratio per family (72 / 48 / 20 candidates): 0.62 for the rank family; CSCV probability of backtest overfitting 0.42; one-shot validation; single holdout.

**What is the strategy's capacity?** Net Sharpe 0.89 at $1M, 0.78 at $5M, 0.52 at $20M, ≈0 near $50M under exchange-member costs; the binding cost is impact against closing-auction volume.

**What regime hurts it?** Calm, low-VIX markets (net Sharpe 0.52 in the low tercile; negative in 2015–2019) and any implementation that pays a spread (+5 bp slippage → negative).

**What would make you stop trading it?** Trailing 12-month net Sharpe below zero, a drawdown beyond 10% (the brake halves exposure), or evidence that the closing-auction fill assumption no longer holds.

**What would you improve with institutional data?** Real NBBO and auction imbalance feeds to replace the volume proxy, a point-in-time sector history, a vendor earnings calendar with announcement times, and full delisted-name coverage before 2012.

**What would you change for HFT?** Move the horizon inside the day: the reversal premium now lives in minutes, not days; that requires order-book data, queue-position modelling and colocated execution, none of which this project has.

**What part would you move to C++?** The simulation engine (done: 6.7× faster, 1e-9 parity); next the CSCV combinatorics and the rolling residualisation.

**What did you learn from failed experiments?** Resting limit orders lose the day-one bounce and suffer adverse selection; hysteresis does not reduce turnover for a one-day signal; range-based spread estimators are unusable for large caps; the pre-earnings exclusion costs more edge than it saves; event-style concentration and earnings drift add nothing; and a validation window that contains one stress episode can confirm an edge that a calm holdout then refutes.
