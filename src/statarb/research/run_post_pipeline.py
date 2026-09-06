"""Stage 2 (unattended): after the market-maker pipeline completes -> fund-profile grid -> fund-profile validation of
the selected configurations -> robustness suite per surviving family -> HTML report."""

from __future__ import annotations

import json
import os
import time
import warnings

warnings.filterwarnings("ignore")
LOG = lambda *a: print(time.strftime("%H:%M:%S"), *a, flush=True)
PIPE_LOG = r"C:\Users\bhavy\statarb_data\pipeline_full2.log"


def main():
    while True:
        try:
            if "PIPELINE DONE" in open(PIPE_LOG, encoding="utf-8", errors="ignore").read():
                break
        except FileNotFoundError:
            pass
        LOG("waiting for stage 1 ...")
        time.sleep(120)
    from statarb.config import REPO_ROOT, load_config
    from statarb.research.dev_grid import run_grid, load_feats
    from statarb.research.select_validate import VAL_OUT, spec_from_choice
    from statarb.backtest.run_strategy import run
    from statarb.research.robustness import run_suite
    t = time.time()
    df = run_grid(write_rows=False, cost_profile="prime_brokered_fund")
    LOG(f"fund-profile grid done in {time.time()-t:.0f}s; top:\n" + df.head(8).to_string(index=False))
    choices = json.load(open(VAL_OUT / "selection.json", encoding="utf-8"))
    cap = json.load(open(REPO_ROOT / "results" / "dev" / "capacity_curve_full.json")).get("primary_capital", 5e6)
    cfg = load_config("splits")["primary_intraday"]["val"]
    feats = load_feats()
    fund = {}
    for fam, ch in choices.items():
        spec = spec_from_choice(ch, cfg["start"], cfg["end"], cap, f"VAL_{fam}_fund")
        spec.cost_profile = "prime_brokered_fund"
        out, s = run(spec, feats, write=False)
        out.to_csv(VAL_OUT / f"daily_VAL_{fam}_fund.csv")
        fund[fam] = s
        LOG(f"VAL (fund profile) {fam}: net SR {s['net']['sharpe_ann']:.2f} net ann {s['net']['ann_return']:.3f} cost {s['cost_bp_per_day']:.2f} bp")
    with open(VAL_OUT / "validation_results_fund.json", "w", encoding="utf-8") as f:
        json.dump(fund, f, indent=1, default=float)
    val = json.load(open(VAL_OUT / "validation_results.json", encoding="utf-8"))
    dev_cfg = load_config("splits")["primary_intraday"]["dev"]
    for fam, ch in choices.items():
        if val.get(fam, {}).get("net", {}).get("sharpe_ann", 0) <= 0:
            LOG(f"robustness skipped for {fam}: validation net Sharpe <= 0 (H5 falsified)")
            continue
        t = time.time()
        spec = spec_from_choice(ch, None, None, cap, f"rob_{fam}")
        kt = run_suite(spec, fam, dev_cfg["start"] or "2005-01-01", cfg["end"])
        LOG(f"robustness {fam} done in {time.time()-t:.0f}s\n" + kt.to_string(index=False))
    from statarb.reporting.html_report import build_report
    LOG("report: " + str(build_report()))
    LOG("STAGE 2 DONE")


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
    main()
