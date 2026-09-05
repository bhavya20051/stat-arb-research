import numpy as np

from statarb.execution.costs import CostParams, borrow_cost, commission, impact_cost, regulatory_fees, spread_cost


def test_commission_minimum_and_cap():
    p = CostParams(commission_per_share=0.0035, min_commission_per_order=0.35, max_commission_pct=0.01)
    sh = np.array([10.0, 1000.0, 0.0, -5.0])
    notional = np.array([1000.0, 100000.0, 0.0, 10.0])
    c = commission(sh, notional, p)
    assert np.isclose(c[0], 0.35)  # 0.035 -> min
    assert np.isclose(c[1], 3.5)
    assert c[2] == 0.0
    assert np.isclose(c[3], 0.10)  # capped at 1% of $10


def test_fees_only_on_sells():
    p = CostParams(sec_fee_rate=27.8e-6, finra_taf_per_share=0.000166, finra_taf_max=8.30)
    sh = np.array([100.0, -100.0, -100000.0])
    notional = np.array([10000.0, -10000.0, -1e7])
    f = regulatory_fees(sh, notional, p)
    assert f[0] == 0.0
    assert np.isclose(f[1], 10000 * 27.8e-6 + 100 * 0.000166)
    assert np.isclose(f[2], 1e7 * 27.8e-6 + 8.30)


def test_spread_zero_for_auction_fills():
    p = CostParams(pay_spread=False)
    assert spread_cost(np.array([1e5]), np.array([0.001]), p)[0] == 0.0
    p2 = CostParams(pay_spread=True, spread_multiplier=2.0, extra_slippage_bp=5)
    assert np.isclose(spread_cost(np.array([1e5]), np.array([0.001]), p2)[0], 1e5 * (0.002 + 0.0005))


def test_impact_and_borrow():
    p = CostParams(impact_k=1.0, impact_exponent=0.5, borrow_annual=0.005, trading_days=250)
    assert np.isclose(impact_cost(np.array([1e5]), np.array([0.04]), np.array([0.02]), p)[0], 1e5 * 0.02 * 0.2)
    assert np.isclose(borrow_cost(np.array([-1e5, 1e5]), p).sum(), 1e5 * 0.005 / 250)
