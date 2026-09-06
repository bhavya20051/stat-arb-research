"""Numerical parity of the C++ engine with the Python engine (hand-computed cases and a random panel)."""

import numpy as np
import pandas as pd
import pytest

from statarb.backtest.engine import EngineInputs, run_backtest
from statarb.execution.costs import CostParams

cpp = pytest.importorskip("statarb.backtest.engine_cpp")


def _compare(inp, capital, costs, atol=1e-10):
    a = run_backtest(inp, capital, costs)
    b = cpp.run_backtest_cpp(inp, capital, costs)
    for col in ("gross_ret", "commission", "fees", "spread", "impact", "borrow", "turnover", "gross_exposure", "net_exposure", "net_ret"):
        assert np.allclose(a[col].to_numpy(), b[col].to_numpy(), atol=atol, equal_nan=True), col
    return a, b


def test_parity_hand_case():
    dates = pd.to_datetime(["2020-01-02", "2020-01-03", "2020-01-06"])
    price = pd.DataFrame({"A": [100.0, 102.0, 101.0], "B": [50.0, 49.0, 50.5]}, index=dates)
    vol = pd.DataFrame(1e6, index=dates, columns=["A", "B"])
    w = pd.DataFrame({"A": [0.5, 0.5, 0.0], "B": [-0.5, -0.5, 0.0]}, index=dates)
    costs = CostParams(commission_per_share=0.0035, min_commission_per_order=0.35, borrow_annual=0.0252, pay_spread=False, impact_k=0.0)
    a, b = _compare(EngineInputs(w, price, vol, lag=0), 1e6, costs)
    assert np.isclose(b["gross_ret"].iloc[1], 0.02)


def test_parity_random_panel_with_delist_mark_and_costs():
    rng = np.random.default_rng(0)
    T, N = 300, 25
    dates = pd.bdate_range("2019-01-01", periods=T)
    cols = [f"S{i}" for i in range(N)]
    px = pd.DataFrame(100 * np.cumprod(1 + rng.normal(0, 0.01, (T, N)), axis=0), index=dates, columns=cols)
    fill = px * (1 + rng.normal(0, 0.001, (T, N)))
    vol = pd.DataFrame(rng.integers(0, 2_000_000, (T, N)).astype(float), index=dates, columns=cols)
    vol.iloc[::17, 3] = 0.0
    w = pd.DataFrame(rng.normal(0, 0.03, (T, N)), index=dates, columns=cols)
    w.iloc[::7, 5] = np.nan
    hs = pd.DataFrame(rng.uniform(0, 0.001, (T, N)), index=dates, columns=cols)
    sig = pd.DataFrame(rng.uniform(0.005, 0.03, (T, N)), index=dates, columns=cols)
    adv = pd.DataFrame(rng.uniform(1e5, 1e7, (T, N)), index=dates, columns=cols)
    delist = {"S7": (dates[150], -1.0), "S9": (dates[200], -0.3)}
    for lag, mark in ((0, px), (1, None)):
        inp = EngineInputs(w, fill, vol, lag=lag, half_spread=hs, sigma_daily=sig, adv_shares=adv, delist=delist, mark_price=mark)
        costs = CostParams(commission_per_share=0.0012, min_commission_per_order=0.0, sec_fee_rate=2.06e-5, finra_taf_per_share=0.000195,
                           finra_taf_max=9.79, clearing_pct_notional=2.6e-6, borrow_annual=0.003, impact_k=0.142, impact_exponent=0.6,
                           pay_spread=(lag == 1), extra_slippage_bp=2.0)
        _compare(inp, 5e6, costs, atol=1e-9)
