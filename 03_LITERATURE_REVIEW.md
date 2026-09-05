# 03 — Literature review and economic hypotheses

Date: 2026-09-05. Items marked [verified] were located on the publisher/repository page during the plan audit; items marked [to verify at M1b] are cited from the author's knowledge and will be checked against the DOI page before the final report cites them. Nothing below is an empirical result of this project.

## Does the phenomenon exist? Mechanism, horizon, conditions

| Paper | Finding relevant to this project | Pre/post cost | Status |
|---|---|---|---|
| Lehmann (1990), "Fads, martingales, and market efficiency", QJE 105(1) | Weekly winners/losers reverse; profits sensitive to costs. | mostly pre-cost | [to verify at M1b] |
| Jegadeesh (1990), "Evidence of predictable behavior of security returns", JF 45(3) | Strong one-month reversal in US stocks. | pre-cost | [to verify at M1b] |
| Campbell, Grossman & Wang (1993), QJE 108(4) | Reversal after high-volume days is consistent with non-informational (liquidity) trading; volume conditions the reversal. | theory + evidence | [to verify at M1b] |
| Avellaneda & Lee (2010), "Statistical arbitrage in the US equities market", Quantitative Finance 10(7):761–782, doi 10.1080/14697680903124632 | PCA/ETF-residual mean-reversion strategies: Sharpe ≈1.44 (1997–2007) after their cost model, ≈0.9 in 2003–2007; degradation after 2002; stress in summer 2007. | post-cost (their model) | [verified — publisher page and SSRN 1153505] |
| Nagel (2012), "Evaporating liquidity", RFS 25(7):2005–2039 | Short-term reversal returns proxy the return to liquidity provision; predictable by VIX; expected returns spike in turmoil. | mostly pre-cost | [verified — OUP abstract, NBER w17653] |
| De Groot, Huij & Zhou (2012), "Another look at trading costs and short-term reversal profits", JBF | Costs eat reversal profits in small caps; large caps plus turnover-aware construction leave 30–50 bp/week net. | post-cost | [verified — SSRN 1605049 / RePub 25718] |
| Blitz, Huij, Lansdorp & Verbeek (2013), "Short-term residual reversal", JFM 16(3):477–504, doi 10.1016/j.finmar.2012.10.005 | Reversal on residual returns has ~2× the risk-adjusted return of conventional reversal and stays significant net of costs in large caps post-1990. | post-cost | [verified — publisher page, SSRN 1911449] |
| Da, Liu & Schaumburg (2014), "A closer look at the short-term return reversal", Management Science 60(3) | Across-industry (fundamental) vs within-industry residual reversal; the residual part is the robust liquidity-driven component. | pre/post | [to verify at M1b] |
| Medhat & Schmeling (2022), "Short-term momentum", RFS 35(3):1480–1533 | Low-turnover stocks reverse; high-turnover stocks show short-term momentum that survives costs and is strongest in the largest, most liquid stocks. | post-cost | [verified — OUP page, SSRN 3150525] |
| Chan (2003), "Stock price reaction to news and no-news", JFE 70(2) | Reversal after large no-news moves; drift after news moves. | pre-cost | [to verify at M1b] |
| Tetlock (2011), "All the news that's fit to reprint", RFS 24(5) | Stale-news moves reverse; genuinely new information continues. | pre-cost | [to verify at M1b] |

Crowding and decay: Avellaneda & Lee document decay after 2002; later decay is commonly attributed to reversal harvesting migrating to intraday horizons. This project treats "the effect has weakened" as the null and tests whether a slower, cost-aware, news-filtered, regime-scaled version still pays on 2023–2026 data.

## Cost, execution and statistics references

| Paper | Use in this project | Status |
|---|---|---|
| Corwin & Schultz (2012), "A simple way to estimate bid-ask spreads from daily high and low prices", JF 67(2) | Range-based spread estimator for continuous-session fills. | [to verify at M1b] |
| Abdi & Ranaldo (2017), "A simple estimation of bid-ask spreads from daily close, high, and low prices", RFS 30(12) | Second estimator; basis = max of the two plus a liquidity floor. | [to verify at M1b] |
| Ardia, Guidotti & Kroencke (2024), "Efficient estimation of bid-ask spreads from open, high, low, and close prices", JFE | Accuracy of range estimators in liquid names; sign of level bias. | [to verify at M1b] |
| Almgren, Thum, Hauptmann & Li (2005), "Direct estimation of equity market impact" | Square-root impact model, k ≈ 1. | [to verify at M1b] |
| Shumway (1997), "The delisting bias in CRSP data", JF 52(1) | −30% convention for performance delistings of unknown return. | [to verify at M1b] |
| Lo (2002), "The statistics of Sharpe ratios", FAJ 58(4) | Sharpe standard error with autocorrelation. | [to verify at M1b] |
| Bailey & López de Prado (2012) J. Risk 15(2); (2014) "The deflated Sharpe ratio", JPM 40(5) | PSR and DSR; SR* = √V[SR]·((1−γ)Φ⁻¹(1−1/N) + γΦ⁻¹(1−1/(N·e))). | [verified during plan review against the author's copy at davidhbailey.com] |
| Bailey, Borwein, López de Prado & Zhu (2017), "The probability of backtest overfitting", J. Comput. Finance 20(4) | CSCV / PBO with S = 16 blocks; candidates only, never placebos. | [verified during plan review] |
| Politis & Romano (1994), "The stationary bootstrap", JASA 89(428); Politis & White (2004) | Block bootstrap CIs and block-length rule. | [to verify at M1b] |
| NYSE closing auction fact sheet (nyse.com) | MOC order entry cutoff 15:50 ET. | [verified during plan review] |

## Pre-registered hypotheses

The registry (`04_HYPOTHESIS_REGISTRY.csv`) holds H1–H8 and fallback B1 with signal definitions, universes, horizons, models, parameters, sample periods, expected results and falsification conditions.

- **H1 (core).** HYPOTHESIS: stock-specific residual returns over the last 1–5 days negatively predict the next 1–5 days for moves without material company news. MECHANISM: liquidity provision / inventory pressure. SIGN: negative. HORIZON: 1–5 days, decaying. CONFOUNDERS: market and sector moves (removed by residualisation), information-driven moves (news layer, turnover conditioning), earnings (pre-event exclusion), halts/delistings (security master). FAILURE CONDITION: Fama–MacBeth slope not significantly negative or decile spread ≤ 0 on DEV. TEST: FM regressions with Newey–West errors; decile long-short portfolios; decay curve.
- **H2** turnover conditioning; **H3** VIX conditioning; **H4** residual vs raw; **H5** net-of-cost survival on untouched validation; **H6** decay-implied horizon; **H7** news vs no-news; **H8** post-news drift; **B1** ETF fallback — each with mechanism, sign, horizon, confounders, failure condition and test in the registry.
