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
              sigma_intraday: pd.DataFrame, delta: float = 0.5, hedge_symbol: str | None = "SPY",
              beta: pd.DataFrame | None = None, net_abs_max: float = 0.05,
              return_effective: bool = False):
    """Limit-on-close on day t (post-audit version, 2026-09-06; red-team findings F1 and F4).

    * An *entry* is an increase in |weight| relative to the weight actually HELD after yesterday's fill decision
      (not relative to yesterday's target): an entry whose LOC was cancelled stays an entry the next day and is
      again submitted as an LOC order; it never degrades into an unconditional MOC fill.
    * The LOC condition is evaluated on the OFFICIAL close: the 15:45 -> close move is the official close-to-close
      return divided by the intraday return from yesterday's last bar to today's 15:45 price. A buy fills only if
      the official close is at or below p1545 * (1 - delta*sigma); a sell only if at or above p1545 * (1 + delta*sigma).
    * Reductions fill MOC. The hedge symbol (SPY) is never LOC-gated: after the fill decision the hedge is re-sized to
      the FILLED stock book, -sum(w_filled * beta) (beta lagged, supplied by the caller; 1.0 if absent), and then
      shifted so that the realized dollar-net of the whole book is inside +/- net_abs_max. It fills MOC.

    Returns the fill panel (adj_close basis, NaN = cancelled) and, if return_effective, the post-decision target book
    (cancelled entries carry the held weight; hedge column re-sized) which the engine should be given as targets.
    """
    idx = target_w.index
    cols = list(target_w.columns)
    N = len(cols)
    W = target_w.fillna(0.0).to_numpy(dtype=float)
    ac = adj_close.reindex(index=idx, columns=cols).to_numpy(dtype=float)
    p = p1545.reindex(index=idx, columns=cols).to_numpy(dtype=float)
    lb = last_bar_close.reindex(index=idx, columns=cols).to_numpy(dtype=float)
    sig = sigma_intraday.reindex(index=idx, columns=cols).to_numpy(dtype=float)
    ac_prev = np.vstack([np.full((1, N), np.nan), ac[:-1]])
    lb_prev = np.vstack([np.full((1, N), np.nan), lb[:-1]])
    with np.errstate(invalid="ignore", divide="ignore"):
        close_rel = (ac / ac_prev) / (p / lb_prev) - 1.0     # 15:45 -> official close, on a common basis
    hj = cols.index(hedge_symbol) if hedge_symbol in cols else None
    B = beta.reindex(index=idx, columns=cols).fillna(0.0).to_numpy(dtype=float) if beta is not None else None
    held = np.zeros(N)
    W_eff = np.zeros_like(W)
    fill = ac.copy()
    for t in range(len(idx)):
        tgt = W[t].copy()
        if hj is not None:
            tgt[hj] = 0.0
        inc_long = (tgt > held) & (tgt > 0)
        inc_short = (tgt < held) & (tgt < 0)
        entry = inc_long | inc_short
        cr = close_rel[t]
        s = sig[t]
        ok = (inc_long & (cr <= -delta * s)) | (inc_short & (cr >= delta * s))
        cancel = entry & ~ok
        eff = np.where(cancel, held, tgt)
        fill[t, cancel] = np.nan
        if hj is not None:
            stock = eff.copy()
            stock[hj] = 0.0
            b = B[t] if B is not None else np.ones(N)
            h = -float(np.nansum(stock * b))
            net = float(np.nansum(stock)) + h
            h -= net - float(np.clip(net, -net_abs_max, net_abs_max))
            eff[hj] = h
            fill[t, hj] = ac[t, hj]
        W_eff[t] = eff
        held = np.where(np.isfinite(fill[t]), eff, held)
    fill_df = pd.DataFrame(fill, index=idx, columns=cols)
    if return_effective:
        return fill_df, pd.DataFrame(W_eff, index=idx, columns=cols)
    return fill_df
