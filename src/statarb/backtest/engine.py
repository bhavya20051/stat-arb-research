"""Daily portfolio simulation with explicit timing, fill rules, delistings and costs.

Timing model
------------
Target weights `w[t]` are decided at the decision time of day t (15:40 ET for the closing-auction model, or the
close for the daily model).  They are executed at the fill price of bar `t + lag`:
  * MOC model: lag = 0, fill = official close of day t (decision 15:40 < 16:00 close).
  * MOO model: lag = 1, fill = open of day t+1.
The position established at fill f_t earns the return from f_t to f_{t+1} (fill-to-fill).  Nothing at time t uses
information after the decision time: the engine only reads `w[t]`, `fill_price[t+lag]`, `fill_volume[t+lag]`.

Fill rules
----------
An order fills only if the fill bar has a printed trade (volume > 0 and a finite price).  Otherwise the order is
cancelled and the previous (drifted) position is carried.

Delistings
----------
`delist` maps symbol -> (date, return).  On the delisting date the position is closed at the pre-registered
return (M&A: 0 relative to last price; bankruptcy: -1.0; unknown: -0.3) and the symbol can never be traded again.

Outputs
-------
DataFrame indexed by fill date with gross_ret, net_ret, cost components, turnover, gross/net exposure, and the
realized weights.  All returns are fractions of capital (NAV is held constant = capital; no compounding of
leverage inside a day).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from statarb.execution.costs import CostParams, borrow_cost, commission, impact_cost, regulatory_fees, spread_cost


@dataclass
class EngineInputs:
    target_weights: pd.DataFrame  # decided at decision time of index date t
    fill_price: pd.DataFrame  # price at which orders on date t fill (already lag-aligned: fill_price.loc[t] is f_t)
    fill_volume: pd.DataFrame  # volume of the fill bar (0 or NaN => no fill)
    lag: int = 0  # 0 for MOC (fill same day close), 1 for MOO (fill next open)
    half_spread: pd.DataFrame | None = None  # proportional half spread known at t (for continuous fills)
    sigma_daily: pd.DataFrame | None = None
    adv_shares: pd.DataFrame | None = None  # average daily volume in shares for participation
    delist: dict | None = None  # symbol -> (Timestamp, return)


def run_backtest(inp: EngineInputs, capital: float, costs: CostParams) -> pd.DataFrame:
    W = inp.target_weights.sort_index()
    dates = W.index
    syms = list(W.columns)
    P = inp.fill_price.reindex(index=dates, columns=syms)
    V = inp.fill_volume.reindex(index=dates, columns=syms)
    HS = inp.half_spread.reindex(index=dates, columns=syms) if inp.half_spread is not None else None
    SIG = inp.sigma_daily.reindex(index=dates, columns=syms) if inp.sigma_daily is not None else None
    ADV = inp.adv_shares.reindex(index=dates, columns=syms) if inp.adv_shares is not None else None
    delist = inp.delist or {}
    delist_idx = {}
    for s, (d, r) in delist.items():
        if s in syms:
            pos = dates.searchsorted(pd.Timestamp(d))
            delist_idx[syms.index(s)] = (pos, float(r))

    Wv = W.to_numpy(dtype=float)
    Pv = P.to_numpy(dtype=float)
    Vv = V.to_numpy(dtype=float)
    T, N = Wv.shape
    held = np.zeros(N)  # dollar weights held after the fill on day i (fraction of capital)
    shares = np.zeros(N)
    dead = np.zeros(N, dtype=bool)
    rows = []
    for i in range(T):
        # fill index for orders decided on day i
        fi = i + inp.lag
        # ---- mark-to-market from previous fill to this fill (positions held from fill fi-1 to fi) ----
        gross_pnl = 0.0
        if fi < T and fi - 1 >= 0:
            p_prev = Pv[fi - 1]
            p_now = Pv[fi]
            ret = np.where(np.isfinite(p_prev) & np.isfinite(p_now) & (p_prev > 0), p_now / p_prev - 1.0, 0.0)
            # delisting: force close at the delisting return on the delisting date
            for j, (pos, r) in delist_idx.items():
                if pos == fi and not dead[j]:
                    ret[j] = r
            gross_pnl = float(np.nansum(held * ret))
            held = held * (1.0 + ret)  # drift
            for j, (pos, r) in delist_idx.items():
                if pos == fi and not dead[j]:
                    held[j] = 0.0
                    shares[j] = 0.0
                    dead[j] = True
        # ---- execute new target weights at fill fi ----
        tgt = np.nan_to_num(Wv[i], nan=0.0).copy()
        tgt[dead] = 0.0
        if fi >= T:
            rows.append(_row(dates[i], gross_pnl, 0, 0, 0, 0, 0, 0.0, held))
            continue
        price = Pv[fi]
        vol = Vv[fi]
        can_fill = np.isfinite(price) & (price > 0) & np.isfinite(vol) & (vol > 0) & ~dead
        new_held = np.where(can_fill, tgt, held)
        trade_w = new_held - held
        trade_notional = trade_w * capital
        trade_shares = np.where(can_fill & (price > 0), trade_notional / np.where(price > 0, price, np.nan), 0.0)
        trade_shares = np.nan_to_num(trade_shares, nan=0.0)
        turnover = float(np.abs(trade_w).sum())
        c_comm = commission(trade_shares, trade_notional, costs).sum()
        c_fees = regulatory_fees(trade_shares, trade_notional, costs).sum()
        hs = HS.to_numpy(dtype=float)[i] if HS is not None else np.zeros(N)
        c_spread = spread_cost(trade_notional, hs, costs).sum()
        if ADV is not None and SIG is not None:
            adv = np.nan_to_num(ADV.to_numpy(dtype=float)[fi], nan=np.inf)
            part = np.abs(trade_shares) / np.where(adv > 0, adv, np.inf)
            c_imp = impact_cost(trade_notional, part, SIG.to_numpy(dtype=float)[i], costs).sum()
        else:
            c_imp = 0.0
        held = new_held
        shares = np.where(can_fill, np.nan_to_num(held * capital / np.where(price > 0, price, np.nan)), shares)
        c_borrow = borrow_cost(held * capital, costs).sum()
        total_cost = (c_comm + c_fees + c_spread + c_imp + c_borrow) / capital
        rows.append(_row(dates[fi], gross_pnl, c_comm / capital, c_fees / capital, c_spread / capital,
                         c_imp / capital, c_borrow / capital, turnover, held))
    out = pd.DataFrame(rows).set_index("date")
    out["net_ret"] = out["gross_ret"] - out[["commission", "fees", "spread", "impact", "borrow"]].sum(axis=1)
    return out


def _row(date, gross, comm, fees, spread, imp, borrow, turnover, held):
    return {
        "date": date,
        "gross_ret": gross,
        "commission": comm,
        "fees": fees,
        "spread": spread,
        "impact": imp,
        "borrow": borrow,
        "turnover": turnover,
        "gross_exposure": float(np.abs(held).sum()),
        "net_exposure": float(held.sum()),
    }
