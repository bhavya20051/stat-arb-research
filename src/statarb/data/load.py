"""Load processed data into wide frames (dates x symbols) and recompute adjustments independently.

Adjustment policy: returns are computed from the vendor's split+dividend adjusted close ("adj_close") but are
cross-checked against an adjustment factor recomputed from the raw close, the splits table and the dividends
table (audit).  Fill prices for execution use the split-adjusted (not dividend-adjusted) series so that share
counts and commissions are in real shares; P&L uses total returns via the adjusted series.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd

from statarb.config import data_dir

PROC = data_dir() / "processed"


@lru_cache(maxsize=1)
def daily_long() -> pd.DataFrame:
    df = pd.read_parquet(PROC / "daily_prices.parquet")
    df["date"] = pd.to_datetime(df["date"])
    return df


def wide(col: str, symbols: list[str] | None = None) -> pd.DataFrame:
    df = daily_long()
    if symbols is not None:
        df = df[df["symbol"].isin(symbols)]
    w = df.pivot(index="date", columns="symbol", values=col).sort_index()
    return w


def membership_intervals() -> pd.DataFrame:
    m = pd.read_csv(PROC / "sp500_membership_intervals.csv", parse_dates=["start", "end"])
    return m


def membership_mask(dates: pd.DatetimeIndex, symbols: list[str], lag_days: int = 1) -> pd.DataFrame:
    """True where symbol is an index member on date (membership effective lag_days trading days after the change)."""
    m = membership_intervals()
    pos = {s: i for i, s in enumerate(symbols)}
    arr = np.zeros((len(dates), len(symbols)), dtype=bool)
    for _, r in m.iterrows():
        s = r["symbol"]
        if s not in pos:
            continue
        start = r["start"] if pd.notna(r["start"]) else dates[0]
        end = r["end"] if pd.notna(r["end"]) else dates[-1] + pd.Timedelta(days=1)
        i0 = dates.searchsorted(start) + lag_days
        i1 = dates.searchsorted(end) + lag_days  # removal also takes effect after the change date
        arr[min(i0, len(dates)) : min(i1, len(dates)), pos[s]] = True
    return pd.DataFrame(arr, index=dates, columns=symbols)


def recompute_adjustment_factor(symbol: str) -> pd.Series | None:
    """Cumulative split factor from the splits table, applied backward: price_adj = price_raw / cum_split_after."""
    try:
        sp = pd.read_parquet(PROC / "splits.parquet")
    except FileNotFoundError:
        return None
    sp = sp[sp["symbol"] == symbol]
    if sp.empty:
        return None
    sp = sp.assign(date=pd.to_datetime(sp["date"]), ratio=sp["numerator"] / sp["denominator"]).sort_values("date")
    return sp.set_index("date")["ratio"]
