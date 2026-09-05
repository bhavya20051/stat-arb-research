import numpy as np
import pandas as pd

from statarb.statistics.panel import decile_spread, fama_macbeth, forward_return, ic_decay


def _panel(seed=0, T=300, N=60, beta=-0.05):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2019-01-01", periods=T)
    cols = [f"S{i}" for i in range(N)]
    sig = pd.DataFrame(rng.normal(size=(T, N)), index=dates, columns=cols)
    eps = rng.normal(0, 0.02, size=(T, N))
    ret = beta * 0.01 * sig.to_numpy() + eps  # next-day return depends on today's signal
    px = pd.DataFrame(100 * np.cumprod(1 + np.vstack([np.zeros((1, N)), ret[:-1]]), axis=0), index=dates, columns=cols)
    # ret[t] is the return from t to t+1 realised at t+1: px[t+1]/px[t]-1 = ret[t]
    px = pd.DataFrame(100 * np.cumprod(1 + np.vstack([np.zeros((1, N)), ret]), axis=0)[:T], index=dates, columns=cols)
    return sig, px, ret


def test_forward_return_alignment():
    px = pd.DataFrame({"A": [100.0, 110.0, 99.0]})
    fr = forward_return(px, 1)
    assert np.isclose(fr["A"].iloc[0], 0.10) and np.isnan(fr["A"].iloc[2])


def test_fama_macbeth_recovers_negative_slope():
    sig, px, ret = _panel(beta=-0.05)
    y = forward_return(px, 1)
    fm = fama_macbeth(y, {"sig": sig})
    s = fm.attrs["summary"]["sig"]
    assert s["mean"] < 0 and s["nw_t"] < -3


def test_ic_and_decile_spread_signs():
    sig, px, _ = _panel(beta=-0.05)
    ic = ic_decay(sig, px, horizons=[1, 2])
    assert ic.loc[1, "ic_mean"] < 0
    spread = decile_spread(sig, px, 1)
    assert spread.mean() < 0  # high signal -> lower return in this synthetic panel


def test_no_relationship_gives_small_t():
    sig, px, _ = _panel(seed=3, beta=0.0)
    fm = fama_macbeth(forward_return(px, 1), {"sig": sig})
    assert abs(fm.attrs["summary"]["sig"]["nw_t"]) < 2.5
