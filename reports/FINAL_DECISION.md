# Final decision

Date: 2026-09-06. Holdout manifest: git `3f5d72b`, config hash `3e6f2ece72612684`, data snapshot `fa95f55af79937b0`, frozen 2026-09-06 04:57 UTC, run once.

## Classification: **C — research-quality negative result**

The methodology held (pre-registration, point-in-time universe with delisted names, 15:40 ET decision cutoff, auction-fill execution, exchange-member cost model, multiple-testing correction, single locked holdout), and the strategy did **not** survive the locked holdout.

| Family (frozen configuration) | DEV net Sharpe | VAL net Sharpe (95% CI) | **Holdout 2023-01-03 → 2026-08-31 net Sharpe (95% CI)** | Holdout gross Sharpe | Holdout net return / vol | Max DD |
|---|---|---|---|---|---|---|
| Rank residual reversal (LOC δ=1, k=1, hold 3, quintiles) | 0.89 | 0.93 (−0.08 .. 1.87) | **0.16 (−1.06 .. 1.46)**, PSR 0.62 | 0.26 | +0.6% / 4.3% | −8.4% |
| Event residual reversal (|z| ≥ 2, hold 3, LOC) | 0.72 | 0.50 (−0.54 .. 1.50) | −0.02 (−0.94 .. 1.08) | 0.06 | −0.1% / — | −8% |
| Earnings-8-K drift (+ volume/timing variants) | 0.10 | 0.03 | −0.07 (−1.10 .. 0.94) | 0.09 | −0.2% / — | −5% |

Holdout stress variants for rank reversal: costs ×1.5 → 0.12, ×2 → 0.07, +5 bp slippage → −1.17, +1-day signal lag → −0.15, prime-brokered-fund profile → 0.15, gross 5× → 0.15, MOC instead of LOC → −0.06.

## Why it failed

1. **The edge decayed, gross of costs.** On 2005–2022 the frozen rank strategy earned a gross Sharpe of 1.05 (net 0.86); on 2023–2026 the gross Sharpe was 0.26. Costs are not the story in the holdout (0.35 bp/day); the signal itself weakened. Yearly net Sharpe on the development and validation samples already showed the pattern: 1.6–3.4 in 2006–2008 and 2011, ≈2 in 2020–2021, and ≤ 0.5 or negative in most calm years since 2012. The 2023–2026 window contained no sustained stress regime, and in calm markets the no-news reversal premium is close to zero.
2. **Regime dependence is structural.** Net Sharpe by lagged-VIX tercile on 2005–2022: low 0.52, mid 0.97, high 1.11. The strategy is compensation for supplying liquidity in stressed markets; it is not a steady-state edge for a large-cap universe in the current market structure. A VIX-gated variant was tested and did not improve on the ungated one in-sample.
3. **Execution fragility.** The strategy only works with auction fills that pay no spread: 5 bp of slippage per side turns Sharpe 0.86 into −0.10 (development + validation) and 0.16 into −1.17 (holdout). Any implementation that pays a spread cannot run it.
4. The two other families never had an edge: event-style concentration lost diversification without adding edge; post-earnings drift is absent in large caps, consistent with Martineau (2022).

## What the evidence supports
- No-news residual reversal in liquid U.S. stocks existed with a gross Sharpe near 1 on 2005–2022, was a day-one effect, was stronger after quiet-volume moves and in high-VIX regimes, and news (earnings-8-K) moves continued rather than reversed. The validation sample confirmed the development result almost exactly (0.93 vs 0.89), so the failure is not overfitting of the parameters but a change in the phenomenon.
- Placebo (inverted signal) −0.17; parameter neighbours 0.5–0.84; universe subset and concentration checks stable; PBO 0.42 and DSR 0.62 for the 72-candidate family.

## What it would take to revisit
A pre-registered, regime-conditional design (trade only when lagged VIX is in its top tercile) is the only variant the evidence points to, and it must be tested on a new forward sample: the 2023–2026 holdout is now spent and becomes development data if research continues. A forward paper-trading ledger from 2026-09 is the correct next experiment.

Not upgraded: the result is C, not B, because the holdout point estimate is economically negligible (0.6%/yr at 4.3% vol), the confidence interval spans zero widely, and the validation sample contained the 2020 stress episode that drove its number.
