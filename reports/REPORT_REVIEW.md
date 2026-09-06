# Report review (2026-09-06) — PM_REPORT.html and QUANT_RESEARCH_REPORT.html

Independent fresh-context reviewer, read-only; 1,788 scripted cell comparisons against the result files (1,673 exact, remainder parser coercion plus findings 1 and 15); headline statistics recomputed from the daily CSVs. Disposition column added by the author after the fixes.

| # | Severity | Location | What is wrong | Evidence | Disposition |
|---|---|---|---|---|---|
| 1 | BLOCKER | Earnings-drift rows in every table of both reports | Earnings-drift cells were run WITHOUT the volume/timing conditioning of the selected id (`spec_from_choice` dropped `drift_timing` / `drift_volume_bucket`), so the numbers belonged to the unconditioned k1/h1/z1 book and did not match the DEV grid (0.376 vs 0.218; 0.200 vs 0.256). | `selection_*.json` params lacked the keys; `run_post_audit_full.py:96`; grid CSV vs full_metrics | FIXED: `select()` and `spec_from_choice` propagate both keys; selection files repaired; all earnings cells rerun (`rerun_earnings_cells.py`). |
| 2 | BLOCKER | PM §1, §5, §6 return and drawdown columns | Fractions printed as "0.01 / 0.00 / -0.00". | `pm_report.py` `_table` default format | FIXED: percentage formatting everywhere. |
| 3 | BLOCKER | PM §8 Leverage, §1 | "reaching 10% vol would require gross near or beyond the 3× cap for most cells" is false; the report's own column shows 0.2×–2.4×. | `full_metrics.json` avg_gross / ann_vol | FIXED: actual range stated; binding constraint is auction capacity. |
| 4 | BLOCKER | PM §1/§8/§9 | The event-reversal cell selected on the 2005 window (VAL 0.95, 2023–26 1.13, +3.9%/yr) was never addressed in the client report. | `post_audit_results.json` `event_reversal@full_2005` | FIXED: dedicated paragraph in §1 and §8 with the FINAL_DECISION caveats. |
| 5 | HIGH | PM §1 | "net Sharpe ratios are near zero or negative … on all three windows" is false for several single cells. | `full_metrics.json` | FIXED: rewritten as "no pre-registered selection holds a positive net Sharpe across all three windows". |
| 6 | HIGH | PM §8 Tail | Kurtosis and ex-best-day figures quoted for one cell as if general. | diag kurtosis 14–73; ex-best-day −0.38…1.00 | FIXED: per-cell table. |
| 7 | HIGH | PM §8 Regime | "Excluding 2020–21 the validation Sharpe is negative" true for two cells only. | `era.sr_ex_2020_2021` | FIXED: values quoted per cell. |
| 8 | HIGH | PM §4 | Event/earnings books are episodic (in market 9–20% of days); hit rate counts flat days as misses; "unlevered +36%/yr" on a 2%-of-capital book. | daily CSVs | FIXED: "days in market" column, hit rate over active days, explicit "episodic book" note. |
| 9 | HIGH | PM §4 yearly unlevered rows | Per-year return divided by window-average gross prints returns no book earned (+110%, −93%). | `pm_report.py` | FIXED: each year's own average gross; blank when < 20 active days. |
| 10 | HIGH | PM §1/§8 | Gross-exposure range and its attribution (LOC fill rate) wrong for MOC event/earnings books. | avg_gross by family | FIXED: per-family ranges; entrant-count sizing named. |
| 11 | HIGH | PM §4 headers | DSR NaN rendered as empty string; PBO 0.00 / PSR 1.00 unexplained for tiny books. | `multiple_testing` | FIXED: "not computable (candidates with no trades)" and a caveat on PBO for episodic books. |
| 12 | HIGH | PM §7 open items | Pooled-N DSR figures (0.62→0.51→0.38) are pre-audit but read as current. | `selection.json` vs `full_metrics.json` | FIXED: labelled pre-audit; post-audit DSRs quoted. |
| 13 | MEDIUM | PM §1 | "holdout … in section 7" → section 6. | headings | FIXED. |
| 14 | MEDIUM | PM §8/§9 capacity | "$5–20M" overstated; ≥90%-of-peak rule gives $1M (rank prereg), $5M (event prereg). | capacity tables | FIXED. |
| 15 | MEDIUM | PM §1 / footer | ann_return is geometric; "SR × 10%" gloss and "uncompounded" footer imprecise. | recompute | FIXED: described as as-run return × (10% / realized vol); footer corrected. |
| 16 | MEDIUM | PM §7, QUANT | Market-component share > 1 shown when cumulative gross ≈ 0. | `market_component` | FIXED: blanked when |cum gross| < 1%. |
| 17 | MEDIUM | PM §8 | "turnover roughly half the book per day" is pre-audit. | `turnover_per_day` | FIXED: actual figures. |
| 18 | MEDIUM | PM/QUANT yearly charts | Partial years (2013: 46 days; 2026: 8 months) plotted as full years. | daily CSVs | FIXED: partial years labelled and excluded from the Sharpe bars. |
| 19 | MEDIUM | PM §5 capacity | Gross SR varies with capital without explanation. | capacity tables | FIXED: sentence added (impact feeds the drawdown brake, which rescales the book). |
| 20 | MEDIUM | PM §5 kill tests | Blank cells for variants that traded nothing. | kill_tests NaN | FIXED: "no trades". |
| 21 | MEDIUM | PM §8/§9 | Mechanism / VIX figures are pre-audit diagnostics; VIX-gated design rests on them. | registry, `regimes_concentration.json` | FIXED: labelled pre-audit with the F1 caveat; VIX gating presented as an untested hypothesis. |
| 22 | MEDIUM | QUANT executive summary | Withdrawn 0.89/0.93 tables appear before the audit notice. | `html_report.py` | FIXED: audit notice first; pre-audit tables headed "(withdrawn, for the record)". |
| 23 | MEDIUM | QUANT registry paragraph | 146 vs 140 candidates. | registry | FIXED: grid rows only. |
| 24 | MEDIUM | QUANT holdout section | Truncated JSON dumps. | `html_report.py` | FIXED: per-family table. |
| 25 | LOW | PM §4 | Sign prefix on hit rate / +months. | | FIXED. |
| 26 | LOW | PM figures | Equity figures compound; tables do not. | | FIXED: caption states compounded. |
| 27–28 | LOW | QUANT | "None" cells; unrounded PBO / "DSR nan". | | FIXED. |
| 29 | LOW | PM appendix | C++ claim without citation. | `cpp/benchmark.md` | FIXED: benchmark file cited. |
| 30 | LOW | PM eyebrow | Build date instead of result vintage. | `generated_utc` | FIXED. |

Done right (reviewer): every table cell traced to a result file matched; JSON metrics reproduce from the daily CSVs; the holdout Sharpe 0.1650 reproduces; 2023–2026 consistently labelled a diagnostic; the three return bases computed as described; cost table matches the config; audit summary faithful; pre-audit numbers explicitly withdrawn; both profiles and the full kill-test suite shown for every family × window.
