"""Development-sample hypothesis tests (H1, H4, H6, H2, H3) — DEV dates only, enforced by the split config.

Runs Fama-MacBeth regressions of forward residual returns on the reversal score, IC-decay curves and decile
spreads; writes tables to results/dev/ and returns a dict for the registry.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from statarb.config import REPO_ROOT, load_config
from statarb.data.load import wide
from statarb.features.build import load_feature
from statarb.statistics.panel import decile_spread, fama_macbeth, forward_return, ic_decay

OUT = REPO_ROOT / "results" / "dev"


def dev_slice(df: pd.DataFrame, sample: str = "secondary_daily") -> pd.DataFrame:
    cfg = load_config("splits")[sample]["dev"]
    start = cfg["start"] or "2005-01-01"
    return df.loc[start : cfg["end"]]


def run(sample: str = "secondary_daily") -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    close = wide("adj_close")
    resid = load_feature("resid")
    elig = load_feature("eligible")
    abn = load_feature("abn_turnover")
    stocks = resid.columns
    px = close[stocks]
    results = {}
    # H1 / H4: FM of forward 1..5 day RAW return on score (residual) and raw-return score
    for k in (1, 3, 5):
        score = dev_slice(load_feature(f"score_k{k}").where(elig), sample)
        raw_score = -(dev_slice(px.pct_change(k).where(elig), sample))
        for h in (1, 3, 5):
            y = dev_slice(forward_return(px, h), sample)
            fm = fama_macbeth(y, {"resid_score": score, "raw_score": raw_score}, min_names=100)
            s = fm.attrs["summary"]
            results[f"FM_k{k}_h{h}"] = {n: s[n] for n in ("resid_score", "raw_score")}
    # decay curve for k=1 and k=3 (H6)
    for k in (1, 3):
        score = dev_slice(load_feature(f"score_k{k}").where(elig), sample)
        ic = ic_decay(score, px, horizons=range(1, 16))
        ic.to_csv(OUT / f"ic_decay_k{k}.csv")
        results[f"ic_decay_k{k}"] = ic["ic_mean"].round(5).to_dict()
        spreads = {h: decile_spread(score, px, h).mean() for h in (1, 2, 3, 5, 10)}
        results[f"decile_spread_k{k}"] = {int(h): float(v) for h, v in spreads.items()}
    # H2: turnover terciles (k=1, h=1)
    score = dev_slice(load_feature("score_k1").where(elig), sample)
    y = dev_slice(forward_return(px, 1), sample)
    a = dev_slice(abn, sample)
    tq = a.rank(axis=1, pct=True)
    for name, m in (("low_turnover", tq <= 1 / 3), ("mid_turnover", (tq > 1 / 3) & (tq <= 2 / 3)), ("high_turnover", tq > 2 / 3)):
        fm = fama_macbeth(y, {"resid_score": score.where(m)}, min_names=50)
        results[f"H2_{name}"] = fm.attrs["summary"]["resid_score"]
    with open(OUT / "dev_analysis.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=1, default=float)
    return results
