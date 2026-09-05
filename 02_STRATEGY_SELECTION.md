# 02 — Strategy-domain selection

Date: 2026-09-05. Scores are 0–10 per criterion, assigned before any backtest, from the firm research (`01_FIRM_RESEARCH.md`), the literature (`03_LITERATURE_REVIEW.md`) and the environment/data audit recorded in the charter.

| Family | Relevance | Hypothesis strength | Data availability | Data quality | Execution modelability | Testability | Neutrality | Math/stat showcase | Python | C++ | Originality | Overfit-safety | Feasibility | Total /130 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **A. Residual short-term reversal, liquid US equities** | 9 | 8 | 8 | 7 | 6 | 9 | 9 | 9 | 9 | 7 | 6 | 7 | 8 | **102** |
| B. ETF / sector relative value | 7 | 5 | 9 | 8 | 6 | 8 | 8 | 7 | 8 | 6 | 5 | 6 | 9 | 92 |
| C. Microstructure / order flow | 10 | 8 | 3 | 8 | 8 | 7 | 6 | 9 | 8 | 10 | 8 | 6 | 4 | 95 |
| D. Options / volatility relative value | 8 | 7 | 2 | 3 | 3 | 6 | 6 | 9 | 7 | 6 | 7 | 5 | 3 | 72 |
| E. Overnight vs intraday decomposition | 7 | 6 | 7 | 7 | 5 | 8 | 7 | 7 | 8 | 5 | 6 | 6 | 8 | 87 |

Rationale per family:

- **A (selected).** The mechanism (liquidity provision / inventory pressure) is documented with pre- and post-cost evidence (Lehmann 1990; Jegadeesh 1990; Nagel 2012; De Groot, Huij & Zhou 2012; Blitz et al. 2013). Data: FMP daily history including delisted names for a point-in-time S&P 500 universe, plus 5-minute bars back to at least 2013 for closing-auction execution modelling. Weakness: no historical quote data, so spreads for continuous-session fills must be estimated with range-based estimators; mitigated by auction fills as the primary execution and by reporting the break-even cost.
- **B.** Feasible without credentials but the cross-section is small (11–100 ETFs), the daily mean-reversion hypothesis is weaker, and delisted-ETF survivorship still needs handling. Retained as the pre-registered fallback B1.
- **C.** Highest relevance and the best C++ showcase but fails the data gate: multi-year quote/trade history is not available within budget (Databento's US-equities datasets start in 2023; the $125 credit covers days, not years).
- **D.** No historical option chains with executable bid/ask; rejected on data quality.
- **E.** Feasible but a narrower hypothesis; its useful element (overnight reversal captured by closing-auction execution) is absorbed into A.

**Decision (user-approved 2026-09-05):** Family A only, re-engineered for execution an individual can perform: closing-auction (MOC) fills as the primary model on the 2013→2026 intraday sample, a resting-limit-order liquidity-provision variant, VIX-regime sizing, and a two-sleeve book (low-turnover reversal, high-turnover continuation). Fallback B1 runs only if H1 is falsified on the development sample.

Avoided by construction: indicator crossovers, moving-average optimisation, single-stock neural prediction, and any strategy chosen because its equity curve looks good.
