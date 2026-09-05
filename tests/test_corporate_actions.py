"""Halted-then-delisted name: no phantom fills on halt bars; forced close at the delisting return.

Hand calc: long 0.10 in X filled day0 @100. Day1 halt (no volume, no price): no fill, no P&L, position carried.
Day2 delisting with return -1.0 (receivership): gross_ret = 0.10 * (-1.0) = -0.10; position becomes 0 forever,
even though target weights keep asking for 0.10.
"""

import numpy as np
import pandas as pd

from statarb.backtest.engine import EngineInputs, run_backtest
from statarb.execution.costs import CostParams

ZERO = CostParams(commission_per_share=0, min_commission_per_order=0, borrow_annual=0, pay_spread=False, impact_k=0)


def test_halt_then_delist_books_full_loss_once():
    dates = pd.bdate_range("2023-03-08", periods=4)  # 03-08, 03-09, 03-10, 03-13
    px = pd.DataFrame({"X": [100.0, np.nan, np.nan, np.nan], "Y": [10.0, 10.0, 10.0, 10.0]}, index=dates)
    vol = pd.DataFrame({"X": [1e6, 0.0, 0.0, 0.0], "Y": [1e6] * 4}, index=dates)
    w = pd.DataFrame({"X": [0.10] * 4, "Y": [0.0] * 4}, index=dates)
    delist = {"X": (dates[2], -1.0)}
    out = run_backtest(EngineInputs(w, px, vol, lag=0, delist=delist), 1e6, ZERO)
    assert np.isclose(out["gross_ret"].iloc[0], 0.0)
    assert np.isclose(out["gross_ret"].iloc[1], 0.0)  # halt: carried, no phantom fill
    assert np.isclose(out["turnover"].iloc[1], 0.0)
    assert np.isclose(out["gross_ret"].iloc[2], -0.10)
    assert np.isclose(out["gross_exposure"].iloc[2], 0.0)
    assert np.isclose(out["gross_exposure"].iloc[3], 0.0)  # cannot re-enter a dead name
    assert np.isclose(out["turnover"].iloc[3], 0.0)


def test_merger_closes_at_last_price():
    dates = pd.bdate_range("2022-10-24", periods=3)
    px = pd.DataFrame({"X": [50.0, 54.0, np.nan]}, index=dates)
    vol = pd.DataFrame({"X": [1e6, 1e6, 0.0]}, index=dates)
    w = pd.DataFrame({"X": [0.2, 0.2, 0.2]}, index=dates)
    out = run_backtest(EngineInputs(w, px, vol, lag=0, delist={"X": (dates[2], 0.0)}), 1e6, ZERO)
    assert np.isclose(out["gross_ret"].iloc[1], 0.2 * (54 / 50 - 1))
    assert np.isclose(out["gross_ret"].iloc[2], 0.0)
    assert np.isclose(out["gross_exposure"].iloc[2], 0.0)
