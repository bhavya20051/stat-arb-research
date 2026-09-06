"""Portfolio construction: dollar neutrality, sector neutralization, beta hedge via SPY, position caps,
volatility targeting, no-trade band.  Every quantity used at t is computed from data through t-1 (betas, vols)
or the signal at t; nothing later.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def neutralize_sector(w: pd.DataFrame, sector: pd.DataFrame) -> pd.DataFrame:
    """Remove the mean weight within each sector on each date (sector: DataFrame of sector labels, same shape)."""
    out = w.copy()
    for d in w.index:
        row = w.loc[d]
        sec = sector.loc[d] if d in sector.index else None
        if sec is None:
            continue
        active = row != 0
        if not active.any():
            continue
        means = row[active].groupby(sec[active]).transform("mean")
        out.loc[d, active] = row[active] - means
    return out


def dollar_neutralize(w: pd.DataFrame) -> pd.DataFrame:
    """Scale longs and shorts so that sum(longs) = -sum(shorts) = 0.5 * gross target of 1 (gross = 1.0)."""
    pos = w.clip(lower=0)
    neg = w.clip(upper=0)
    ps = pos.sum(axis=1).replace(0, np.nan)
    ns = -neg.sum(axis=1).replace(0, np.nan)
    return (pos.div(ps, axis=0).fillna(0) * 0.5 + neg.div(ns, axis=0).fillna(0) * 0.5)


def cap_weights(w: pd.DataFrame, max_abs: float) -> pd.DataFrame:
    return w.clip(lower=-max_abs, upper=max_abs)


def inverse_vol_scale(w: pd.DataFrame, vol: pd.DataFrame) -> pd.DataFrame:
    """Multiply weights by 1/vol (vol known at t-1) and renormalize each side to its previous gross."""
    s = w / vol.replace(0, np.nan)
    s = s.fillna(0)
    return dollar_neutralize(s) * w.abs().sum(axis=1).to_numpy()[:, None]


def beta_hedge(w: pd.DataFrame, beta: pd.DataFrame, hedge_symbol: str = "SPY") -> pd.DataFrame:
    """Add a hedge position in `hedge_symbol` = -sum(w * beta) so the ex-ante portfolio beta is zero."""
    port_beta = (w * beta.reindex_like(w).fillna(0)).sum(axis=1)
    out = w.copy()
    out[hedge_symbol] = out.get(hedge_symbol, 0.0) - port_beta
    return out


def vol_target(w: pd.DataFrame, port_vol_estimate: pd.Series, target_annual: float = 0.10, max_lever: float = 2.0) -> pd.DataFrame:
    """Scale the whole book by target / trailing portfolio vol (annualised, estimated through t-1), capped."""
    scale = (target_annual / port_vol_estimate.replace(0, np.nan)).clip(upper=max_lever).fillna(1.0)
    return w.mul(scale, axis=0)


def apply_no_trade_band(target: pd.DataFrame, band: float) -> pd.DataFrame:
    """Suppress weight changes smaller than `band` versus the previously *targeted* weight (path-dependent)."""
    out = target.copy()
    prev = pd.Series(0.0, index=target.columns)
    for d in target.index:
        row = target.loc[d]
        small = (row - prev).abs() < band
        row = row.where(~small, prev)
        out.loc[d] = row
        prev = row
    return out


def enforce_limits(w: pd.DataFrame, gross_max: float = 2.0, net_abs_max: float = 0.05) -> pd.DataFrame:
    gross = w.abs().sum(axis=1)
    scale = (gross_max / gross.replace(0, np.nan)).clip(upper=1.0).fillna(1.0)
    w = w.mul(scale, axis=0)
    net = w.sum(axis=1)
    # push net back inside the band by shifting proportionally on the larger side
    excess = net.clip(lower=-net_abs_max, upper=net_abs_max)
    adj = net - excess
    out = w.copy()
    for d in w.index[adj.abs() > 1e-12]:
        row = out.loc[d]
        if adj[d] > 0:
            pos = row.clip(lower=0)
            out.loc[d] = row - pos / pos.sum() * adj[d]
        else:
            neg = row.clip(upper=0)
            out.loc[d] = row - neg / neg.sum() * adj[d]
    return out


def hysteresis_weights(score: pd.DataFrame, enter_pct: float = 0.2, exit_pct: float = 0.4, max_hold: int = 5) -> pd.DataFrame:
    """Rank-space hysteresis: open a long when the score's cross-sectional rank is in the top `enter_pct`
    (short: bottom), keep it while the rank stays within the top/bottom `exit_pct`, force exit after `max_hold`
    days or when the score is missing. Equal weights per side, dollar-neutral, gross = 1 (0.5 per side).
    Uses only the score at t (ex-ante); state is path-dependent."""
    rk = score.rank(axis=1, pct=True)
    T, N = rk.shape
    side = np.zeros(N)          # +1 long, -1 short, 0 flat
    age = np.zeros(N, dtype=int)
    out = np.zeros((T, N))
    R = rk.to_numpy()
    for t in range(T):
        r = R[t]
        valid = np.isfinite(r)
        # exits
        exit_long = (side > 0) & (~valid | (r < 1 - exit_pct) | (age >= max_hold))
        exit_short = (side < 0) & (~valid | (r > exit_pct) | (age >= max_hold))
        side[exit_long | exit_short] = 0
        age[exit_long | exit_short] = 0
        # entries
        side[(side == 0) & valid & (r >= 1 - enter_pct)] = 1
        side[(side == 0) & valid & (r <= enter_pct)] = -1
        age[side != 0] += 1
        nl = (side > 0).sum(); ns = (side < 0).sum()
        if nl:
            out[t, side > 0] = 0.5 / nl
        if ns:
            out[t, side < 0] = -0.5 / ns
    return pd.DataFrame(out, index=score.index, columns=score.columns)


def event_weights(score: pd.DataFrame, entry_z: float = 2.0, holding: int = 3, per_side_gross: float = 0.5,
                  max_name: float = 0.02, ref_window: int = 60) -> pd.DataFrame:
    """Event construction: on day t, every eligible name with score >= entry_z is bought and every name with
    score <= -entry_z is shorted; each day's cohort receives per_side_gross/holding per side, split equally among that
    day's entrants, and is held for exactly `holding` days with NO rebalancing (weights drift with price in the
    engine).  Cohorts overlap, so the book holds up to `holding` cohorts per side.  Ex-ante: uses only score_t."""
    S = score.to_numpy()
    T, N = S.shape
    out = np.zeros((T, N))
    # fixed weight per position: budget per side per cohort divided by the EX-ANTE expected number of entrants
    # (trailing ref_window-day mean of daily entry counts through t-1), capped at max_name.
    n_long = np.array([(np.isfinite(r) & (r >= entry_z)).sum() for r in S], dtype=float)
    n_short = np.array([(np.isfinite(r) & (r <= -entry_z)).sum() for r in S], dtype=float)
    exp_long = pd.Series(n_long).rolling(ref_window, min_periods=min(20, ref_window)).mean().shift(1).to_numpy()
    exp_short = pd.Series(n_short).rolling(ref_window, min_periods=min(20, ref_window)).mean().shift(1).to_numpy()
    for t in range(T):
        row = S[t]
        longs = np.isfinite(row) & (row >= entry_z)
        shorts = np.isfinite(row) & (row <= -entry_z)
        nl, ns = longs.sum(), shorts.sum()
        cohort = np.zeros(N)
        wl = min(max_name, per_side_gross / holding / max(exp_long[t], 1.0)) if np.isfinite(exp_long[t]) else 0.0
        ws = min(max_name, per_side_gross / holding / max(exp_short[t], 1.0)) if np.isfinite(exp_short[t]) else 0.0
        if nl:
            cohort[longs] = wl
        if ns:
            cohort[shorts] = -ws
        for k in range(holding):
            if t + k < T:
                out[t + k] += cohort
    return pd.DataFrame(out, index=score.index, columns=score.columns)
