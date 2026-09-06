# 06 — Data audit

Generated 2026-09-05 by `statarb.data.audit` from `C:\Users\bhavy\statarb_data\processed`.

- Rows: 3,777,995; symbols: 848; date range 2005-01-03 → 2026-08-31.
- Trading days (SPY): 5,449. First 2005-01-03, last 2026-08-31.
- Duplicate (symbol, date) rows: 0.
- Impossible bars (high<low or close outside [low,high]): 0; non-positive prices: 0.
- Zero-volume symbol-days: 11,877 (0.314% of observations).
- Stale closes (5 identical consecutive): 5,564 symbol-days.
- |daily return| > 50%: 360 symbol-days (cross-checked against splits below).
- Adjustment-ratio jumps: 48,030; not matching a split/dividend date: 13,840 (28.8%).
- Known split AAPL 2020-08-31 4:1 — close ratio prev/day 0.967 (≈4 if close is unadjusted, ≈1 if split-adjusted); adjClose ratio 0.967.
- Known split TSLA 2022-08-25 3:1 — close ratio prev/day 1.003 (≈3 if close is unadjusted, ≈1 if split-adjusted); adjClose ratio 1.003.
- Known split NVDA 2024-06-10 10:1 — close ratio prev/day 0.993 (≈10 if close is unadjusted, ≈1 if split-adjusted); adjClose ratio 0.993.
- Membership symbols without any price rows: 112: ABS, ACAS, ANDW, ANR, APCC, ASN, AV, AW, AYE, BCR, BDK, BJS, BLS, BMC, BMET, BRL, BSC, BXLT, CBE, CBSS, CEPH, CFC, CFN, CIN, CMCSK, CMVT, CMX, COV, CVH, DF, DJ, DPH, DPS, DWDP, EDS, EOP, FDC, FDO, FRX, FSH …

| Year | trading days | symbols with data |
|---|---|---|
| 2005 | 252 | 604 |
| 2006 | 251 | 616 |
| 2007 | 251 | 633 |
| 2008 | 253 | 644 |
| 2009 | 252 | 651 |
| 2010 | 252 | 665 |
| 2011 | 252 | 677 |
| 2012 | 250 | 692 |
| 2013 | 252 | 708 |
| 2014 | 252 | 722 |
| 2015 | 252 | 738 |
| 2016 | 252 | 745 |
| 2017 | 251 | 749 |
| 2018 | 251 | 750 |
| 2019 | 252 | 748 |
| 2020 | 253 | 756 |
| 2021 | 252 | 753 |
| 2022 | 251 | 743 |
| 2023 | 250 | 730 |
| 2024 | 252 | 728 |
| 2025 | 250 | 726 |
| 2026 | 166 | 710 |

## Survivorship gap (members without any FMP price history)

112 of the 948 symbols with S&P 500 membership overlapping 2005+ have no price rows on FMP (mostly pre-2012 acquisitions and failures, e.g. BSC, CFC, ANR). Their absence biases the early development years; validation and holdout are unaffected.

| Year | active members | without prices | gap % |
|---|---|---|---|
| 2005 | 505 | 81 | 16.0 |
| 2006 | 521 | 79 | 15.2 |
| 2007 | 526 | 73 | 13.9 |
| 2008 | 530 | 63 | 11.9 |
| 2009 | 522 | 55 | 10.5 |
| 2010 | 512 | 48 | 9.4 |
| 2011 | 515 | 45 | 8.7 |
| 2012 | 513 | 37 | 7.2 |
| 2013 | 515 | 30 | 5.8 |
| 2014 | 510 | 24 | 4.7 |
| 2015 | 521 | 24 | 4.6 |
| 2016 | 527 | 12 | 2.3 |
| 2017 | 524 | 9 | 1.7 |
| 2018 | 519 | 6 | 1.2 |
| 2019 | 517 | 2 | 0.4 |
| 2020 | 516 | 0 | 0.0 |
| 2021 | 520 | 0 | 0.0 |
| 2022 | 519 | 0 | 0.0 |
| 2023 | 519 | 0 | 0.0 |
| 2024 | 527 | 0 | 0.0 |
| 2025 | 529 | 0 | 0.0 |
| 2026 | 523 | 0 | 0.0 |

Handling: the gap is reported alongside every DEV result; the 2005–2011 DEV years are treated as lower-quality and the registry notes 'survivorship gap 9–16%' for tests that use them. The 2013+ intraday primary sample has a gap of ≤ 5.8%.

## Open audit items
- 28.8% of adjustment-ratio jumps do not coincide with a recorded split/dividend date (likely ex-date vs record-date conventions in FMP's dividends table); to be resolved before the report by matching within ±3 days.
- FMP daily `open` provenance (auction print vs first trade) unverified; affects only the secondary next-open model.
- 185 symbols lack a CIK in their FMP profile, so 8-K coverage is 763/948 symbols; the missing names are mostly delisted and will be mapped through EDGAR's company search.

## Spread-estimator check (2026-09-05)
Range-based spread estimates (Corwin–Schultz / Abdi–Ranaldo, 21-day) give a median full spread of 42–56 bp per year for eligible S&P 500 names (2018 p10/p50/p90 = 28/52/100 bp), about ten times the quoted spreads of these stocks. The estimators are therefore rejected as a cost basis for large caps (registry COST-2); the primary execution models use auction or resting-limit fills that pay no spread.

## Membership cross-check vs Wikipedia (2026-09-05)
Current 503 constituents identical in FMP and Wikipedia; 'date added' agrees exactly for 98.2% of names (99.0% within 7 days). The remaining differences are the GOOG/GOOGL share-class listing dates and DowDuPont's 2019 reorganisation. Wikipedia no longer publishes the historical change table, so historical membership relies on FMP's change list (registry UNIV-1).
