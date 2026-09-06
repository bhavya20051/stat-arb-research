"""Post-audit re-analysis (2026-09-06), run after the red-team review (reports/RED_TEAM_AUDIT.md).

What it does, in order:
  1. rebuild the closing-auction feature panels with the repaired code (ex-ante 15:45 eligibility, dividend basis);
  2. rerun the full 140-candidate grid under the market-maker profile on (a) the window actually used before the audit
     (2005-01-03 -> 2018-12-14) and (b) the PRE-REGISTERED window (first date with >= 80% intraday coverage of the
     point-in-time universe over a trailing 60-day window: 2013-10-23 -> 2018-12-14);
  3. apply the unchanged selection rule to each grid; run the one-shot validation window (2019-01-02 -> 2022-12-15)
     for each selected configuration under both cost profiles;
  4. run the selected configurations over 2023-01-03 -> 2026-08-31 as a POST-AUDIT DIAGNOSTIC. This is NOT a holdout:
     the locked holdout (results/holdout, frozen 2026-09-06 04:57 UTC) was spent before the audit and is left untouched;
     the 2023-2026 numbers here are reported only to show whether the repairs change the sign of the conclusion;
  5. robustness suite, era decomposition (yearly Sharpe, ex-stress-years), realized exposures, LOC fill statistics and
     the capacity curve by cost profile for the primary (pre-registered-window) configuration.
Every figure is written to results/post_audit/ and the registry receives one diagnostic row per step.
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

PREREG_DEV_START = "2013-10-23"   # first date with trailing-60-day intraday coverage >= 0.80 (strict PIT denominator)
FULL_DEV_START = "2005-01-03"
DEV_END = "2018-12-14"
VAL = ("2019-01-02", "2022-12-15")
DIAG = ("2023-01-03", "2026-08-31")


def _sr(x: pd.Series) -> float:
    x = x.dropna()
    return float(x.mean() / x.std(ddof=1) * np.sqrt(252)) if len(x) > 20 and x.std(ddof=1) > 0 else float("nan")


def era_table(r: pd.Series) -> dict:
    out = {"yearly_sr": {str(y): round(_sr(g), 2) for y, g in r.groupby(r.index.year)},
           "yearly_ret": {str(y): round(float(g.sum()), 4) for y, g in r.groupby(r.index.year)}}
    yrs = r.index.year
    out["sr_full"] = round(_sr(r), 3)
    out["sr_ex_2008"] = round(_sr(r[yrs != 2008]), 3)
    out["sr_ex_2020_2021"] = round(_sr(r[~np.isin(yrs, [2020, 2021])]), 3)
    out["sr_ex_best_day"] = round(_sr(r.drop(r.idxmax())), 3) if len(r) > 30 else None
    out["sr_2005_2011"] = round(_sr(r[yrs <= 2011]), 3)
    out["sr_2012_2018"] = round(_sr(r[(yrs >= 2012) & (yrs <= 2018)]), 3)
    return out


def exposures(out: pd.DataFrame) -> dict:
    return {"gross_mean": round(float(out["gross_exposure"].mean()), 3), "net_mean": round(float(out["net_exposure"].mean()), 3),
            "net_std": round(float(out["net_exposure"].std()), 3), "net_abs_max": round(float(out["net_exposure"].abs().max()), 3),
            "turnover": round(float(out["turnover"].mean()), 3)}


def market_component(out: pd.DataFrame, spy: pd.Series) -> dict:
    """Share of cumulative gross P&L explained by realized net exposure x next-day SPY return (audit F1 decomposition)."""
    ne = out["net_exposure"].shift(1)
    s = spy.reindex(out.index).fillna(0.0)
    comp = (ne * s).fillna(0.0)
    g = out["gross_ret"]
    return {"cum_gross": round(float(g.sum()), 4), "cum_market_component": round(float(comp.sum()), 4),
            "share": round(float(comp.sum() / g.sum()), 3) if abs(g.sum()) > 1e-9 else None,
            "beta_to_spy": round(float(np.polyfit(s, g, 1)[0]), 4) if s.std() > 0 else None,
            "net_sr_ex_market": round(_sr(out["net_ret"] - comp), 3)}


def main(rebuild: bool = True):
    from statarb.backtest.run_strategy import run
    from statarb.config import REPO_ROOT, load_config
    from statarb.data.load import wide
    from statarb.research import robustness
    from statarb.research.dev_grid import OUT as GRID_OUT, load_feats, run_grid
    from statarb.research.registry import record, register
    from statarb.research.select_validate import select, spec_from_choice
    from statarb.statistics.metrics import bootstrap_sharpe_ci, psr

    PA = REPO_ROOT / "results" / "post_audit"
    PA.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    if rebuild:
        from statarb.features.build_moc import build
        build()
        LOG(f"features_moc rebuilt in {time.time()-t0:.0f}s")
    feats = load_feats()
    LOG(f"delisting events wired: {len(feats.get('delist', {}))}; eligible/day {feats['eligible_moc'].sum(axis=1).mean():.0f}")
    spy = wide("adj_close")["SPY"].pct_change()

    windows = {"prereg_2013": PREREG_DEV_START, "full_2005": FULL_DEV_START}
    results = {"generated_utc": pd.Timestamp.utcnow().isoformat(), "dev_windows": windows, "families": {}}
    selections = {}
    sel_path = REPO_ROOT / "results" / "validation" / "selection.json"
    sel_backup = sel_path.read_bytes() if sel_path.exists() else None   # pre-audit selection = frozen holdout provenance
    for tag, start in windows.items():
        t = time.time()
        df = run_grid(dev_end=DEV_END, write_rows=False, cost_profile="market_maker", dev_start=start, tag=f"postaudit_{tag}", feats=feats)
        LOG(f"grid {tag} done in {time.time()-t:.0f}s; top:\n" + df.head(5).to_string(index=False))
        # selection rule unchanged; point it at this grid's files
        rets_path = GRID_OUT / f"grid_net_returns_postaudit_{tag}.parquet"
        orig = pd.read_parquet(GRID_OUT / "grid_net_returns.parquet") if (GRID_OUT / "grid_net_returns.parquet").exists() else None
        pd.read_parquet(rets_path).to_parquet(GRID_OUT / "grid_net_returns.parquet")   # select() reads this fixed name
        try:
            choices = select(GRID_OUT / f"grid_results_postaudit_{tag}.csv")
        finally:
            if orig is not None:
                orig.to_parquet(GRID_OUT / "grid_net_returns.parquet")
            sel_path.replace(PA / f"selection_{tag}.json")
            if sel_backup is not None:
                sel_path.write_bytes(sel_backup)
        selections[tag] = choices
        LOG(f"selection {tag}: " + ", ".join(f"{f}: {c['id']} (DEV net SR {c['dev']['net_sr']:.2f}, DSR {c['multiple_testing']['dsr']:.2f})" for f, c in choices.items()))
    cap = json.load(open(REPO_ROOT / "results" / "dev" / "capacity_curve_full.json")).get("primary_capital", 1e6)

    for tag, choices in selections.items():
        for fam, ch in choices.items():
            key = f"{fam}@{tag}"
            fr = {"selected_id": ch["id"], "params": ch["params"], "dev": {"net_sr": ch["dev"]["net_sr"], "gross_sr": ch["dev"]["gross_sr"],
                  "net_ann": ch["dev"]["net_ann"], "max_dd": ch["dev"]["max_dd"], "turnover": ch["dev"]["turnover"]},
                  "multiple_testing": ch["multiple_testing"]}
            grid_rets = pd.read_parquet(GRID_OUT / f"grid_net_returns_postaudit_{tag}.parquet")[ch["id"]]
            fr["dev_era"] = era_table(grid_rets)
            for prof in ("market_maker", "prime_brokered_fund"):
                for wname, (a, b) in (("val", VAL), ("diag_2023_2026", DIAG)):
                    spec = spec_from_choice(ch, a, b, cap, f"PA_{fam}_{tag}_{prof}_{wname}")
                    spec.cost_profile = prof
                    out, s = run(spec, feats, write=False)
                    out.to_csv(PA / f"daily_{fam}_{tag}_{prof}_{wname}.csv")
                    r = out["net_ret"].to_numpy()
                    lo, hi, _ = bootstrap_sharpe_ci(r, n_boot=1000, block_mean=10, seed=7)
                    fr[f"{wname}_{prof}"] = {"net_sr": s["net"]["sharpe_ann"], "gross_sr": s["gross"]["sharpe_ann"], "net_ann": s["net"]["ann_return"],
                                             "net_vol": s["net"]["ann_vol"], "max_dd": s["net"]["max_drawdown"], "turnover": s["avg_turnover"],
                                             "cost_bp": s["cost_bp_per_day"], "sharpe_ci95": [lo * np.sqrt(252), hi * np.sqrt(252)],
                                             "psr_vs_zero": float(psr(r)), "era": era_table(out["net_ret"]), "exposures": exposures(out),
                                             "market_component": market_component(out, spy)}
                    LOG(f"{key} {prof} {wname}: net SR {s['net']['sharpe_ann']:.2f} gross {s['gross']['sharpe_ann']:.2f} ann {s['net']['ann_return']:.3f} net_std {fr[f'{wname}_{prof}']['exposures']['net_std']:.3f}")
            results["families"][key] = fr
    with open(PA / "post_audit_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=1, default=float)

    # ---- primary = pre-registered window, rank reversal: robustness, LOC fill stats, capacity by profile
    prim = selections["prereg_2013"].get("rank_reversal") or selections["full_2005"].get("rank_reversal")
    prim_tag = "prereg_2013" if "rank_reversal" in selections["prereg_2013"] else "full_2005"
    if prim is not None:
        robustness.OUT = PA / "robustness"
        spec = spec_from_choice(prim, None, None, cap, "PA_rob")
        t = time.time()
        kt = robustness.run_suite(spec, "rank_reversal", windows[prim_tag], VAL[1])
        LOG(f"robustness done in {time.time()-t:.0f}s\n" + kt.to_string(index=False))
        # LOC fill statistics on the DEV+VAL window
        from statarb.backtest.run_strategy import build_weights
        from statarb.execution.limit_orders import loc_fills
        from statarb.features.build_moc import load_moc
        spec2 = replace(spec, start=windows[prim_tag], end=VAL[1])
        w = build_weights(spec2, feats).loc[spec2.start: spec2.end]
        syms = list(w.columns)
        ac = wide("adj_close").reindex(index=w.index, columns=syms)
        p1545 = load_moc("p1545").reindex(index=w.index, columns=syms)
        lb = load_moc("last_bar_close").reindex(index=w.index, columns=syms)
        sig_i = (lb / p1545 - 1.0).abs().rolling(60, min_periods=20).mean().shift(1)
        beta_lag = feats["beta"].reindex(index=w.index, columns=syms).shift(1)
        fill, w_eff = loc_fills(w, p1545, lb, ac, sig_i, spec2.limit_delta, hedge_symbol="SPY", beta=beta_lag, return_effective=True)
        stock = [s for s in syms if s != "SPY"]
        held_prev = w_eff[stock].shift(1).fillna(0.0)
        entry = ((w[stock] > held_prev) & (w[stock] > 0)) | ((w[stock] < held_prev) & (w[stock] < 0))
        filled = entry & fill[stock].notna()
        results["loc_fill_stats"] = {"entries": int(entry.sum().sum()), "fill_rate": round(float(filled.sum().sum() / max(entry.sum().sum(), 1)), 3),
                                     "target_gross_mean": round(float(w[stock].abs().sum(axis=1).mean()), 3), "effective_gross_mean": round(float(w_eff[stock].abs().sum(axis=1).mean()), 3),
                                     "effective_net_std": round(float(w_eff.sum(axis=1).std()), 4)}
        LOG("LOC fill stats " + json.dumps(results["loc_fill_stats"]))
        rows = []
        for prof in ("market_maker", "prime_brokered_fund"):
            for c in (1e6, 5e6, 2e7, 5e7, 1e8):
                sp = spec_from_choice(prim, windows[prim_tag], DEV_END, c, f"PA_cap_{prof}_{int(c)}")
                sp.cost_profile = prof
                out, s = run(sp, feats, write=False)
                rows.append({"profile": prof, "capital_$M": c / 1e6, "gross_SR": round(s["gross"]["sharpe_ann"], 2), "net_SR": round(s["net"]["sharpe_ann"], 2),
                             "net_ann": round(s["net"]["ann_return"], 4), "impact_bp": round(float(out["impact"].mean() * 1e4), 2), "total_bp": round(s["cost_bp_per_day"], 2)})
        capdf = pd.DataFrame(rows)
        capdf.to_csv(PA / "capacity_curve_by_profile.csv", index=False)
        LOG("capacity by profile:\n" + capdf.to_string(index=False))
        results["primary"] = {"tag": prim_tag, "id": prim["id"]}
    with open(PA / "post_audit_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=1, default=float)
    try:
        register("AUDIT-1", "diagnostic", hypothesis="Post-audit re-analysis after red-team findings F1-F4, F9, F15 (hedge executed MOC on the filled book, ex-ante 15:45 eligibility, LOC entries vs held weights on the official close, dividend basis, delisting wiring); selection re-run on the pre-registered DEV window and on the 2005 window; 2023-2026 rerun is a labelled diagnostic, not a holdout",
                 train_period=f"{PREREG_DEV_START} -> {DEV_END} (pre-registered) and {FULL_DEV_START} -> {DEV_END}", validation_period=f"{VAL[0]} -> {VAL[1]}; diagnostic {DIAG[0]} -> {DIAG[1]}",
                 expected_result="repairs remove the market-timing component; conclusion unchanged (no economically meaningful edge)", falsification_condition="n/a (diagnostic)")
    except ValueError:
        pass
    summ = "; ".join(f"{k}: DEV {v['dev']['net_sr']:.2f} VAL {v['val_market_maker']['net_sr']:.2f} 2023-26 {v['diag_2023_2026_market_maker']['net_sr']:.2f}" for k, v in results["families"].items())
    record("AUDIT-1", summ, "diagnostic recorded")
    LOG(f"POST-AUDIT DONE in {time.time()-t0:.0f}s")


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
    main(rebuild=os.environ.get("PA_REBUILD", "1") == "1")
