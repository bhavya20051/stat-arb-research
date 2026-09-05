"""Residual-reversal signal: standardized trailing residual return, ranked cross-sectionally, with ex-ante masks."""

from __future__ import annotations

import numpy as np
import pandas as pd

from statarb.features.residual import rolling_zscore, trailing_sum


def reversal_score(residuals: pd.DataFrame, lookback: int, zscore_window: int = 60) -> pd.DataFrame:
    """score_t = -(sum of residuals over the last `lookback` days) standardized by trailing residual vol.

    Positive score = oversold (buy candidate); negative = overbought (short candidate)."""
    s = trailing_sum(residuals, lookback)
    vol = residuals.rolling(zscore_window, min_periods=max(20, zscore_window // 3)).std(ddof=1) * np.sqrt(lookback)
    return -(s / vol.replace(0.0, np.nan))


def abnormal_turnover(volume: pd.DataFrame, window: int = 60) -> pd.DataFrame:
    """volume_t / trailing mean volume over [t-window, t-1] (excludes t's own volume from the mean)."""
    base = volume.shift(1).rolling(window, min_periods=max(20, window // 3)).mean()
    return volume / base.replace(0.0, np.nan)


def cross_sectional_rank(score: pd.DataFrame, mask: pd.DataFrame | None = None) -> pd.DataFrame:
    """Rank in [0,1] per date among eligible names (mask True). Ineligible names get NaN."""
    x = score.copy()
    if mask is not None:
        x = x.where(mask)
    return x.rank(axis=1, pct=True)


def decile_weights(score: pd.DataFrame, mask: pd.DataFrame | None = None, n_deciles: int = 10) -> pd.DataFrame:
    """+1/n_long for top decile (buy), -1/n_short for bottom decile, 0 otherwise; dollar-neutral by construction."""
    rk = cross_sectional_rank(score, mask)
    long = rk >= 1 - 1 / n_deciles
    short = rk <= 1 / n_deciles
    nl = long.sum(axis=1).replace(0, np.nan)
    ns = short.sum(axis=1).replace(0, np.nan)
    w = long.astype(float).div(nl, axis=0).fillna(0.0) - short.astype(float).div(ns, axis=0).fillna(0.0)
    return w


def jump_exclusion_mask(residuals: pd.DataFrame, sigma_window: int = 60, n_sigma: float = 3.0, days: int = 3) -> pd.DataFrame:
    """True where the name is eligible: no |residual| >= n_sigma * trailing vol in the last `days` days (through t).

    Uses only data through t (the vol at t-1 and the residuals at t-days+1..t)."""
    vol = residuals.rolling(sigma_window, min_periods=20).std(ddof=1).shift(1)
    jump = (residuals.abs() >= n_sigma * vol)
    recent = jump.rolling(days, min_periods=1).max().astype(bool)
    return ~recent
