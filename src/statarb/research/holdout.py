"""Phase 14: freeze -> single locked-holdout batch -> immutable results with manifest.

The frozen configuration per family comes from results/validation/selection.json (DEV-selected, VAL-confirmed).
The batch is pre-declared here and executed ONCE: base, costs x1.5, x2.0, +5 bp, signal lag +1 day, fund profile,
gross 2x / 5x, drawdown rule off, other execution. Nothing is re-run afterwards; if research continues, this sample
becomes development data and a new forward sample is required (plan section 13).
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import replace
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import yaml

from statarb.backtest.run_strategy import run
from statarb.config import REPO_ROOT, config_hash, load_config
from statarb.research.dev_grid import load_feats
from statarb.research.registry import record, register
from statarb.research.select_validate import VAL_OUT, spec_from_choice
from statarb.statistics.metrics import bootstrap_sharpe_ci, psr, summary_table

HOLD_OUT = REPO_ROOT / "results" / "holdout"
VARIANTS = ["base", "costs_x1.5", "costs_x2.0", "slippage_+5bp", "signal_lag_+1day", "profile_prime_brokered_fund",
            "gross_max_2.0", "gross_max_5.0", "no_drawdown_rule", "other_execution"]


def freeze() -> dict:
    choices = json.load(open(VAL_OUT / "selection.json", encoding="utf-8"))
    val = json.load(open(VAL_OUT / "validation_results.json", encoding="utf-8"))
    cap = json.load(open(REPO_ROOT / "results" / "dev" / "capacity_curve_full.json")).get("primary_capital", 5e6)
    cfg = load_config("splits")["primary_intraday"]["holdout"]
    frozen = {"frozen_at_utc": datetime.now(timezone.utc).isoformat(), "git": _git(), "config_hash": config_hash("base", "costs", "universe", "splits"),
              "capital": cap, "holdout": cfg, "variants": VARIANTS, "families": {}}
    for fam, ch in choices.items():
        if val.get(fam, {}).get("net", {}).get("sharpe_ann", 0) <= 0:
            frozen["families"][fam] = {"status": "not run: H5 falsified on validation", "params": ch["params"]}
            continue
        frozen["families"][fam] = {"status": "frozen", "id": ch["id"], "params": ch["params"], "val_net_sharpe": val[fam]["net"]["sharpe_ann"]}
    man = REPO_ROOT / "data" / "snapshot_manifest.json"
    frozen["data_snapshot_sha256"] = hashlib.sha256(man.read_bytes()).hexdigest()[:16] if man.exists() else "missing"
    with open(REPO_ROOT / "configs" / "holdout.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(frozen, f, sort_keys=False, default_flow_style=False)
    return frozen


def _git() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, text=True).strip()
    except Exception:
        return "unknown"


def run_holdout(frozen: dict) -> dict:
    HOLD_OUT.mkdir(parents=True, exist_ok=True)
    if (HOLD_OUT / "holdout_results.json").exists():
        raise RuntimeError("holdout already run; results are immutable")
    feats = load_feats()
    h = frozen["holdout"]
    results = {"manifest": {k: frozen[k] for k in ("frozen_at_utc", "git", "config_hash", "capital", "data_snapshot_sha256")},
               "run_at_utc": datetime.now(timezone.utc).isoformat(), "families": {}}
    choices = json.load(open(VAL_OUT / "selection.json", encoding="utf-8"))
    for fam, info in frozen["families"].items():
        if info["status"] != "frozen":
            results["families"][fam] = {"status": info["status"]}
            continue
        base = spec_from_choice(choices[fam], h["start"], h["end"], frozen["capital"], f"HOLDOUT_{fam}")
        fam_res = {}
        for v in VARIANTS:
            spec, mult, extra = base, 1.0, 0.0
            if v == "costs_x1.5":
                mult = 1.5
            elif v == "costs_x2.0":
                mult = 2.0
            elif v == "slippage_+5bp":
                extra = 5.0
            elif v == "signal_lag_+1day":
                spec = replace(base, signal_lag_days=1)
            elif v == "profile_prime_brokered_fund":
                spec = replace(base, cost_profile="prime_brokered_fund")
            elif v == "gross_max_2.0":
                spec = replace(base, gross_max=2.0)
            elif v == "gross_max_5.0":
                spec = replace(base, gross_max=5.0)
            elif v == "no_drawdown_rule":
                spec = replace(base, drawdown_rule=False)
            elif v == "other_execution":
                spec = replace(base, execution="moc" if base.execution == "loc" else "loc")
            out, s = run(spec, feats, cost_multiplier=mult, extra_bp=extra, write=False)
            r = out["net_ret"].to_numpy()
            entry = {"net_sharpe": s["net"]["sharpe_ann"], "gross_sharpe": s["gross"]["sharpe_ann"], "net_ann": s["net"]["ann_return"],
                     "net_vol": s["net"]["ann_vol"], "max_dd": s["net"]["max_drawdown"], "turnover": s["avg_turnover"], "cost_bp": s["cost_bp_per_day"], "n_days": s["net"]["n_days"]}
            if v == "base":
                lo, hi, _ = bootstrap_sharpe_ci(r, n_boot=2000, block_mean=10, seed=2023)
                entry.update({"sharpe_ci95": [lo * np.sqrt(252), hi * np.sqrt(252)], "psr_vs_zero": float(psr(r)),
                              "yearly_net": {str(y): float(x) for y, x in out["net_ret"].groupby(out.index.year).sum().items()},
                              "summary": summary_table(out["net_ret"])})
                out.to_csv(HOLD_OUT / f"daily_HOLDOUT_{fam}.csv")
            fam_res[v] = entry
        results["families"][fam] = {"status": "run", "id": info["id"], "params": info["params"], "holdout_net_sharpe": fam_res["base"]["net_sharpe"],
                                    "holdout_net_ann": fam_res["base"]["net_ann"], "holdout_max_dd": fam_res["base"]["max_dd"], "variants": fam_res}
        try:
            register(f"HOLDOUT-{fam}", "candidate", hypothesis=f"Locked holdout, single run, frozen {info['id']}", parameters=json.dumps(info["params"], default=str),
                     train_period="DEV+VAL frozen", validation_period=f"{h['start']} -> {h['end']}", expected_result="net Sharpe >= 1.2 credible / >= 1.5 strong", falsification_condition="net Sharpe <= 0")
        except ValueError:
            pass
        b = fam_res["base"]
        record(f"HOLDOUT-{fam}", f"net SR {b['net_sharpe']:.2f} (95% CI {b['sharpe_ci95'][0]:.2f}..{b['sharpe_ci95'][1]:.2f}), PSR {b['psr_vs_zero']:.3f}, gross SR {b['gross_sharpe']:.2f}, net ann {b['net_ann']:.3f}, maxDD {b['max_dd']:.2f}, yearly {b['yearly_net']}; costs x1.5 -> {fam_res['costs_x1.5']['net_sharpe']:.2f}, x2 -> {fam_res['costs_x2.0']['net_sharpe']:.2f}",
               "RECORDED (immutable)")
    with open(HOLD_OUT / "holdout_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=1, default=float)
    return results
