"""Limit-order execution variants simulated on 15-minute bars (pre-registered candidates, configs/costs.yaml).

Variant "limit" (resting limit during the next session):
  weights decided at 15:40 on day t; for names whose |weight| INCREASES a limit order rests during session t+1 at
  ref * (1 - delta*sigma) for buys / ref * (1 + delta*sigma) for sells, where ref = last-bar close of day t (intraday
  basis) and sigma = trailing daily residual vol (known at t). It fills at the limit if some 15-min bar through the
  15:30 bar (complete 15:45) trades through the limit by at least `through` (default 5 bp, proxy for one tick plus
  half a large-cap spread); otherwise it is cancelled (position unchanged). Names whose |weight| decreases exit MOC
  at the close of t+1. No spread is paid on limit fills (the order provides liquidity); commissions/fees apply.

Variant "loc" (limit-on-close on day t):
  a buy fills at the close of day t only if close_t <= p1545 * (1 - delta*sigma_intraday) (the stock keeps falling
  into the auction); otherwise cancelled. Exits by MOC. This captures day-1 reversal only on continued pressure.

Both return a fill-price panel (adj_close basis) with NaN where no fill occurs, plus a diagnostics frame.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from statarb.data.load import PROC


def session_extremes(symbols: list[str], cutoff: str = "15:45") -> tuple[pd.DataFrame, pd.DataFrame]:
    """Per-day min low and max high over 15-min bars whose start time is before `cutoff` (intraday basis)."""
    lows, highs = {}, {}
    hh, mm = (int(x) for x in cutoff.split(":"))
    for s in symbols:
        f = PROC / "intraday_15min" / f"{s}.parquet"
        if not f.exists():
            continue
        df = pd.read_parquet(f, columns=["ts", "low", "high"])
        ts = pd.to_datetime(df["ts"])
        keep = (ts.dt.hour * 60 + ts.dt.minute) < hh * 60 + mm
        d = df[keep].assign(day=ts[keep].dt.normalize())
        g = d.groupby("day")
        lows[s] = g["low"].min()
        highs[s] = g["high"].max()
    return pd.DataFrame(lows).sort_index(), pd.DataFrame(highs).sort_index()


def resting_limit_fills(target_w: pd.DataFrame, ref_intraday: pd.DataFrame, last_bar_close: pd.DataFrame,
                        adj_close: pd.DataFrame, sigma: pd.DataFrame, lows: pd.DataFrame, highs: pd.DataFrame,
                        delta: float = 0.5, through: float = 0.0005) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fill panel aligned to fill day t+1 for weights decided on day t (engine lag=1).

    Entries (|w_t| > |w_{t-1}| in the same direction) require a limit fill; reductions/exits fill at the close.
    Returns (fill_price on adj_close basis, filled_entry flag)."""
    idx = target_w.index
    prev = target_w.shift(1).fillna(0.0)
    increase_long = (target_w > prev) & (target_w > 0)
    increase_short = (target_w < prev) & (target_w < 0)
    entry = increase_long | increase_short
    ref = ref_intraday.reindex(index=idx, columns=target_w.columns)
    sig = sigma.reindex(index=idx, columns=target_w.columns)
    buy_limit = ref * (1 - delta * sig)
    sell_limit = ref * (1 + delta * sig)
    # next-session extremes (day t+1) aligned to decision day t
    lo_next = lows.reindex(index=idx, columns=target_w.columns).shift(-1)
    hi_next = highs.reindex(index=idx, columns=target_w.columns).shift(-1)
    hit_buy = lo_next <= buy_limit * (1 - through)
    hit_sell = hi_next >= sell_limit * (1 + through)
    limit_px = buy_limit.where(increase_long).combine_first(sell_limit.where(increase_short))
    filled = (increase_long & hit_buy) | (increase_short & hit_sell)
    # convert intraday-basis limit price to the adj_close basis using day t+1's ratio
    ratio_next = (adj_close.reindex(index=idx, columns=target_w.columns) / last_bar_close.reindex(index=idx, columns=target_w.columns)).shift(-1)
    fill_next = pd.DataFrame(np.nan, index=idx, columns=target_w.columns)
    close_next = adj_close.reindex(index=idx, columns=target_w.columns).shift(-1)
    fill_next = fill_next.where(entry, close_next)                       # non-entries: MOC at close t+1
    fill_next = fill_next.mask(entry & filled, limit_px * ratio_next)     # filled entries: at the limit
    # fill_next is indexed by decision day t; the engine wants fill_price.loc[t+1] -> shift forward by one day
    return fill_next.shift(1), filled.shift(1).fillna(False)


def loc_fills(target_w: pd.DataFrame, p1545: pd.DataFrame, last_bar_close: pd.DataFrame, adj_close: pd.DataFrame,
              sigma_intraday: pd.DataFrame, delta: float = 0.5) -> pd.DataFrame:
    """Limit-on-close on day t: entries fill at the close only if the close is beyond p1545 by delta*sigma in the
    order's favour; reductions fill MOC. Returns fill panel on the adj_close basis aligned to day t (engine lag=0)."""
    idx = target_w.index
    prev = target_w.shift(1).fillna(0.0)
    increase_long = (target_w > prev) & (target_w > 0)
    increase_short = (target_w < prev) & (target_w < 0)
    entry = increase_long | increase_short
    p = p1545.reindex(index=idx, columns=target_w.columns)
    lb = last_bar_close.reindex(index=idx, columns=target_w.columns)
    sig = sigma_intraday.reindex(index=idx, columns=target_w.columns)
    close_rel = lb / p - 1.0  # move from 15:45 to the close in intraday basis
    ok = (increase_long & (close_rel <= -delta * sig)) | (increase_short & (close_rel >= delta * sig))
    ac = adj_close.reindex(index=idx, columns=target_w.columns)
    fill = ac.where(~entry | ok)
    return fill
