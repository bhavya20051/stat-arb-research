"""Rolling factor residualization and z-scores using ONLY trailing data.

residual_returns(): for each date t and symbol, regress the symbol's returns on factor returns over the
trailing `window` days ending at t (inclusive) and report the residual AT t.  The betas used at t are estimated
on [t-window+1, t]; because the residual at t is the in-sample residual of that window there is no look-ahead
(only data through t is used).  The z-score at t uses residual history through t.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def rolling_ols_residuals(
    returns: pd.DataFrame, factors: pd.DataFrame, window: int = 120, min_obs: int | None = None
) -> pd.DataFrame:
    """Residual of each column of `returns` on `factors` (+intercept) using a trailing window.

    Returns a DataFrame aligned to `returns` with NaN where fewer than `min_obs` observations are available.
    Implementation: per date t, solve OLS on the window for all symbols at once (factors shared across symbols).
    """
    if min_obs is None:
        min_obs = max(20, window // 2)
    idx = returns.index
    F = factors.reindex(idx).to_numpy(dtype=float)
    R = returns.to_numpy(dtype=float)
    T, N = R.shape
    K = F.shape[1]
    out = np.full((T, N), np.nan)
    X_full = np.column_stack([np.ones(T), F])
    for t in range(T):
        lo = max(0, t - window + 1)
        X = X_full[lo : t + 1]
        Y = R[lo : t + 1]
        ok_rows = ~np.isnan(X).any(axis=1)
        X = X[ok_rows]
        Y = Y[ok_rows]
        if X.shape[0] < min_obs:
            continue
        # symbols with enough non-missing returns in the window
        Ymask = ~np.isnan(Y)
        good = Ymask.sum(axis=0) >= min_obs
        if not good.any():
            continue
        Yg = np.where(Ymask[:, good], Y[:, good], 0.0)
        # OLS with missing handled per symbol via masked normal equations
        XtX = X.T @ X
        try:
            XtX_inv = np.linalg.pinv(XtX)
        except np.linalg.LinAlgError:
            continue
        # for symbols with no missing values in window use shared solve; otherwise loop
        full = Ymask[:, good].all(axis=0)
        cols = np.where(good)[0]
        if full.any():
            B = XtX_inv @ X.T @ Yg[:, full]
            res_t = Yg[-1, full] - X[-1] @ B
            out[t, cols[full]] = res_t
        for j in np.where(~full)[0]:
            m = Ymask[:, good][:, j]
            Xj = X[m]
            yj = Y[:, good][:, j][m]
            if Xj.shape[0] < min_obs or not Ymask[-1, good][j]:
                continue
            bj = np.linalg.lstsq(Xj, yj, rcond=None)[0]
            out[t, cols[j]] = Y[-1, good][j] - X[-1] @ bj
    return pd.DataFrame(out, index=idx, columns=returns.columns)


def rolling_zscore(x: pd.DataFrame, window: int = 60, min_obs: int = 20) -> pd.DataFrame:
    """z-score of x_t relative to the trailing window's mean/std (window includes t; no future data)."""
    mu = x.rolling(window, min_periods=min_obs).mean()
    sd = x.rolling(window, min_periods=min_obs).std(ddof=1)
    return (x - mu) / sd.replace(0.0, np.nan)


def trailing_sum(x: pd.DataFrame, k: int) -> pd.DataFrame:
    return x.rolling(k, min_periods=k).sum()
