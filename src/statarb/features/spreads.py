"""Range-based bid-ask spread estimators from daily OHLC.

Corwin & Schultz (2012, JF): uses two consecutive days' highs and lows.
Abdi & Ranaldo (2017, RFS): uses close and the mid-range of high/low on consecutive days.
Both return *proportional full spreads* (e.g. 0.001 = 10 bp).  Formulas verified at M3 against the papers'
equations (Corwin-Schultz eq. 14-18; Abdi-Ranaldo eq. 9). Negative daily estimates are set to zero before
averaging (pre-registered rule, configs/costs.yaml).
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def corwin_schultz(high: pd.DataFrame, low: pd.DataFrame) -> pd.DataFrame:
    """Daily CS spread estimate S_t from days (t-1, t). Requires positive prices."""
    h = np.log(high)
    lo = np.log(low)
    beta = (h - lo) ** 2 + (h - lo).shift(1) ** 2
    h2 = np.log(np.maximum(high, high.shift(1)))
    l2 = np.log(np.minimum(low, low.shift(1)))
    gamma = (h2 - l2) ** 2
    c = 3 - 2 * np.sqrt(2)
    alpha = (np.sqrt(2 * beta) - np.sqrt(beta)) / c - np.sqrt(gamma / c)
    s = 2 * (np.exp(alpha) - 1) / (1 + np.exp(alpha))
    return s


def abdi_ranaldo(close: pd.DataFrame, high: pd.DataFrame, low: pd.DataFrame) -> pd.DataFrame:
    """Daily AR squared-spread term 4*(c_t - eta_t)*(c_t - eta_{t+1}); the spread is sqrt(mean(.)) over a window.

    Note eta_{t+1} uses day t+1's high/low, so the daily term for t is only known at t+1; callers must shift by one
    day before using it in a trailing window (handled in rolling_spread())."""
    c = np.log(close)
    eta = (np.log(high) + np.log(low)) / 2
    term = 4 * (c - eta) * (c - eta.shift(-1))
    return term


def rolling_spread(
    close: pd.DataFrame, high: pd.DataFrame, low: pd.DataFrame, window: int = 21, cap: float = 0.01
) -> pd.DataFrame:
    """Trailing-window estimate known at t (no future data): max(CS mean, AR sqrt(mean)), clipped to [0, cap]."""
    cs = corwin_schultz(high, low).clip(lower=0.0)
    cs_m = cs.rolling(window, min_periods=max(5, window // 2)).mean()
    ar_term = abdi_ranaldo(close, high, low).shift(1)  # term for day t-1 becomes known at t
    ar_m = ar_term.rolling(window, min_periods=max(5, window // 2)).mean().clip(lower=0.0)
    ar_s = np.sqrt(ar_m)
    s = pd.concat([cs_m, ar_s]).groupby(level=0).max() if False else np.maximum(cs_m, ar_s)
    return s.clip(upper=cap)
