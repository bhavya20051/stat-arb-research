"""Fixed selection rule on the DEV grid, multiple-testing statistics, and the one-shot VALIDATION run.

Selection rule (pre-specified in the plan, section 8 and dev_grid.py):
  among candidates of a strategy family (rank reversal / event reversal / earnings drift), maximise DEV net Sharpe
  subject to avg gross exposure <= gross_max, avg turnover <= 2.5, and neighbour stability: the mean net Sharpe of
  the candidates that differ in exactly one grid parameter must be >= 0.5 * the winner's (a winner surrounded by
  failures is rejected in favour of the next best). Ties -> lower turnover.
Multiple testing: PSR, DSR (N = number of candidates in the family), CSCV/PBO over the family's net-return matrix.
Validation: the chosen configuration is run ONCE on 2019-01-02 -> 2022-12-15 with identical parameters.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from statarb.backtest.run_strategy import StrategySpec, run
from statarb.config import REPO_ROOT, load_config
from statarb.research.dev_grid import OUT as GRID_OUT, load_feats
from statarb.research.registry import record, register
from statarb.statistics.metrics import bootstrap_sharpe_ci, dsr, pbo_cscv, psr, sharpe, summary_table

VAL_OUT = REPO_ROOT / "results" / "validation"


def family_of(row: pd.Series) -> str:
    if row.get("signal") == "earnings_drift":
        return "earnings_drift"
    if row.get("construction") == "event":
        return "event_reversal"
    return "rank_reversal"


def neighbours(df: pd.DataFrame, row: pd.Series, params: list[str]) -> pd.DataFrame:
    same = np.ones(len(df), dtype=bool)
    diff_count = np.zeros(len(df), dtype=int)
    for p in params:
        d = (df[p].astype(str) != str(row[p])).to_numpy()
        diff_count += d
    return df[(diff_count == 1)]


def select(grid_csv=None, gross_max: float = 3.0, max_turnover: float = 2.5) -> dict:
    df = pd.read_csv(grid_csv or GRID_OUT / "grid_results.csv")
    if "signal" not in df:
        df["signal"] = "reversal"
    if "construction" not in df:
        df["construction"] = "quantile"
    df["family"] = df.apply(family_of, axis=1)
    rets = pd.read_parquet(GRID_OUT / "grid_net_returns.parquet")
    choices = {}
    for fam, g in df.groupby("family"):
        params = [c for c in ("lookback", "holding", "n_deciles", "entry_z", "vix_gate", "exec") if c in g and g[c].nunique() > 1]
        ok = g[(g["gross_exp"] <= gross_max) & (g["turnover"] <= max_turnover)].sort_values(["net_sr", "turnover"], ascending=[False, True])
        chosen = None
        for _, row in ok.iterrows():
            nb = neighbours(g, row, params)
            if len(nb) == 0 or nb["net_sr"].mean() >= 0.5 * row["net_sr"]:
                chosen = row
                break
        if chosen is None:
            continue
        # multiple-testing statistics over the family
        ids = [i for i in g["id"] if i in rets.columns]
        M = rets[ids].dropna(how="all").fillna(0.0)
        fam_sharpes = np.array([sharpe(M[i].to_numpy()) for i in ids])
        r_best = M[chosen["id"]].to_numpy()
        stats = {
            "n_candidates": len(ids),
            "dev_net_sharpe_ann": float(chosen["net_sr"]),
            "psr_vs_zero": float(psr(r_best)),
            "dsr": float(dsr(r_best, fam_sharpes)),
            "pbo_cscv": float(pbo_cscv(M.to_numpy(), n_blocks=16 if len(M) > 2000 else 8)["pbo"]) if len(ids) >= 3 else None,
        }
        choices[fam] = {"id": chosen["id"], "params": {p: chosen[p] for p in ("lookback", "holding", "n_deciles", "entry_z", "vix_gate", "exec", "construction", "signal", "drift_volume_bucket", "drift_timing") if p in chosen and pd.notna(chosen[p])},
                        "dev": chosen.to_dict(), "multiple_testing": stats}
    VAL_OUT.mkdir(parents=True, exist_ok=True)
    with open(VAL_OUT / "selection.json", "w", encoding="utf-8") as f:
        json.dump(choices, f, indent=1, default=str)
    return choices


def spec_from_choice(ch: dict, start: str, end: str, capital: float, label: str) -> StrategySpec:
    p = ch["params"]
    ex = str(p.get("exec", "moc"))
    kw = dict(lookback=int(p["lookback"]), holding=int(p["holding"]), vix_gate=str(p.get("vix_gate", "none")),
              execution="loc" if ex.startswith("loc") else "moc", limit_delta=float(ex[3:]) if ex.startswith("loc") else 0.5,
              band=0.0, start=start, end=end, capital=capital, label=label)
    if p.get("construction") == "event":
        kw.update(construction="event", entry_z=float(p["entry_z"]))
    else:
        kw.update(n_deciles=int(p["n_deciles"]))
    if p.get("signal") == "earnings_drift":
        kw.update(signal="earnings_drift")
        # post-review fix (REPORT_REVIEW finding 1): the volume/timing conditioning was silently dropped before 2026-09-06
        for k in ("drift_volume_bucket", "drift_timing"):
            if p.get(k) not in (None, "", "nan") and not (isinstance(p.get(k), float) and np.isnan(p.get(k))):
                kw[k] = str(p[k])
    return StrategySpec(**kw)


def validate(choices: dict, capital: float) -> dict:
    """ONE run per chosen family on the validation window; results written and registered."""
    cfg = load_config("splits")["primary_intraday"]["val"]
    feats = load_feats()
    results = {}
    for fam, ch in choices.items():
        spec = spec_from_choice(ch, cfg["start"], cfg["end"], capital, f"VAL_{fam}")
        out, s = run(spec, feats, write=False)
        out.to_csv(VAL_OUT / f"daily_VAL_{fam}.csv")
        r = out["net_ret"].to_numpy()
        lo, hi, _ = bootstrap_sharpe_ci(r, n_boot=1000, block_mean=10, seed=7)
        s["net"]["sharpe_ci95_ann"] = [lo * np.sqrt(252), hi * np.sqrt(252)]
        s["net"]["psr_vs_zero"] = float(psr(r))
        s["yearly_net"] = {str(y): float(v) for y, v in out["net_ret"].groupby(out.index.year).sum().items()}
        results[fam] = s
        try:
            register(f"VAL-{fam}", "candidate", hypothesis=f"One-shot validation of the DEV-selected {fam} configuration {ch['id']}",
                     parameters=json.dumps(ch["params"], default=str), train_period="DEV", validation_period=f"{cfg['start']} -> {cfg['end']}",
                     expected_result="net Sharpe > 0", falsification_condition="net Sharpe <= 0 (H5)")
        except ValueError:
            pass
        record(f"VAL-{fam}", f"VAL net SR {s['net']['sharpe_ann']:.2f} (95% CI {lo*np.sqrt(252):.2f}..{hi*np.sqrt(252):.2f}), gross SR {s['gross']['sharpe_ann']:.2f}, net ann {s['net']['ann_return']:.3f}, maxDD {s['net']['max_drawdown']:.2f}, turnover {s['avg_turnover']:.2f}, yearly {s['yearly_net']}",
               "PASS" if s["net"]["sharpe_ann"] > 0 else "FAIL (H5 falsified)")
    with open(VAL_OUT / "validation_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=1, default=float)
    return results
