"""Pre-registered DEV candidate grid for the closing-auction model (Phase 8/9 selection discipline).

Every configuration is a `candidate` registry row created BEFORE it runs; the per-period net return series of
every candidate is stored so CSCV/PBO and the Deflated Sharpe Ratio can be computed over the full set.
Selection rule (fixed in advance): maximise DEV net Sharpe subject to gross exposure <= 2, avg turnover <= 2.5,
and the parameter-neighbour stability check in Phase 10; ties broken toward lower turnover.
"""

from __future__ import annotations

import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd

from statarb.backtest.run_strategy import StrategySpec, run
from statarb.config import REPO_ROOT
from statarb.features.build import load_feature
from statarb.features.build_moc import load_moc
from statarb.research.registry import _read, record, register

OUT = REPO_ROOT / "results" / "dev" / "grid"

GRID = {
    "lookback": [1, 3],
    "holding": [1, 2, 3],
    "n_deciles": [5, 10],
    "vix_gate": ["none", "linear"],
    "exec": ["moc", "loc0.5", "loc1.0"],
}


GRID_EVENT = {
    "lookback": [1, 3],
    "holding": [1, 2, 3],
    "entry_z": [2.0, 3.0],
    "vix_gate": ["none", "linear"],
    "exec": ["moc", "loc1.0"],
}


GRID_DRIFT = {   # third strategy: earnings-8-K drift (PEAD replication under our timing/cost model)
    "lookback": [1],
    "holding": [1, 3, 5, 10],
    "entry_z": [1.0, 2.0],
    "vix_gate": ["none"],
    "exec": ["moc"],
}


GRID_DRIFT_VOL = {"lookback": [1], "holding": [1, 3], "entry_z": [1.0, 2.0], "vix_gate": ["none"], "exec": ["moc"], "drift_volume_bucket": ["high", "low"]}
GRID_DRIFT_TIMING = {"lookback": [1], "holding": [1, 3], "entry_z": [1.0], "vix_gate": ["none"], "exec": ["moc"], "drift_timing": ["after_hours", "intraday"]}


def candidate_id(d: dict) -> str:
    return "C-moc-" + "-".join(f"{k}{v}" for k, v in d.items())


def load_feats() -> dict:
    feats = {"ret": load_feature("ret"), "abn_turnover": load_feature("abn_turnover"), "spread": load_feature("spread"),
             "eligible_moc": load_moc("eligible_moc")}
    for k in (1, 2, 3):
        feats[f"score_moc_k{k}"] = load_moc(f"score_moc_k{k}")
    for extra in ("auction_vol_proxy", "beta_spy", "expected_earnings", "sector", "eligible_base", "earnings_flag_1540", "abn_turnover_1545", "earnings_timing_1540"):
        try:
            feats[extra if extra != "beta_spy" else "beta"] = load_moc(extra)
        except FileNotFoundError:
            pass
    return feats


def run_grid(dev_end: str = "2018-12-14", write_rows: bool = True) -> pd.DataFrame:
    OUT.mkdir(parents=True, exist_ok=True)
    feats = load_feats()
    existing = {r["experiment_id"] for r in _read()}
    rows, series = [], {}
    combos = [dict(zip(GRID.keys(), c)) for c in itertools.product(*GRID.values())]
    combos += [{"construction": "event", **dict(zip(GRID_EVENT.keys(), c))} for c in itertools.product(*GRID_EVENT.values())]
    combos += [{"construction": "event", "signal": "earnings_drift", **dict(zip(GRID_DRIFT.keys(), c))} for c in itertools.product(*GRID_DRIFT.values())]
    combos += [{"construction": "event", "signal": "earnings_drift", **dict(zip(GRID_DRIFT_VOL.keys(), c))} for c in itertools.product(*GRID_DRIFT_VOL.values())]
    combos += [{"construction": "event", "signal": "earnings_drift", **dict(zip(GRID_DRIFT_TIMING.keys(), c))} for c in itertools.product(*GRID_DRIFT_TIMING.values())]
    for d in combos:
        cid = candidate_id(d)
        if cid not in existing and write_rows:
            register(cid, "candidate", hypothesis="MOC residual reversal, DEV candidate configuration",
                     signal_definition=f"score_moc_k{d['lookback']} (15:45 signal, 250d betas, news/reliability masks)",
                     universe="PIT S&P 500, eligible_moc", holding_period=str(d["holding"]),
                     features="residual reversal score, VIX", model="rank portfolio (quantile), vol-target 10%, caps 2%",
                     parameters=json.dumps(d), train_period=f"DEV intraday start -> {dev_end}", validation_period="none (DEV)",
                     expected_result="net Sharpe > 0", falsification_condition="net Sharpe <= 0 on DEV")
        ex = d["exec"]
        kw = {k: v for k, v in d.items() if k != "exec"}
        spec = StrategySpec(execution="loc" if ex.startswith("loc") else "moc", limit_delta=float(ex[3:]) if ex.startswith("loc") else 0.5,
                            band=0.0, end=dev_end, label=cid, **kw)  # kw may include construction="event", entry_z
        out, s = run(spec, feats, write=False)
        series[cid] = out["net_ret"]
        r = {"id": cid, **d, "gross_sr": s["gross"]["sharpe_ann"], "net_sr": s["net"]["sharpe_ann"],
             "net_ann": s["net"]["ann_return"], "max_dd": s["net"]["max_drawdown"], "turnover": s["avg_turnover"],
             "gross_exp": s["avg_gross_exposure"], "cost_bp": s["cost_bp_per_day"], "n_days": s["net"]["n_days"]}
        rows.append(r)
        if write_rows:
            record(cid, f"DEV net SR {r['net_sr']:.2f}, gross SR {r['gross_sr']:.2f}, net ann {r['net_ann']:.3f}, maxDD {r['max_dd']:.2f}, turnover {r['turnover']:.2f}, cost {r['cost_bp']:.1f} bp/day",
                   "PASS" if r["net_sr"] > 0 else "FAIL (net <= 0)")
        print(f"{cid}: gross {r['gross_sr']:.2f} net {r['net_sr']:.2f} turn {r['turnover']:.2f} cost {r['cost_bp']:.1f}")
    df = pd.DataFrame(rows).sort_values("net_sr", ascending=False)
    df.to_csv(OUT / "grid_results.csv", index=False)
    pd.DataFrame(series).to_parquet(OUT / "grid_net_returns.parquet")
    return df
