import numpy as np
import pandas as pd

from statarb.portfolio.construct import (
    apply_no_trade_band,
    beta_hedge,
    cap_weights,
    dollar_neutralize,
    enforce_limits,
    neutralize_sector,
    vol_target,
)
from statarb.signals.reversal import decile_weights, jump_exclusion_mask, reversal_score


def _frame(seed=0, T=5, N=40):
    rng = np.random.default_rng(seed)
    return pd.DataFrame(rng.normal(size=(T, N)), index=pd.bdate_range("2020-01-01", periods=T),
                        columns=[f"S{i}" for i in range(N)])


def test_decile_weights_are_dollar_neutral_and_signed():
    score = _frame()
    w = decile_weights(score)
    assert np.allclose(w.sum(axis=1), 0)
    assert np.allclose(w.abs().sum(axis=1), 2.0)
    top = score.iloc[0].idxmax()
    bottom = score.iloc[0].idxmin()
    assert w.iloc[0][top] > 0 and w.iloc[0][bottom] < 0  # oversold (high score) is bought


def test_reversal_score_sign():
    res = pd.DataFrame({"A": [0.0] * 60 + [-0.05], "B": [0.0] * 60 + [0.05]})
    res.iloc[:60] = np.random.default_rng(1).normal(0, 0.01, (60, 2))
    s = reversal_score(res, lookback=1, zscore_window=60)
    assert s["A"].iloc[-1] > 0 and s["B"].iloc[-1] < 0  # a big drop yields a positive (buy) score


def test_sector_neutral_and_caps_and_limits():
    w = dollar_neutralize(_frame(seed=2))
    sec = pd.DataFrame([["X"] * 20 + ["Y"] * 20] * 5, index=w.index, columns=w.columns)
    wn = neutralize_sector(w, sec)
    for d in wn.index:
        assert abs(wn.loc[d][sec.loc[d] == "X"].sum()) < 1e-12
    wc = cap_weights(wn * 10, 0.02)
    assert wc.abs().max().max() <= 0.02 + 1e-12
    wl = enforce_limits(wn * 5, gross_max=2.0, net_abs_max=0.05)
    assert (wl.abs().sum(axis=1) <= 2.0 + 1e-9).all()
    assert (wl.sum(axis=1).abs() <= 0.05 + 1e-9).all()


def test_beta_hedge_zero_ex_ante_beta():
    w = dollar_neutralize(_frame(seed=3))
    beta = pd.DataFrame(1.2, index=w.index, columns=w.columns)
    beta.iloc[:, :10] = 0.5
    h = beta_hedge(w, beta, "SPY")
    full_beta = beta.copy()
    full_beta["SPY"] = 1.0
    assert np.allclose((h * full_beta).sum(axis=1), 0)


def test_vol_target_and_band():
    w = dollar_neutralize(_frame(seed=4))
    est = pd.Series([0.20] * 5, index=w.index)
    wt = vol_target(w, est, 0.10)
    assert np.allclose(wt.abs().sum(axis=1), 0.5)
    tgt = pd.DataFrame({"A": [0.10, 0.1005, 0.13], "B": [0.0, 0.0, 0.0]},
                       index=pd.bdate_range("2020-01-01", periods=3))
    b = apply_no_trade_band(tgt, 0.002)
    assert b["A"].tolist() == [0.10, 0.10, 0.13]


def test_jump_mask_is_ex_ante():
    rng = np.random.default_rng(5)
    res = pd.DataFrame(rng.normal(0, 0.01, (120, 2)), columns=["A", "B"])
    res.iloc[100, 0] = 0.10  # 10-sigma jump on day 100
    m = jump_exclusion_mask(res, 60, 3.0, 3)
    assert not m.iloc[100, 0] and not m.iloc[102, 0] and m.iloc[103, 0]
    assert m.iloc[99, 0]  # the day before the jump is unaffected (no lookahead)
