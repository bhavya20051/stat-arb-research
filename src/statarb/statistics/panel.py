"""Cross-sectional inference: Fama-MacBeth with Newey-West errors, IC decay curves, decile spreads."""

from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm


def newey_west_tstat(x: np.ndarray, lags: int | None = None) -> tuple[float, float, float]:
    """Mean, NW standard error and t-stat of a time series of coefficients (HAC with Bartlett kernel)."""
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    if lags is None:
        lags = int(np.floor(4 * (n / 100.0) ** (2.0 / 9.0)))
    X = np.ones((n, 1))
    fit = sm.OLS(x, X).fit(cov_type="HAC", cov_kwds={"maxlags": lags})
    return float(fit.params[0]), float(fit.bse[0]), float(fit.tvalues[0])


def fama_macbeth(y: pd.DataFrame, xs: dict[str, pd.DataFrame], min_names: int = 30) -> pd.DataFrame:
    """Per-date cross-sectional OLS of y (T x N forward returns) on regressors (each T x N); returns the
    time series of slopes plus NW summary.  Dates with fewer than `min_names` complete observations are skipped."""
    names = list(xs)
    rows = []
    for d in y.index:
        parts = [y.loc[d]] + [xs[k].loc[d] for k in names]
        df = pd.concat(parts, axis=1)
        df.columns = ["y"] + names
        df = df.dropna()
        if len(df) < min_names:
            continue
        X = sm.add_constant(df[names].to_numpy())
        beta = np.linalg.lstsq(X, df["y"].to_numpy(), rcond=None)[0]
        rows.append([d] + list(beta))
    out = pd.DataFrame(rows, columns=["date", "const"] + names).set_index("date")
    summary = {}
    for k in ["const"] + names:
        m, se, t = newey_west_tstat(out[k].to_numpy())
        summary[k] = {"mean": m, "nw_se": se, "nw_t": t, "n_dates": len(out)}
    out.attrs["summary"] = summary
    return out


def forward_return(px: pd.DataFrame, h: int) -> pd.DataFrame:
    """Return from fill at t to fill at t+h (uses future prices by design: this is the LABEL, aligned at t)."""
    return px.shift(-h) / px - 1.0


def ic_decay(signal: pd.DataFrame, px: pd.DataFrame, horizons=range(1, 21), method: str = "spearman") -> pd.DataFrame:
    """Mean cross-sectional rank IC of signal_t with return t->t+h for each h, with NW t-stats."""
    rows = []
    for h in horizons:
        fr = forward_return(px, h)
        ics = signal.corrwith(fr, axis=1, method=method)
        m, se, t = newey_west_tstat(ics.dropna().to_numpy(), lags=h)
        rows.append({"horizon": h, "ic_mean": m, "ic_nw_t": t, "n": int(ics.notna().sum())})
    return pd.DataFrame(rows).set_index("horizon")


def decile_spread(signal: pd.DataFrame, px: pd.DataFrame, h: int, n: int = 10) -> pd.Series:
    """Equal-weight top-decile minus bottom-decile forward return (t -> t+h), per date (overlapping if h>1)."""
    fr = forward_return(px, h)
    rk = signal.rank(axis=1, pct=True)
    top = fr.where(rk >= 1 - 1 / n).mean(axis=1)
    bot = fr.where(rk <= 1 / n).mean(axis=1)
    return (top - bot).dropna()
