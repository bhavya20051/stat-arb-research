"""Forensic data audit -> 06_DATA_AUDIT.md (scripted, reproducible)."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from statarb.config import REPO_ROOT
from statarb.data.load import PROC, daily_long, membership_intervals, wide


def nyse_calendar_from_spy() -> pd.DatetimeIndex:
    spy = daily_long()
    spy = spy[spy["symbol"] == "SPY"]
    return pd.DatetimeIndex(sorted(spy["date"].unique()))


def run_audit() -> str:
    df = daily_long()
    lines = [f"# 06 — Data audit\n\nGenerated {date.today()} by `statarb.data.audit` from `{PROC}`.\n"]
    n_sym = df["symbol"].nunique()
    lines.append(f"- Rows: {len(df):,}; symbols: {n_sym}; date range {df['date'].min().date()} → {df['date'].max().date()}.")
    cal = nyse_calendar_from_spy()
    lines.append(f"- Trading days (SPY): {len(cal):,}. First {cal[0].date()}, last {cal[-1].date()}.")
    dup = df.duplicated(["symbol", "date"]).sum()
    lines.append(f"- Duplicate (symbol, date) rows: {dup}.")
    close = wide("close")
    hi, lo, op, vol = wide("high"), wide("low"), wide("open"), wide("volume")
    bad_hl = int(((hi < lo) | (close > hi * 1.0001) | (close < lo * 0.9999)).sum().sum())
    nonpos = int(((close <= 0) | (op <= 0)).sum().sum())
    lines.append(f"- Impossible bars (high<low or close outside [low,high]): {bad_hl}; non-positive prices: {nonpos}.")
    zero_vol = int((vol == 0).sum().sum())
    lines.append(f"- Zero-volume symbol-days: {zero_vol:,} ({zero_vol / vol.notna().sum().sum():.3%} of observations).")
    stale = int(((close == close.shift(1)) & (close == close.shift(2)) & (close == close.shift(3)) & (close == close.shift(4))).sum().sum())
    lines.append(f"- Stale closes (5 identical consecutive): {stale:,} symbol-days.")
    ret = close.pct_change()
    big = (ret.abs() > 0.5)
    lines.append(f"- |daily return| > 50%: {int(big.sum().sum())} symbol-days (cross-checked against splits below).")
    # split consistency: adjClose/close ratio should be piecewise constant; jumps should coincide with splits/dividends
    if "adj_close" in df.columns:
        adj = wide("adj_close")
        ratio = (adj / close)
        jumps = (ratio / ratio.shift(1) - 1).abs() > 1e-6
        n_jumps = int(jumps.sum().sum())
        try:
            sp = pd.read_parquet(PROC / "splits.parquet")
            dv = pd.read_parquet(PROC / "dividends.parquet")
            ev = set(zip(sp["symbol"], pd.to_datetime(sp["date"]))) | set(zip(dv["symbol"], pd.to_datetime(dv["date"])))
            js = [(s, d) for d, row in jumps.iterrows() for s in row.index[row.to_numpy()]]
            unexplained = [x for x in js if x not in ev]
            lines.append(f"- Adjustment-ratio jumps: {n_jumps:,}; not matching a split/dividend date: {len(unexplained):,} ({len(unexplained) / max(n_jumps, 1):.1%}).")
        except FileNotFoundError:
            lines.append(f"- Adjustment-ratio jumps: {n_jumps:,} (splits/dividends tables missing).")
        # known splits
        for s, d, k in [("AAPL", "2020-08-31", 4.0), ("TSLA", "2022-08-25", 3.0), ("NVDA", "2024-06-10", 10.0)]:
            if s in close.columns and pd.Timestamp(d) in close.index:
                i = close.index.get_loc(pd.Timestamp(d))
                raw_jump = close[s].iloc[i - 1] / close[s].iloc[i]
                adj_jump = adj[s].iloc[i - 1] / adj[s].iloc[i]
                lines.append(f"- Known split {s} {d} {k:.0f}:1 — close ratio prev/day {raw_jump:.3f} (≈{k:.0f} if close is unadjusted, ≈1 if split-adjusted); adjClose ratio {adj_jump:.3f}.")
    # membership coverage
    m = membership_intervals()
    have = set(df["symbol"].unique())
    missing = sorted(set(m["symbol"].dropna()) - have)
    lines.append(f"- Membership symbols without any price rows: {len(missing)}: {', '.join(missing[:40])}{' …' if len(missing) > 40 else ''}")
    # per-year counts of members with data
    cal_years = pd.Series(cal.year).value_counts().sort_index()
    lines.append("\n| Year | trading days | symbols with data |\n|---|---|---|")
    counts = df.groupby(df["date"].dt.year)["symbol"].nunique()
    for y, n in counts.items():
        lines.append(f"| {y} | {cal_years.get(y, 0)} | {n} |")
    text = "\n".join(lines) + "\n"
    (REPO_ROOT / "06_DATA_AUDIT.md").write_text(text, encoding="utf-8")
    return text
