# Final decision (revised 2026-09-06 after the red-team audit)

Holdout manifest: git `3f5d72b`, config hash `3e6f2ece72612684`, data snapshot `fa95f55af79937b0`, frozen 2026-09-06 04:57 UTC, one pre-declared batch of 30 backtests, never re-run. Red-team audit: `reports/RED_TEAM_AUDIT.md` (22 findings). Post-audit re-analysis: `results/post_audit/` (`post_audit_results.json`, `full_metrics.json`).

## Classification: **C — research-quality negative result**

The classification is unchanged, but the reasoning is not. The pre-audit decision memo attributed the failure to "decay of the gross edge in a calm regime" and claimed that validation "confirmed the development result almost exactly". The audit showed that the pre-audit development and validation numbers (net Sharpe 0.89 / 0.93) did not measure a stock-selection edge: the SPY hedge and the net-exposure correction were gated by the limit-on-close fill rule, so the book carried ±20% of capital in unhedged market exposure whose sign flipped with the closing tape, and about half of the 2005–2022 gross P&L was that exposure times the next day's market return; the development grid ran from 2005 although the pre-registered rule set the start at the first date with ≥ 80% intraday coverage (2013-10-23); the 15:40 eligibility mask used the full-day residual; and cancelled LOC entries fell back to unconditional MOC fills. The reviewer's own classification was D for the positive claims as originally stated, and C after repairs. Those repairs were made (six new tests, 48 passing), the documents were rewritten, and the pipeline was rerun in full.

## What the locked holdout said (frozen pre-audit pipeline, immutable)

| Family (frozen configuration) | Pre-audit DEV net SR (2005–18) | Pre-audit VAL net SR (95% CI) | **Holdout 2023-01-03 → 2026-08-31 net SR (95% CI)** | Holdout gross SR | Net return / vol | Max DD |
|---|---|---|---|---|---|---|
| Rank residual reversal (LOC δ=1, k=1, hold 3, quintiles) | 0.89 | 0.93 (−0.08 .. 1.87) | **0.16 (−1.06 .. 1.46)** | 0.26 | +0.6% / 4.3% | −8.4% |
| Event residual reversal (\|z\| ≥ 2, hold 3, LOC) | 0.72 | 0.50 (−0.54 .. 1.50) | −0.02 | 0.06 | −0.1% | −8% |
| Earnings-8-K drift | 0.10 | 0.03 | −0.07 | 0.09 | −0.2% | −5% |

The audit established that the defects were neutral-to-negative in 2023–2026, so the holdout's direction stands. Its magnitude was never economically meaningful (0.6%/yr).

## What the repaired pipeline says (post-audit re-analysis; exchange-member profile; fund profile within 0.03 of every figure)

Selection was rerun with the unchanged rule on two development windows. VAL is the one-shot 2019-01-02 → 2022-12-15 window. "2023–26" is a **diagnostic** run of the repaired code on 2023-01-03 → 2026-08-31: the holdout was spent before the audit, so these figures are not out-of-sample in the pre-registered sense and were looked at once, for all six family × window cells at the same time.

| Family | Selected on | Configuration | DEV net SR | VAL net SR (95% CI) | VAL net ret/yr | 2023–26 net SR (95% CI) | 2023–26 net ret/yr / vol / max DD |
|---|---|---|---|---|---|---|---|
| Rank reversal | 2013-10-23 → 2018 (pre-registered) | k=1, hold 1, quintiles, VIX-linear, LOC δ=1 | 0.22 | 0.49 (−0.60 .. 1.38) | +0.6% | −0.24 (−1.38 .. 1.06) | −0.5% / 2.0% / −6.6% |
| Rank reversal | 2005-01-03 → 2018 | k=1, hold 3, quintiles, LOC δ=1 (= frozen config) | 1.27 | 1.59 (0.68 .. 2.42) | +2.3% | 0.20 (−0.92 .. 1.37) | +0.5% / 2.7% / −6.4% |
| Event reversal | 2013-10-23 → 2018 | \|z\| ≥ 3, hold 2, VIX-linear, MOC (gross exposure 2%) | 1.00 | −0.42 (−1.18 .. 0.72) | −1.0% | 0.45 (−0.69 .. 1.39) | +0.5% / 1.0% / −1.5% |
| Event reversal | 2005-01-03 → 2018 | \|z\| ≥ 2, hold 3, LOC δ=1 (= frozen config) | 1.02 | 0.95 (0.09 .. 1.66) | +2.2% | 1.13 (0.22 .. 1.96) | +3.9% / 3.4% / −2.4% |
| Earnings drift | 2013-10-23 → 2018 (pre-registered) | after-hours 2.02 filers, hold 1 (gross exposure 3–6%) | 0.22 | −0.32 (−1.26 .. 0.63) | −0.5% | 0.79 (−0.26 .. 1.87) | +1.1% / 1.4% / −1.4% |
| Earnings drift | 2005-01-03 → 2018 | high-volume 2.02 filers, hold 1 (gross exposure 1%) | 0.26 | −1.08 (−1.98 .. −0.01) | −0.8% | 0.61 (−0.27 .. 1.33) | +0.5% / 0.9% / −0.9% |

Realized net-exposure standard deviation is now 0.04 of capital in every cell (0.20 before the repair); the market-timing component of gross P&L is ≤ 25% in every cell with a non-trivial gross return. LOC fill rate on the rank book is 19%; the effective gross exposure is 0.11–0.49 of capital against a targeted 0.41–0.94, which is why annual returns are one to four percent even at a 10% volatility target: the limit-on-close filter leaves the book under-invested and the vol target is computed on the targeted, not the filled, book.

## Why the decision is still C

1. **The pre-registered development window fails.** On 2013-10-23 → 2018-12-14 the best rank configuration has a net Sharpe of 0.22 (DSR 0.19) and the event configuration that passes has a 2% gross book; on the validation window the rank pick earns 0.6%/yr and the event pick loses money. By the project's own rule the family did not earn a validation run, let alone a holdout.
2. **The results that look good are selected on the window the audit rejected.** The k=1/hold-3 rank configuration and the |z| ≥ 2 event configuration were selected on 2005–2018, where the 2005–2011 era (net Sharpe 1.85 and 1.48 respectively) dominates, on a panel with a 6–16% survivorship gap and intraday coverage below the pre-registered threshold. Their 2012–2018 Sharpes are 0.16 and 0.30.
3. **The one cell that would interest an allocator is not out-of-sample.** The event-reversal configuration selected on 2005–2018 earned a net Sharpe of 1.13 on 2023–2026 (+3.9%/yr at 3.4% vol, max drawdown −2.4%, positive in three of four years) after the repairs, against −0.02 for the same configuration on the frozen holdout. That swing is the product of four simultaneous code changes examined once on a spent window, for one of six cells. It is a candidate for a forward test, not evidence.
4. **Economic size.** Even the best cells earn 2–4% per year on capital at 2–3% realized volatility with a 19% fill rate; capacity under closing-auction impact is on the order of $5–20M; five basis points of slippage per side makes every cell negative.

## What the evidence supports
A day-one, no-news residual reversal in the 2005–2011 large-cap panel and in the 2020–2021 stress period; a premium that scales with lagged VIX; continuation rather than reversal after earnings 8-Ks; auction fills as a necessary condition. Not supported: a steady, economically meaningful net edge at this horizon in this universe after 2012 under either institutional cost profile.

## What it would take to revisit
A pre-registered forward paper test from 2026-09 of two candidates with the repaired code: (a) the event-reversal configuration |z| ≥ 2 / hold 3 / LOC δ=1 and (b) a VIX-top-tercile-gated rank reversal, both at ≤ $20M with exchange-member execution, the live news layer, and a kill rule (trailing 12-month net Sharpe < 0). The forward ledger is the only remaining out-of-sample instrument; 2023–2026 is spent. Before any capital: point-in-time sector history, enforced participation caps, permanent-id keying of membership, vol targeting on the filled book, and a second adversarial review of the forward-test design.

Not upgraded: C, not B, because no cell that survives the pre-registered protocol is economically meaningful, and the cells that are economically interesting were selected outside the protocol and examined on a spent window.
