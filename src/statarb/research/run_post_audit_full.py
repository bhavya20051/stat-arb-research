"""Complete performance data set for portfolio-manager review: all three strategy families x both institutional cost
profiles, on the repaired (post-audit) pipeline. Runs after run_post_audit.py (uses its selections).

Per family (selected on the pre-registered development window 2013-10-23 -> 2018-12-14) and per profile
(market_maker, prime_brokered_fund):
  * full statistics on DEV, VAL (2019-01-02 -> 2022-12-15) and the 2023-01-03 -> 2026-08-31 diagnostic window:
    annualised return / vol / Sharpe (with Lo SE and bootstrap CI) / Sortino / Calmar / max drawdown / hit rate /
    profit factor / skew / kurtosis / PSR, average gross and net exposure, turnover, cost in bp/day by component,
    realized beta to SPY, market-timing component, yearly and monthly net returns, drawdown duration;
  * the kill-test suite (costs x1.5/x2, +5 bp, lag, other execution, neighbours, leverage, placebo, universe subset);
  * the capacity curve $1M -> $100M.
Everything is written to results/post_audit/full_metrics.json and results/post_audit/robustness_<profile>/<family>/.
"""

from __future__ import annotations

import json
import os
import time
import warnings
from dataclasses import replace

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
LOG = lambda *a: print(time.strftime("%H:%M:%S"), *a, flush=True)


def drawdown_stats(net: pd.Series) -> dict:
    cum = net.cumsum()
    peak = cum.cummax()
    dd = cum - peak
    in_dd = dd < 0
    # longest drawdown spell in trading days
    longest = cur = 0
    for v in in_dd:
        cur = cur + 1 if v else 0
        longest = max(longest, cur)
    return {"max_drawdown": float(dd.min()), "max_dd_date": str(dd.idxmin().date()) if len(dd) else None,
            "longest_drawdown_days": int(longest), "time_in_drawdown": float(in_dd.mean())}


def full_stats(out: pd.DataFrame, spy: pd.Series) -> dict:
    from statarb.statistics.metrics import bootstrap_sharpe_ci, summary_table
    net = out["net_ret"]
    s = summary_table(net)
    g = summary_table(out["gross_ret"])
    lo, hi, _ = bootstrap_sharpe_ci(net.to_numpy(), n_boot=1000, block_mean=10, seed=7)
    sp = spy.reindex(out.index).fillna(0.0)
    beta = float(np.polyfit(sp, net, 1)[0]) if sp.std() > 0 else None
    ne = out["net_exposure"].shift(1).fillna(0.0)
    comp = (ne * sp)
    cost_cols = ["commission", "fees", "spread", "impact", "borrow"]
    d = {"net": s, "gross": g, "sharpe_ci95_ann": [lo * np.sqrt(252), hi * np.sqrt(252)],
         "beta_to_spy": beta, "market_component_share": float(comp.sum() / out["gross_ret"].sum()) if abs(out["gross_ret"].sum()) > 1e-9 else None,
         "net_sharpe_ex_market": summary_table(net - comp)["sharpe_ann"],
         "avg_gross_exposure": float(out["gross_exposure"].mean()), "avg_net_exposure": float(out["net_exposure"].mean()),
         "net_exposure_std": float(out["net_exposure"].std()), "turnover_per_day": float(out["turnover"].mean()),
         "cost_bp_per_day": {c: float(out[c].mean() * 1e4) for c in cost_cols if c in out},
         "cost_bp_total": float(out[cost_cols].sum(axis=1).mean() * 1e4),
         "yearly_net": {str(y): float(v) for y, v in net.groupby(net.index.year).sum().items()},
         "yearly_sharpe": {str(y): (float(v.mean() / v.std() * np.sqrt(252)) if v.std() > 0 and len(v) > 20 else None) for y, v in net.groupby(net.index.year)},
         "monthly_net": {f"{k[0]}-{k[1]:02d}": float(v) for k, v in net.groupby([net.index.year, net.index.month]).sum().items()},
         "best_day": [str(net.idxmax().date()), float(net.max())], "worst_day": [str(net.idxmin().date()), float(net.min())],
         "pct_positive_months": float((net.groupby([net.index.year, net.index.month]).sum() > 0).mean()),
         **drawdown_stats(net)}
    return d


def main():
    from statarb.backtest.run_strategy import run
    from statarb.config import REPO_ROOT
    from statarb.data.load import wide
    from statarb.research import robustness
    from statarb.research.dev_grid import OUT as GRID_OUT, load_feats
    from statarb.research.run_post_audit import DEV_END, DIAG, PREREG_DEV_START, VAL
    from statarb.research.select_validate import spec_from_choice

    PA = REPO_ROOT / "results" / "post_audit"
    sels = {"prereg_2013": json.load(open(PA / "selection_prereg_2013.json", encoding="utf-8")),
            "full_2005": json.load(open(PA / "selection_full_2005.json", encoding="utf-8"))}
    dev_start = {"prereg_2013": PREREG_DEV_START, "full_2005": "2005-01-03"}
    sel = {f"{fam}@{tag}": ch for tag, s_ in sels.items() for fam, ch in s_.items()}
    feats = load_feats()
    spy = wide("adj_close")["SPY"].pct_change()
    cap = json.load(open(REPO_ROOT / "results" / "dev" / "capacity_curve_full.json")).get("primary_capital", 1e6)
    res = {"generated_utc": pd.Timestamp.utcnow().isoformat(), "dev_window": [PREREG_DEV_START, DEV_END], "val_window": list(VAL),
           "diagnostic_window": list(DIAG), "capital": cap, "families": {}}
    t0 = time.time()
    for key, ch in sel.items():
        fam, tag = key.split("@")
        DSTART = dev_start[tag]
        fr = {"selected_id": ch["id"], "params": ch["params"], "multiple_testing": ch["multiple_testing"], "dev_window": [DSTART, DEV_END], "profiles": {}}
        for prof in ("market_maker", "prime_brokered_fund"):
            pr = {}
            for wname, (a, b) in (("dev", (DSTART, DEV_END)), ("val", VAL), ("diag_2023_2026", DIAG)):
                spec = spec_from_choice(ch, a, b, cap, f"PAF_{key}_{prof}_{wname}")
                spec.cost_profile = prof
                out, s = run(spec, feats, write=False)
                out.to_csv(PA / f"daily_full_{key}_{prof}_{wname}.csv")
                pr[wname] = full_stats(out, spy)
                LOG(f"{key} {prof} {wname}: net SR {pr[wname]['net']['sharpe_ann']:.2f} ann {pr[wname]['net']['ann_return']:.3f} vol {pr[wname]['net']['ann_vol']:.3f} maxDD {pr[wname]['max_drawdown']:.3f}")
            # robustness (DEV+VAL) under this profile
            robustness.OUT = PA / f"robustness_{prof}_{tag}"
            base = spec_from_choice(ch, None, None, cap, f"PAF_rob_{key}_{prof}")
            base.cost_profile = prof
            t = time.time()
            kt = robustness.run_suite(base, fam, DSTART, VAL[1])
            pr["kill_tests"] = kt.to_dict(orient="records")
            LOG(f"{key} {prof} robustness in {time.time()-t:.0f}s")
            rows = []
            for c in (1e6, 5e6, 2e7, 5e7, 1e8):
                sp = spec_from_choice(ch, DSTART, DEV_END, c, f"PAF_cap_{key}_{prof}_{int(c)}")
                sp.cost_profile = prof
                out, s = run(sp, feats, write=False)
                rows.append({"capital_$M": c / 1e6, "gross_SR": s["gross"]["sharpe_ann"], "net_SR": s["net"]["sharpe_ann"], "net_ann": s["net"]["ann_return"],
                             "impact_bp": float(out["impact"].mean() * 1e4), "total_bp": s["cost_bp_per_day"]})
            pr["capacity"] = rows
            fr["profiles"][prof] = pr
        res["families"][key] = fr
        with open(PA / "full_metrics.json", "w", encoding="utf-8") as f:
            json.dump(res, f, indent=1, default=float)
    LOG(f"FULL METRICS DONE in {time.time()-t0:.0f}s")


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
    main()
