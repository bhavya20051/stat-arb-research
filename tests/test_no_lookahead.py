"""Position lagging and no-lookahead execution.

A signal with perfect foresight of the NEXT fill-to-fill return must earn nothing when executed with lag=1
(fill at next open) and a lot when incorrectly executed with lag=0. Also: outputs up to date t must not
change when prices after t change.
"""

import numpy as np
import pandas as pd

from statarb.backtest.engine import EngineInputs, run_backtest
from statarb.execution.costs import CostParams

ZERO = CostParams(commission_per_share=0, min_commission_per_order=0, borrow_annual=0, pay_spread=False, impact_k=0)


def _random_prices(seed=1, T=400, N=8):
    rng = np.random.default_rng(seed)
    ret = rng.normal(0, 0.01, size=(T, N))
    px = 100 * np.cumprod(1 + ret, axis=0)
    dates = pd.bdate_range("2015-01-01", periods=T)
    cols = [f"S{i}" for i in range(N)]
    return pd.DataFrame(px, index=dates, columns=cols)


def test_foresight_signal_earns_nothing_with_one_bar_lag():
    px = _random_prices()
    vol = pd.DataFrame(1e6, index=px.index, columns=px.columns)
    fwd = px.shift(-1) / px - 1  # return from fill t to fill t+1 (lookahead)
    w = np.sign(fwd).fillna(0) / px.shape[1]
    cheat = run_backtest(EngineInputs(w, px, vol, lag=0), 1e6, ZERO)
    honest = run_backtest(EngineInputs(w, px, vol, lag=1), 1e6, ZERO)
    assert cheat["gross_ret"].mean() > 0.004  # ~ mean |ret| of 0.008
    assert abs(honest["gross_ret"].mean()) < 0.0015


def test_past_results_invariant_to_future_prices():
    px = _random_prices(seed=2)
    vol = pd.DataFrame(1e6, index=px.index, columns=px.columns)
    rng = np.random.default_rng(3)
    w = pd.DataFrame(rng.normal(0, 0.05, size=px.shape), index=px.index, columns=px.columns)
    base = run_backtest(EngineInputs(w, px, vol, lag=1), 1e6, ZERO)
    px2 = px.copy()
    px2.iloc[300:] *= 1.5
    alt = run_backtest(EngineInputs(w, px2, vol, lag=1), 1e6, ZERO)
    pd.testing.assert_frame_equal(base.iloc[:299], alt.iloc[:299])
