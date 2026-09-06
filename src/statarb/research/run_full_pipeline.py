"""Unattended full-panel pipeline: wait for ingest -> rebuild MOC features -> registered DEV grid -> selection ->
capacity curve for the selected rank configuration -> one-shot validation -> combined book.  Logs to stdout."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import warnings

warnings.filterwarnings("ignore")
LOG = lambda *a: print(time.strftime("%H:%M:%S"), *a, flush=True)


def ingest_running() -> bool:
    try:
        out = subprocess.check_output(["powershell", "-NoProfile", "-Command",
                                       "(Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and $_.CommandLine -like '*statarb.cli*ingest*' -and $_.CommandLine -notlike '*Win32_Process*' } | Measure-Object).Count"],
                                      text=True, timeout=60)
        return int(out.strip() or "0") > 0
    except Exception:
        return False


def main():
    while ingest_running():
        LOG("waiting for ingest to finish ...")
        time.sleep(120)
    LOG("ingest finished")
    from statarb.features.build_moc import build
    t = time.time()
    f = build()
    LOG(f"MOC features rebuilt on full panel in {time.time()-t:.0f}s; symbols {f['score_moc_k1'].shape[1]}; eligible/day (DEV) {f['eligible_moc'].loc[:'2018-12-14'].sum(axis=1).mean():.0f}")
    from statarb.research.dev_grid import run_grid
    t = time.time()
    df = run_grid(write_rows=True)
    LOG(f"grid done in {time.time()-t:.0f}s")
    print(df.head(15).to_string(index=False), flush=True)
    from statarb.research.select_validate import select, spec_from_choice, validate
    from statarb.backtest.run_strategy import run
    from statarb.research.dev_grid import load_feats
    choices = select()
    LOG("selection: " + json.dumps({k: v["id"] for k, v in choices.items()}))
    for k, v in choices.items():
        LOG(f"  {k}: {v['multiple_testing']}")
    # capacity curve for the selected rank configuration (CAP-1 rule -> primary capital)
    feats = load_feats()
    cap_choice = 5e6
    if "rank_reversal" in choices:
        curve = {}
        for cap in (1e6, 5e6, 2e7, 5e7, 1e8, 2e8):
            spec = spec_from_choice(choices["rank_reversal"], None, "2018-12-14", cap, f"capacity_full_{int(cap)}")
            out, s = run(spec, feats, write=True)
            curve[cap] = s["net"]["sharpe_ann"]
            LOG(f"  capacity ${cap/1e6:.0f}M: net SR {s['net']['sharpe_ann']:.2f} cost {s['cost_bp_per_day']:.2f} bp")
        mx = max(curve.values())
        cap_choice = max(c for c, v in curve.items() if v >= 0.9 * mx)
        LOG(f"CAP-1 primary capital = ${cap_choice/1e6:.0f}M")
        with open("results/dev/capacity_curve_full.json", "w") as fh:
            json.dump({"curve": curve, "primary_capital": cap_choice}, fh, indent=1)
    res = validate(choices, cap_choice)
    for k, s in res.items():
        LOG(f"VAL {k}: net SR {s['net']['sharpe_ann']:.2f} CI {s['net']['sharpe_ci95_ann']} gross {s['gross']['sharpe_ann']:.2f} net ann {s['net']['ann_return']:.3f} maxDD {s['net']['max_drawdown']:.2f} yearly {s['yearly_net']}")
    from statarb.research.combine import run as combine
    LOG("combined book: " + json.dumps(combine(), default=float)[:800])
    LOG("PIPELINE DONE")


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
    main()
