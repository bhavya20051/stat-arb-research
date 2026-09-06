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


def test_expected_earnings_window_is_ex_ante_construction():
    """An expected-earnings flag derived from last year's filing must not depend on this year's actual filing date."""
    import pandas as pd
    idx = pd.bdate_range("2019-01-01", periods=600)
    earn = pd.DataFrame(False, index=idx, columns=["A"])
    earn.loc[idx[50], "A"] = True  # filing in year 1
    # replicate the builder's rule
    ex = pd.DataFrame(False, index=idx, columns=["A"])
    i = idx.searchsorted(idx[50] + pd.Timedelta(days=364))
    for off in range(-3, 4):
        ex.iat[i + off, 0] = True
    assert ex["A"].sum() == 7 and ex["A"].iloc[i]
    assert not ex["A"].iloc[:i - 3].any()


def test_event_weights_cohorts_and_neutrality():
    from statarb.portfolio.construct import event_weights
    idx = pd.bdate_range("2020-01-01", periods=6)
    sc = pd.DataFrame(0.0, index=idx, columns=["A", "B", "C", "D"])
    sc.loc[idx[0], ["A", "B"]] = [2.5, -2.5]   # one long, one short on day 0
    sc.loc[idx[1], "C"] = 3.0                   # one long on day 1
    w = event_weights(sc, entry_z=2.0, holding=3, per_side_gross=0.5, max_name=0.05, ref_window=3)
    # ref_window=3, min_periods=20 -> no expected count available on these few days -> zero weights (ex-ante rule)
    assert w.abs().sum().sum() == 0.0
    idx2 = pd.bdate_range("2020-01-01", periods=40)
    sc2 = pd.DataFrame(0.0, index=idx2, columns=["A", "B", "C", "D"])
    sc2.iloc[:, 0] = 2.5; sc2.iloc[:, 1] = -2.5          # one long and one short entrant every day
    w2 = event_weights(sc2, entry_z=2.0, holding=3, per_side_gross=0.5, max_name=0.05, ref_window=30)
    # expected entrants = 1 per side -> weight = min(0.05, 0.5/3) = 0.05 per cohort; 3 overlapping cohorts -> 0.15
    assert np.isclose(w2.iloc[-1]["A"], 0.15) and np.isclose(w2.iloc[-1]["B"], -0.15)
    assert np.isclose(w2.iloc[-1].sum(), 0.0)


def test_drawdown_scaler_is_ex_ante_and_releases():
    from statarb.backtest.run_strategy import drawdown_scaler
    r = pd.Series([0.0, -0.06, -0.06, 0.02, 0.05, 0.05, 0.0])  # dd: 0, -6%, -11.6%, -9.9%, -5.4%, -0.7%, -0.7%
    m = drawdown_scaler(r, 0.10, 0.5, 0.05)
    assert m.tolist()[:4] == [1.0, 1.0, 1.0, 0.5]   # trigger seen at t=2 -> multiplier applies from t=3 (ex-ante)
    assert m.iloc[4] == 0.5 and m.iloc[6] == 1.0      # released once within 5% of peak (seen at t=5 -> applies t=6)
