"""Rerun only the earnings-drift cells of the post-audit data set after REPORT_REVIEW finding 1 (conditioning params
were dropped by spec_from_choice). Patches results/post_audit/full_metrics.json and post_audit_results.json in place."""
import json, os, time, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from statarb.backtest.run_strategy import run
from statarb.config import REPO_ROOT
from statarb.data.load import wide
from statarb.research import robustness
from statarb.research.dev_grid import load_feats
from statarb.research.run_post_audit import DEV_END, DIAG, PREREG_DEV_START, VAL, era_table, exposures, market_component
from statarb.research.run_post_audit_full import full_stats
from statarb.research.select_validate import spec_from_choice
from statarb.statistics.metrics import bootstrap_sharpe_ci, psr
LOG = lambda *a: print(time.strftime("%H:%M:%S"), *a, flush=True)
PA = REPO_ROOT / "results" / "post_audit"
feats = load_feats(); spy = wide("adj_close")["SPY"].pct_change()
fm = json.load(open(PA / "full_metrics.json")); pa = json.load(open(PA / "post_audit_results.json"))
cap = fm["capital"]; dev_start = {"prereg_2013": PREREG_DEV_START, "full_2005": "2005-01-03"}
for tag in ("prereg_2013", "full_2005"):
    ch = json.load(open(PA / f"selection_{tag}.json"))["earnings_drift"]; key = f"earnings_drift@{tag}"; DSTART = dev_start[tag]
    LOG(key, ch["params"])
    fr = {"selected_id": ch["id"], "params": ch["params"], "multiple_testing": ch["multiple_testing"], "dev_window": [DSTART, DEV_END], "profiles": {}}
    pr_pa = pa["families"][key]
    for prof in ("market_maker", "prime_brokered_fund"):
        pr = {}
        for wname, (a, b) in (("dev", (DSTART, DEV_END)), ("val", VAL), ("diag_2023_2026", DIAG)):
            spec = spec_from_choice(ch, a, b, cap, f"PAF_{key}_{prof}_{wname}"); spec.cost_profile = prof
            out, s = run(spec, feats, write=False); out.to_csv(PA / f"daily_full_{key}_{prof}_{wname}.csv")
            pr[wname] = full_stats(out, spy)
            LOG(f"{key} {prof} {wname}: net SR {pr[wname]['net']['sharpe_ann']:.2f} ann {pr[wname]['net']['ann_return']:.4f} gross_exp {pr[wname]['avg_gross_exposure']:.3f}")
            if wname != "dev":
                out.to_csv(PA / f"daily_earnings_drift_{tag}_{prof}_{wname}.csv")
                r = out["net_ret"].to_numpy(); lo, hi, _ = bootstrap_sharpe_ci(r, n_boot=1000, block_mean=10, seed=7)
                pr_pa[f"{wname}_{prof}"] = {"net_sr": s["net"]["sharpe_ann"], "gross_sr": s["gross"]["sharpe_ann"], "net_ann": s["net"]["ann_return"], "net_vol": s["net"]["ann_vol"],
                                            "max_dd": s["net"]["max_drawdown"], "turnover": s["avg_turnover"], "cost_bp": s["cost_bp_per_day"], "sharpe_ci95": [lo*np.sqrt(252), hi*np.sqrt(252)],
                                            "psr_vs_zero": float(psr(r)), "era": era_table(out["net_ret"]), "exposures": exposures(out), "market_component": market_component(out, spy)}
        robustness.OUT = PA / f"robustness_{prof}_{tag}"
        base = spec_from_choice(ch, None, None, cap, f"PAF_rob_{key}_{prof}"); base.cost_profile = prof
        kt = robustness.run_suite(base, "earnings_drift", DSTART, VAL[1]); pr["kill_tests"] = kt.to_dict(orient="records")
        rows = []
        for c in (1e6, 5e6, 2e7, 5e7, 1e8):
            sp = spec_from_choice(ch, DSTART, DEV_END, c, f"PAF_cap_{key}_{prof}_{int(c)}"); sp.cost_profile = prof
            out, s = run(sp, feats, write=False)
            rows.append({"capital_$M": c/1e6, "gross_SR": s["gross"]["sharpe_ann"], "net_SR": s["net"]["sharpe_ann"], "net_ann": s["net"]["ann_return"], "impact_bp": float(out["impact"].mean()*1e4), "total_bp": s["cost_bp_per_day"]})
        pr["capacity"] = rows; fr["profiles"][prof] = pr
    fm["families"][key] = fr
    json.dump(fm, open(PA / "full_metrics.json", "w"), indent=1, default=float); json.dump(pa, open(PA / "post_audit_results.json", "w"), indent=1, default=float)
LOG("EARNINGS RERUN DONE")
