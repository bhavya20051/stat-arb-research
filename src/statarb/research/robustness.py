"""Phase 10 kill tests for a selected configuration, run on DEV+VAL (never on the holdout).

Each test is a CLI-reproducible variant of the frozen spec; results are written to results/robustness/<family>/.
Tests: cost multipliers (1.0/1.5/2.0, +5 bp), sqrt/k=1 impact stress, cost profiles (retail/institutional),
execution delay (+1 bar via signal lag), fill at the 15:55 bar proxy (worse fill), parameter neighbours, yearly and
VIX-regime P&L, universe subsets (top-250 liquidity), P&L concentration (drop best day/week/month/name/5 names),
placebos (signal lagged +1 day, inverted signal), leverage 2x/5x, pre-earnings exclusion ON, drawdown rule off.
"""

from __future__ import annotations

import json
from dataclasses import replace

import numpy as np
import pandas as pd

from statarb.backtest.run_strategy import StrategySpec, run
from statarb.config import REPO_ROOT
from statarb.data.load import PROC
from statarb.research.dev_grid import load_feats
from statarb.statistics.metrics import summary_table

OUT = REPO_ROOT / "results" / "robustness"


def _summ(out: pd.DataFrame, s: dict, label: str) -> dict:
    n = s["net"]
    return {"variant": label, "net_sr": n["sharpe_ann"], "net_ann": n["ann_return"], "max_dd": n["max_drawdown"],
            "gross_sr": s["gross"]["sharpe_ann"], "turnover": s["avg_turnover"], "cost_bp": s["cost_bp_per_day"], "n_days": n["n_days"]}


def concentration(out: pd.DataFrame) -> dict:
    r = out["net_ret"]
    res = {"base_sr": summary_table(r)["sharpe_ann"]}
    res["drop_best_day"] = summary_table(r.drop(r.idxmax()))["sharpe_ann"]
    wk = r.groupby(pd.Grouper(freq="W")).sum()
    res["drop_best_week"] = summary_table(r[~r.index.to_period("W").isin([wk.idxmax().to_period("W")])])["sharpe_ann"]
    mo = r.groupby(pd.Grouper(freq="ME")).sum()
    res["drop_best_month"] = summary_table(r[r.index.to_period("M") != mo.idxmax().to_period("M")])["sharpe_ann"]
    return res


def run_suite(spec: StrategySpec, family: str, start: str, end: str) -> pd.DataFrame:
    d = OUT / family
    d.mkdir(parents=True, exist_ok=True)
    feats = load_feats()
    base = replace(spec, start=start, end=end, label=f"rob_{family}_base")
    rows = []
    out0, s0 = run(base, feats, write=False)
    rows.append(_summ(out0, s0, "base"))
    out0.to_csv(d / "daily_base.csv")
    # costs
    for m in (1.5, 2.0):
        o, s = run(base, feats, cost_multiplier=m, write=False); rows.append(_summ(o, s, f"costs_x{m}"))
    o, s = run(base, feats, extra_bp=5.0, write=False); rows.append(_summ(o, s, "slippage_+5bp"))
    o, s = run(replace(base, cost_profile="prime_brokered_fund"), feats, write=False); rows.append(_summ(o, s, "profile_prime_brokered_fund"))
    # execution
    o, s = run(replace(base, signal_lag_days=1), feats, write=False); rows.append(_summ(o, s, "signal_lag_+1day"))
    o, s = run(replace(base, execution="moc" if base.execution == "loc" else "loc"), feats, write=False); rows.append(_summ(o, s, "other_execution"))
    # parameters (neighbours)
    for lb in (1, 2, 3):
        for h in (1, 2, 3):
            if (lb, h) != (base.lookback, base.holding):
                o, s = run(replace(base, lookback=lb, holding=h), feats, write=False); rows.append(_summ(o, s, f"neighbour_k{lb}_h{h}"))
    # leverage / risk
    for g in (2.0, 5.0):
        o, s = run(replace(base, gross_max=g), feats, write=False); rows.append(_summ(o, s, f"gross_max_{g}"))
    o, s = run(replace(base, drawdown_rule=False), feats, write=False); rows.append(_summ(o, s, "no_drawdown_rule"))
    o, s = run(replace(base, pre_earnings_exclusion=True), feats, write=False); rows.append(_summ(o, s, "pre_earnings_exclusion_on"))
    o, s = run(replace(base, vix_gate="none" if base.vix_gate != "none" else "linear"), feats, write=False); rows.append(_summ(o, s, "vix_gate_toggled"))
    # placebo: inverted signal
    inv = dict(feats)
    for k in list(feats):
        if k.startswith("score_moc_k"):
            inv[k] = -feats[k]
    o, s = run(base, inv, write=False); rows.append(_summ(o, s, "placebo_inverted_signal"))
    # universe subset: top-250 by trailing dollar volume
    from statarb.features.build import load_feature
    dv = load_feature("dollar_vol_60")
    top = dv.rank(axis=1, ascending=False) <= 250
    sub = dict(feats); sub["eligible_moc"] = feats["eligible_moc"] & top.reindex_like(feats["eligible_moc"]).fillna(False)
    o, s = run(base, sub, write=False); rows.append(_summ(o, s, "universe_top250"))
    df = pd.DataFrame(rows)
    df.to_csv(d / "kill_tests.csv", index=False)
    # time slices and regimes on the base run
    yearly = out0["net_ret"].groupby(out0.index.year).agg(["sum", lambda x: summary_table(x)["sharpe_ann"] if len(x) > 20 else np.nan])
    yearly.columns = ["net_return", "net_sharpe"]
    yearly.to_csv(d / "yearly.csv")
    vix = pd.read_parquet(PROC / "vix.parquet").set_index("date")["vix"].reindex(out0.index).shift(1)
    q = vix.rolling(252, min_periods=120).rank(pct=True)
    reg = {}
    for name, m in (("low_vix", q <= 1 / 3), ("mid_vix", (q > 1 / 3) & (q <= 2 / 3)), ("high_vix", q > 2 / 3)):
        r = out0["net_ret"][m.fillna(False)]
        reg[name] = {"net_sharpe": summary_table(r)["sharpe_ann"] if len(r) > 60 else None, "days": int(len(r))}
    conc = concentration(out0)
    with open(d / "regimes_concentration.json", "w", encoding="utf-8") as f:
        json.dump({"vix_regimes": reg, "concentration": conc}, f, indent=1, default=float)
    return df
