"""Performance statistics with uncertainty.

Sharpe ratios inside every formula are NON-annualised (per-period) unless the function name says annualised.
References (formulas verified against the papers before use — see 03_LITERATURE_REVIEW.md):
  * Lo (2002): SE of the Sharpe ratio, iid and autocorrelation-adjusted.
  * Bailey & Lopez de Prado (2012): Probabilistic Sharpe Ratio (PSR).
  * Bailey & Lopez de Prado (2014): Deflated Sharpe Ratio (DSR) threshold SR*.
  * Politis & Romano (1994): stationary bootstrap.
  * Bailey, Borwein, Lopez de Prado & Zhu (2017): CSCV probability of backtest overfitting (PBO).
"""

from __future__ import annotations

from itertools import combinations

import numpy as np
import pandas as pd
from scipy import stats

EULER_GAMMA = 0.5772156649015329


def sharpe(r: np.ndarray) -> float:
    r = np.asarray(r, dtype=float)
    r = r[np.isfinite(r)]
    s = r.std(ddof=1)
    return float(r.mean() / s) if s > 0 else float("nan")


def annualise_sharpe(sr: float, periods: int = 252) -> float:
    return sr * np.sqrt(periods)


def sharpe_se_iid(sr: float, n: int) -> float:
    """Lo (2002) eq. for iid returns: SE(SR) = sqrt((1 + SR^2/2) / n)."""
    return float(np.sqrt((1.0 + 0.5 * sr**2) / n))


def sharpe_se_autocorr(r: np.ndarray, q: int | None = None) -> float:
    """Lo (2002) autocorrelation-adjusted SE via the delta method with a Newey-West style variance.

    Uses the variance of the per-period mean under q-lag serial correlation (Bartlett weights) and the
    iid correction for the volatility term; q defaults to floor(4 (n/100)^(2/9))."""
    r = np.asarray(r, dtype=float)
    r = r[np.isfinite(r)]
    n = len(r)
    if q is None:
        q = int(np.floor(4 * (n / 100.0) ** (2.0 / 9.0)))
    mu = r.mean()
    s = r.std(ddof=1)
    sr = mu / s
    rho = [1.0] + [np.corrcoef(r[:-k], r[k:])[0, 1] for k in range(1, q + 1)]
    lr_factor = 1.0 + 2.0 * sum((1 - k / (q + 1)) * rho[k] for k in range(1, q + 1))
    lr_factor = max(lr_factor, 1e-8)
    return float(np.sqrt((lr_factor + 0.5 * sr**2) / n))


def psr(r: np.ndarray, sr_benchmark: float = 0.0) -> float:
    """Probabilistic Sharpe Ratio (Bailey & Lopez de Prado 2012):
    PSR = Phi[ (SR - SR*) sqrt(n-1) / sqrt(1 - g3 SR + (g4 - 1)/4 SR^2) ], SR per-period, g3 skew, g4 kurtosis."""
    r = np.asarray(r, dtype=float)
    r = r[np.isfinite(r)]
    n = len(r)
    sr = sharpe(r)
    g3 = stats.skew(r, bias=False)
    g4 = stats.kurtosis(r, fisher=False, bias=False)
    denom = np.sqrt(max(1.0 - g3 * sr + (g4 - 1.0) / 4.0 * sr**2, 1e-12))
    z = (sr - sr_benchmark) * np.sqrt(n - 1) / denom
    return float(stats.norm.cdf(z))


def dsr_threshold(var_sr: float, n_trials: int) -> float:
    """Expected maximum Sharpe among N independent trials with Sharpe variance var_sr (Bailey & LdP 2014):
    SR* = sqrt(V[SR]) * ((1 - gamma) Z^-1(1 - 1/N) + gamma Z^-1(1 - 1/(N e)))."""
    if n_trials <= 1:
        return 0.0
    z1 = stats.norm.ppf(1.0 - 1.0 / n_trials)
    z2 = stats.norm.ppf(1.0 - 1.0 / (n_trials * np.e))
    return float(np.sqrt(var_sr) * ((1 - EULER_GAMMA) * z1 + EULER_GAMMA * z2))


def dsr(r: np.ndarray, trial_sharpes: np.ndarray) -> float:
    """Deflated Sharpe Ratio: PSR evaluated at SR* computed from the variance of per-period Sharpe across trials."""
    trial_sharpes = np.asarray(trial_sharpes, dtype=float)
    var_sr = float(np.var(trial_sharpes, ddof=1)) if len(trial_sharpes) > 1 else 0.0
    return psr(r, dsr_threshold(var_sr, len(trial_sharpes)))


def stationary_bootstrap_indices(n: int, block_mean: float, rng: np.random.Generator) -> np.ndarray:
    """Politis-Romano stationary bootstrap: geometric block lengths with mean block_mean, circular wrap."""
    p = 1.0 / block_mean
    idx = np.empty(n, dtype=int)
    i = 0
    while i < n:
        start = rng.integers(0, n)
        L = rng.geometric(p)
        L = min(L, n - i)
        idx[i : i + L] = (start + np.arange(L)) % n
        i += L
    return idx


def bootstrap_sharpe_ci(
    r: np.ndarray, n_boot: int = 2000, block_mean: float = 10.0, alpha: float = 0.05, seed: int = 0
) -> tuple[float, float, np.ndarray]:
    r = np.asarray(r, dtype=float)
    r = r[np.isfinite(r)]
    rng = np.random.default_rng(seed)
    srs = np.empty(n_boot)
    for b in range(n_boot):
        idx = stationary_bootstrap_indices(len(r), block_mean, rng)
        srs[b] = sharpe(r[idx])
    lo, hi = np.percentile(srs, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return float(lo), float(hi), srs


def pbo_cscv(M: np.ndarray, n_blocks: int = 16, metric=sharpe) -> dict:
    """Probability of Backtest Overfitting via CSCV (Bailey et al. 2017).

    M: (T x K) matrix of per-period returns for K candidate configurations (candidates only, no placebos).
    Splits T into n_blocks contiguous blocks; for every combination of n_blocks/2 blocks as train (rest test):
    pick the best in-sample config, compute its out-of-sample rank; PBO = P(OOS rank <= median), i.e. the
    relative rank w = rank/(K+1) gives logit lambda = log(w/(1-w)); PBO = fraction of lambda <= 0."""
    T, K = M.shape
    blocks = np.array_split(np.arange(T), n_blocks)
    half = n_blocks // 2
    lambdas = []
    oos_best = []
    for train_blocks in combinations(range(n_blocks), half):
        tr = np.concatenate([blocks[b] for b in train_blocks])
        te = np.concatenate([blocks[b] for b in range(n_blocks) if b not in train_blocks])
        is_perf = np.array([metric(M[tr, k]) for k in range(K)])
        oos_perf = np.array([metric(M[te, k]) for k in range(K)])
        best = int(np.nanargmax(is_perf))
        rank = stats.rankdata(oos_perf)[best]  # 1..K, higher is better
        w = rank / (K + 1.0)
        lambdas.append(np.log(w / (1.0 - w)))
        oos_best.append(oos_perf[best])
    lambdas = np.array(lambdas)
    return {"pbo": float(np.mean(lambdas <= 0)), "lambda": lambdas, "oos_best": np.array(oos_best), "n_combinations": len(lambdas)}


def summary_table(daily: pd.Series, periods: int = 252) -> dict:
    r = daily.dropna().to_numpy()
    n = len(r)
    sr = sharpe(r)
    cum = np.cumprod(1 + r)
    peak = np.maximum.accumulate(cum)
    dd = cum / peak - 1
    ann_ret = cum[-1] ** (periods / n) - 1 if n > 0 else np.nan
    ann_vol = r.std(ddof=1) * np.sqrt(periods)
    downside = r[r < 0].std(ddof=1) * np.sqrt(periods) if (r < 0).any() else np.nan
    gains = r[r > 0].sum()
    losses = -r[r < 0].sum()
    return {
        "n_days": n,
        "total_return": float(cum[-1] - 1),
        "ann_return": float(ann_ret),
        "ann_vol": float(ann_vol),
        "sharpe_ann": float(annualise_sharpe(sr, periods)),
        "sharpe_se_iid_ann": float(sharpe_se_iid(sr, n) * np.sqrt(periods)),
        "sharpe_se_autocorr_ann": float(sharpe_se_autocorr(r) * np.sqrt(periods)),
        "sortino_ann": float(r.mean() * periods / downside) if downside and downside > 0 else np.nan,
        "max_drawdown": float(dd.min()),
        "calmar": float(ann_ret / -dd.min()) if dd.min() < 0 else np.nan,
        "hit_rate": float((r > 0).mean()),
        "profit_factor": float(gains / losses) if losses > 0 else np.nan,
        "skew": float(stats.skew(r, bias=False)),
        "kurtosis": float(stats.kurtosis(r, fisher=False, bias=False)),
        "psr_vs_zero": float(psr(r, 0.0)),
    }
