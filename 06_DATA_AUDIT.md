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
