"""Exact hand-computed P&L for a two-symbol, three-day MOC book (lag = 0).

Hand calculation (capital 1,000,000, commissions 0.0035/share min 0.35, no other costs):
Day0 fills: A +0.5 @100 -> 5,000 sh (comm 17.50); B -0.5 @50 -> 10,000 sh (comm 35.00). total 52.50.
Day1: gross = 0.5*(102/100-1) + (-0.5)*(49/50-1) = 0.01 + 0.01 = 0.02.
      drifted held: A 0.51, B -0.49; rebalance to +/-0.5: A sells $10,000 (98.04 sh -> min 0.35),
      B buys back $10,000 @49 (204.08 sh -> 0.7143). total 1.0643. turnover 0.02.
Day2: gross = 0.5*(101/102-1) + (-0.5)*(50.5/49-1) = -0.00490196 - 0.01530612 = -0.02020808.
      drifted held: A 0.495098, B -0.515306; close all: A 4,902.0 sh -> 17.157; B 10,204.0 sh -> 35.714.
"""

import numpy as np
import pandas as pd

from statarb.backtest.engine import EngineInputs, run_backtest
from statarb.execution.costs import CostParams


def _inputs():
    dates = pd.to_datetime(["2020-01-02", "2020-01-03", "2020-01-06"])
    price = pd.DataFrame({"A": [100.0, 102.0, 101.0], "B": [50.0, 49.0, 50.5]}, index=dates)
    vol = pd.DataFrame(1_000_000.0, index=dates, columns=["A", "B"])
    w = pd.DataFrame({"A": [0.5, 0.5, 0.0], "B": [-0.5, -0.5, 0.0]}, index=dates)
    return EngineInputs(target_weights=w, fill_price=price, fill_volume=vol, lag=0)


def test_hand_computed_gross_and_commissions():
    costs = CostParams(commission_per_share=0.0035, min_commission_per_order=0.35, borrow_annual=0.0,
                       pay_spread=False, impact_k=0.0)
    out = run_backtest(_inputs(), capital=1_000_000, costs=costs)
    assert np.isclose(out["gross_ret"].iloc[0], 0.0)
    assert np.isclose(out["gross_ret"].iloc[1], 0.02, atol=1e-12)
    assert np.isclose(out["gross_ret"].iloc[2], -0.02020808, atol=1e-8)
    comm = out["commission"] * 1_000_000
    assert np.isclose(comm.iloc[0], 52.50, atol=1e-9)
    a1 = 0.35  # 98.04 sh * 0.0035 = 0.343 -> min 0.35
    b1 = 10_000 / 49 * 0.0035
    assert np.isclose(comm.iloc[1], a1 + b1, atol=1e-9)
    a2 = 0.5 * (101 / 102) * 1_000_000 / 101 * 0.0035
    b2 = 0.5 * (50.5 / 49) * 1_000_000 / 50.5 * 0.0035
    assert np.isclose(comm.iloc[2], a2 + b2, atol=1e-9)
    assert np.isclose(out["turnover"].iloc[0], 1.0)
    assert np.isclose(out["turnover"].iloc[1], 0.02, atol=1e-12)
    assert np.isclose(out["net_ret"].iloc[1], 0.02 - (a1 + b1) / 1_000_000, atol=1e-12)
    assert np.isclose(out["gross_exposure"].iloc[2], 0.0)


def test_borrow_charged_on_short_only():
    costs = CostParams(commission_per_share=0.0, min_commission_per_order=0.0, borrow_annual=0.0252,
                       pay_spread=False, impact_k=0.0)
    out = run_backtest(_inputs(), capital=1_000_000, costs=costs)
    # day0: short notional 500,000 * 0.0252/252 = 50 -> 5e-5 of capital
    assert np.isclose(out["borrow"].iloc[0], 50 / 1_000_000, atol=1e-12)
    assert np.isclose(out["borrow"].iloc[2], 0.0)


def test_mark_vs_fill_execution_pnl():
    """Buy 10% of capital at a limit fill of 98 while the close is 100 -> +0.2% execution gain on the fill day,
    then marked close-to-close; selling next day at a fill of 106 vs close 104 -> +2% * 0.1 gain."""
    dates = pd.to_datetime(["2020-01-02", "2020-01-03", "2020-01-06"])
    fill = pd.DataFrame({"X": [98.0, 106.0, 104.0]}, index=dates)
    mark = pd.DataFrame({"X": [100.0, 104.0, 104.0]}, index=dates)
    vol = pd.DataFrame({"X": [1e6, 1e6, 1e6]}, index=dates)
    w = pd.DataFrame({"X": [0.10, 0.0, 0.0]}, index=dates)
    costs = CostParams(commission_per_share=0, min_commission_per_order=0, borrow_annual=0, pay_spread=False, impact_k=0)
    out = run_backtest(EngineInputs(w, fill, vol, lag=0, mark_price=mark), 1e6, costs)
    assert np.isclose(out["gross_ret"].iloc[0], 0.10 * (100 / 98 - 1))
    # day1: held (marked value 0.10*100/98) earns 104/100-1, then sold at 106 vs mark 104: trade_w = -held
    held1 = 0.10 * (100 / 98) * (104 / 100)
    assert np.isclose(out["gross_ret"].iloc[1], 0.10 * (100 / 98) * (104 / 100 - 1) + (-held1) * (104 / 106 - 1))
    assert np.isclose(out["gross_exposure"].iloc[1], 0.0)
