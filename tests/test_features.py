import numpy as np
import pandas as pd
import statsmodels.api as sm

from statarb.features.residual import rolling_ols_residuals, rolling_zscore
from statarb.features.spreads import corwin_schultz, rolling_spread


def test_rolling_residual_matches_statsmodels_last_window():
    rng = np.random.default_rng(0)
    T = 200
    dates = pd.bdate_range("2018-01-01", periods=T)
    f = pd.DataFrame(rng.normal(0, 0.01, (T, 2)), index=dates, columns=["MKT", "SEC"])
    eps = rng.normal(0, 0.01, (T, 3))
    r = pd.DataFrame(0.8 * f["MKT"].to_numpy()[:, None] + 0.5 * f["SEC"].to_numpy()[:, None] + eps,
                     index=dates, columns=["A", "B", "C"])
    res = rolling_ols_residuals(r, f, window=60)
    t = T - 1
    X = sm.add_constant(f.iloc[t - 59 : t + 1].to_numpy())
    fit = sm.OLS(r["B"].iloc[t - 59 : t + 1].to_numpy(), X).fit()
    assert np.isclose(res["B"].iloc[t], fit.resid[-1], atol=1e-10)
    assert res.iloc[:19].isna().all().all()  # needs min_obs


def test_residual_uses_no_future_data():
    rng = np.random.default_rng(1)
    T = 150
    dates = pd.bdate_range("2018-01-01", periods=T)
    f = pd.DataFrame(rng.normal(0, 0.01, (T, 1)), index=dates, columns=["MKT"])
    r = pd.DataFrame(rng.normal(0, 0.01, (T, 2)), index=dates, columns=["A", "B"])
    a = rolling_ols_residuals(r, f, window=40)
    r2 = r.copy()
    r2.iloc[100:] += 0.05
    b = rolling_ols_residuals(r2, f, window=40)
    pd.testing.assert_frame_equal(a.iloc[:100], b.iloc[:100])


def test_zscore_and_missing():
    x = pd.DataFrame({"A": np.arange(100, dtype=float)})
    z = rolling_zscore(x, window=20)
    assert z["A"].iloc[:19].isna().all()
    assert np.isfinite(z["A"].iloc[50])


def test_corwin_schultz_zero_when_no_range():
    p = pd.DataFrame({"A": [100.0] * 10})
    s = corwin_schultz(p, p)
    assert np.allclose(s.iloc[1:], 0.0)


def test_spread_estimators_recover_simulated_spread():
    rng = np.random.default_rng(2)
    T, n_intraday = 4000, 200
    true_spread = 0.004
    mid = 100.0
    close, high, low = [], [], []
    for _ in range(T):
        path = mid * np.exp(np.cumsum(rng.normal(0, 0.012 / np.sqrt(n_intraday), n_intraday)))
        mid = path[-1]
        high.append(path.max() * (1 + true_spread / 2))
        low.append(path.min() * (1 - true_spread / 2))
        close.append(path[-1] * (1 + rng.choice([-1, 1]) * true_spread / 2))
    df = lambda v: pd.DataFrame({"A": v})
    s = rolling_spread(df(close), df(high), df(low), window=T, cap=0.05)["A"].iloc[-1]
    assert 0.5 * true_spread < s < 2.0 * true_spread
