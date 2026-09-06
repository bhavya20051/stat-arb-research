"""Tests for the post-audit repairs of 2026-09-06 (red-team findings F1, F3, F4, F9, F15).

F1  the SPY hedge is executed MOC on the FILLED book and the realized dollar-net stays inside the band;
F4  an LOC entry that is cancelled stays an entry the next day (it is re-submitted as an LOC, never a fallback MOC);
F3  eligibility at 15:45 is invariant to anything that happens between 15:45 and the close of day t;
F9  a raw dividend is rescaled to a split-adjusted intraday basis;
F15 delisting rules: a bankruptcy 'Q' ticker maps to -100%, a plain ticker change to 0.
"""

import numpy as np
import pandas as pd

from statarb.execution.limit_orders import loc_fills
from statarb.features.build_moc import dividend_on_intraday_basis, ex_ante_eligibility


def _frames(T=6):
    idx = pd.bdate_range("2024-01-02", periods=T)
    cols = ["A", "B", "SPY"]
    p1545 = pd.DataFrame(100.0, index=idx, columns=cols)
    last_bar = pd.DataFrame(100.0, index=idx, columns=cols)
    adj_close = pd.DataFrame(100.0, index=idx, columns=cols)
    sigma = pd.DataFrame(0.002, index=idx, columns=cols)  # typical 15:45->close move 20 bp
    return idx, cols, p1545, last_bar, adj_close, sigma


def test_hedge_is_sized_to_the_filled_book_and_fills_moc():
    idx, cols, p1545, last_bar, ac, sig = _frames()
    # target: long A 0.5, short B 0.5 every day; A never satisfies the LOC condition, B always does
    w = pd.DataFrame({"A": 0.5, "B": -0.5, "SPY": 0.0}, index=idx)
    ac["B"] = 100.0 * (1 + 0.01) ** np.arange(len(idx))         # B rallies 1%/day into the close -> short LOC fills
    last_bar["B"] = ac["B"].shift(1).fillna(100.0)               # yesterday's last bar = yesterday's close (same basis)
    beta = pd.DataFrame(1.0, index=idx, columns=cols)
    fill, w_eff = loc_fills(w, p1545, last_bar, ac, sig, delta=1.0, hedge_symbol="SPY", beta=beta, net_abs_max=0.05, return_effective=True)
    assert fill["SPY"].notna().all()                              # hedge always fills (MOC)
    assert fill["A"].isna().all()                                 # A's LOC never fills
    assert fill["B"].iloc[1:].notna().all()                      # (day 0 has no prior close to evaluate the limit)
    # filled book is short B only -> hedge = +0.5 SPY; realized net within the band
    assert np.allclose(w_eff["SPY"].iloc[1:], 0.5)
    net = w_eff.sum(axis=1)
    assert (net.abs() <= 0.05 + 1e-12).all()


def test_cancelled_entry_is_resubmitted_as_loc_not_moc():
    idx, cols, p1545, last_bar, ac, sig = _frames()
    w = pd.DataFrame({"A": 0.5, "B": 0.0, "SPY": 0.0}, index=idx)
    fill, w_eff = loc_fills(w, p1545, last_bar, ac, sig, delta=1.0, hedge_symbol=None, return_effective=True)
    # the close never extends the move, so the entry is cancelled EVERY day (old code filled it MOC on day 2)
    assert fill["A"].isna().all()
    assert (w_eff["A"] == 0.0).all()


def test_loc_condition_uses_official_close():
    idx, cols, p1545, last_bar, ac, sig = _frames()
    w = pd.DataFrame({"A": 0.5, "B": 0.0, "SPY": 0.0}, index=idx)
    # the intraday last bar of day 1 prints 50 bp below the 15:45 price, but the OFFICIAL close is unchanged -> no fill
    # (the old code compared last_bar to p1545 and would have filled)
    last_bar.loc[idx[1], "A"] = 99.5
    fill = loc_fills(w, p1545, last_bar, ac, sig, delta=1.0, hedge_symbol=None)
    assert np.isnan(fill.loc[idx[1], "A"])
    # official close down 50 bp with 15:45 at 100 -> fill
    ac2 = ac.copy()
    ac2["A"] = 100.0 * (1 - 0.005) ** np.arange(len(idx))
    lb2 = last_bar.copy()
    lb2["A"] = ac2["A"].shift(1).fillna(100.0)
    fill2 = loc_fills(w, p1545, lb2, ac2, sig, delta=1.0, hedge_symbol=None)
    assert fill2["A"].iloc[1:].notna().all()


def test_eligibility_at_1545_ignores_the_close_of_day_t():
    idx = pd.bdate_range("2024-01-02", periods=5)
    elig = pd.DataFrame(True, index=idx, columns=["A"])
    z = pd.DataFrame(0.5, index=idx, columns=["A"])
    base = ex_ante_eligibility(elig, z)
    # a jump that is only visible in the day-t daily panel (full-day residual) must not change eligibility at t
    elig2 = elig.copy()
    elig2.iloc[3, 0] = False
    after = ex_ante_eligibility(elig2, z)
    assert after.iloc[3, 0] == base.iloc[3, 0]
    assert not after.iloc[4, 0]                       # ...but it does exclude the NEXT day (known by then)
    # partial-day jump at 15:45 excludes today
    z2 = z.copy()
    z2.iloc[2, 0] = 3.5
    assert not ex_ante_eligibility(elig, z2).iloc[2, 0]


def test_dividend_rescaled_to_split_adjusted_intraday_basis():
    idx = pd.bdate_range("2019-08-08", periods=2)
    div = pd.DataFrame({"AAPL": [0.0, 0.77]}, index=idx)          # raw pre-4:1 dividend on the ex-date
    last_bar = pd.DataFrame({"AAPL": [50.86, 50.66]}, index=idx)  # intraday series split-adjusted (/4)
    close_raw = pd.DataFrame({"AAPL": [203.43, 202.64]}, index=idx)
    d = dividend_on_intraday_basis(div, last_bar, close_raw)
    assert abs(d.iloc[1, 0] - 0.77 / 4) < 1e-3


def test_delisting_rule_mapping(tmp_path, monkeypatch):
    import statarb.data.delisting as dl
    px = pd.DataFrame({"symbol": ["FTR"] * 3 + ["GPS"] * 3 + ["ZZZ"] * 3 + ["LIVE"] * 3,
                       "date": list(pd.bdate_range("2020-01-01", periods=3)) * 3 + list(pd.bdate_range("2026-08-26", periods=3))})
    monkeypatch.setattr(dl, "daily_long", lambda: px)
    monkeypatch.setattr(dl, "membership_intervals", lambda: pd.DataFrame())
    sm = pd.DataFrame({"symbol": ["FTR", "GPS", "ZZZ", "LIVE"], "new_symbol": ["FTERQ", "GAP", np.nan, np.nan]})
    sm.to_csv(tmp_path / "security_master.csv", index=False)
    monkeypatch.setattr(dl, "PROC", tmp_path)
    ev = dl.delisting_events("2026-08-31")
    assert ev["FTR"][1] == -1.0
    assert ev["GPS"][1] == 0.0
    assert ev["ZZZ"][1] == -0.30
    assert "LIVE" not in ev
