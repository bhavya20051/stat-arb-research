"""Stage 3b: rerun robustness with the corrected cost stress -> freeze -> locked holdout batch (once) -> report."""

from __future__ import annotations

import json
import os
import time
import warnings

warnings.filterwarnings("ignore")
LOG = lambda *a: print(time.strftime("%H:%M:%S"), *a, flush=True)


def main():
    from statarb.config import REPO_ROOT, load_config
    from statarb.research.select_validate import VAL_OUT, spec_from_choice
    from statarb.research.robustness import run_suite
    choices = json.load(open(VAL_OUT / "selection.json", encoding="utf-8"))
    val = json.load(open(VAL_OUT / "validation_results.json", encoding="utf-8"))
    cap = json.load(open(REPO_ROOT / "results" / "dev" / "capacity_curve_full.json")).get("primary_capital", 5e6)
    dev_cfg = load_config("splits")["primary_intraday"]["dev"]
    val_cfg = load_config("splits")["primary_intraday"]["val"]
    for fam, ch in choices.items():
        if val.get(fam, {}).get("net", {}).get("sharpe_ann", 0) <= 0:
            LOG(f"robustness skipped for {fam}")
            continue
        t = time.time()
        kt = run_suite(spec_from_choice(ch, None, None, cap, f"rob_{fam}"), fam, dev_cfg["start"] or "2005-01-01", val_cfg["end"])
        LOG(f"robustness {fam} done in {time.time()-t:.0f}s\n" + kt[["variant", "net_sr", "net_ann", "max_dd", "cost_bp"]].to_string(index=False))
    from statarb.research.holdout import freeze, run_holdout
    frozen = freeze()
    LOG("frozen: " + ", ".join(f"{k}: {v['status']}" for k, v in frozen["families"].items()))
    t = time.time()
    res = run_holdout(frozen)
    for fam, r in res["families"].items():
        if r.get("status") == "run":
            b = r["variants"]["base"]
            LOG(f"HOLDOUT {fam}: net SR {b['net_sharpe']:.2f} CI {b['sharpe_ci95']} PSR {b['psr_vs_zero']:.3f} gross {b['gross_sharpe']:.2f} net ann {b['net_ann']:.3f} maxDD {b['max_dd']:.2f} yearly {b['yearly_net']}")
            for v in ("costs_x1.5", "costs_x2.0", "slippage_+5bp", "signal_lag_+1day", "profile_prime_brokered_fund", "gross_max_5.0", "other_execution"):
                LOG(f"    {v}: net SR {r['variants'][v]['net_sharpe']:.2f}")
        else:
            LOG(f"HOLDOUT {fam}: {r.get('status')}")
    LOG(f"holdout batch done in {time.time()-t:.0f}s")
    from statarb.reporting.html_report import build_report
    LOG("report: " + str(build_report()))
    LOG("STAGE 3B DONE")


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
    main()
