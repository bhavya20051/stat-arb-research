"""Decision-time (15:45 ET) prices from 15-minute bars and the closing-auction-model signal.

The 15:30 bar (label = bar start) closes at 15:45; its close is the last price known at the 15:40 decision
routine's completion. The MOC signal on day t combines:
  * partial-day residual return r_partial(t) = (P15:45(t) / adj_close(t-1) - 1) - beta_{t-1} · f_partial(t),
    with betas from the daily rolling OLS through t-1 and f_partial the same partial-day return of SPY/sector;
  * the trailing (lookback-1) daily residuals through t-1;
standardised by the daily residual vol through t-1.  Nothing after 15:45 on day t is used.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from statarb.data.load import PROC


def decision_price_panel(symbols: list[str], bar_start: str = "15:30", value: str = "close") -> pd.DataFrame:
    """Wide panel (dates x symbols) of the `value` of the 15-min bar starting at `bar_start`."""
    d = PROC / "intraday_15min"
    cols = {}
    for s in symbols:
        f = d / f"{s}.parquet"
        if not f.exists():
            continue
        df = pd.read_parquet(f, columns=["ts", value])
        ts = pd.to_datetime(df["ts"])
        sel = df[ts.dt.strftime("%H:%M") == bar_start]
        ser = pd.Series(sel[value].to_numpy(), index=pd.to_datetime(sel["ts"]).dt.normalize())
        cols[s] = ser[~ser.index.duplicated()]
    return pd.DataFrame(cols).sort_index()


def auction_volume_proxy(symbols: list[str]) -> pd.DataFrame:
    """Volume of the last 15-min bar (15:45-16:00, which includes the closing print) as the auction-volume proxy.
    UNVERIFIED against official auction volume; used only for the participation-cost term."""
    return decision_price_panel(symbols, bar_start="15:45", value="volume")


def rolling_betas(returns: pd.DataFrame, factors: pd.DataFrame, window: int = 120, min_obs: int = 60) -> dict[str, pd.DataFrame]:
    """Rolling OLS betas (dates x symbols) for each factor column, using data through t (apply .shift(1) for t-1)."""
    idx = returns.index
    F = factors.reindex(idx).fillna(0.0).to_numpy(float)
    R = returns.to_numpy(float)
    T, N = R.shape
    K = F.shape[1]
    X_full = np.column_stack([np.ones(T), F])
    out = {k: np.full((T, N), np.nan) for k in factors.columns}
    for t in range(window - 1, T):
        lo = t - window + 1
        X = X_full[lo : t + 1]
        Y = R[lo : t + 1]
        ok = ~np.isnan(Y).any(axis=0)
        if ok.sum() == 0:
            continue
        B = np.linalg.pinv(X.T @ X) @ X.T @ Y[:, ok]
        for j, k in enumerate(factors.columns):
            out[k][t, ok] = B[j + 1]
    return {k: pd.DataFrame(v, index=idx, columns=returns.columns) for k, v in out.items()}


def moc_score(p1545: pd.DataFrame, adj_close: pd.DataFrame, factor_p1545: pd.DataFrame, factor_close: pd.DataFrame,
              betas_lag: dict[str, pd.DataFrame], sector_of: dict[str, str], resid_daily: pd.DataFrame,
              resid_vol_lag: pd.DataFrame, lookback: int = 1) -> pd.DataFrame:
    """Reversal score at 15:45 on day t (positive = oversold)."""
    partial = p1545 / adj_close.shift(1).reindex_like(p1545) - 1.0
    fpart = factor_p1545 / factor_close.shift(1).reindex_like(factor_p1545) - 1.0
    resid_partial = partial.copy()
    for s in partial.columns:
        b_m = betas_lag["SPY"][s] if s in betas_lag["SPY"] else 0.0
        resid_partial[s] = partial[s] - b_m * fpart["SPY"]
        etf = sector_of.get(s)
        if etf and etf in betas_lag and etf in fpart:
            resid_partial[s] = resid_partial[s] - betas_lag[etf][s] * fpart[etf]
    total = resid_partial
    if lookback > 1:
        total = total + resid_daily.shift(1).rolling(lookback - 1, min_periods=lookback - 1).sum().reindex_like(total)
    vol = resid_vol_lag.reindex_like(total) * np.sqrt(lookback)
    return -(total / vol.replace(0.0, np.nan))
