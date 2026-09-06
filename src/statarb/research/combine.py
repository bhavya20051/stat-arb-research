"""Combined-book test (pre-specified two/multi-sleeve design): equal-risk combination of the surviving families'
validation-period net returns. Run ONLY after validation; uses trailing realized vol (through t-1) for the weights
so the combination itself is ex-ante.  Reports pairwise correlations, per-sleeve and combined Sharpe.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from statarb.config import REPO_ROOT
from statarb.statistics.metrics import bootstrap_sharpe_ci, summary_table

VAL_OUT = REPO_ROOT / "results" / "validation"


def equal_risk_combination(returns: dict[str, pd.Series], vol_window: int = 60, target_vol: float = 0.10) -> pd.DataFrame:
    df = pd.DataFrame(returns).dropna(how="all").fillna(0.0)
    vol = df.rolling(vol_window, min_periods=20).std(ddof=1).shift(1) * np.sqrt(252)
    w = (1.0 / vol.replace(0, np.nan))
    w = w.div(w.sum(axis=1), axis=0).fillna(1.0 / df.shape[1])
    combo = (w * df).sum(axis=1)
    # scale to target vol using trailing realized vol of the combination (ex-ante)
    cv = combo.rolling(vol_window, min_periods=20).std(ddof=1).shift(1) * np.sqrt(252)
    scaled = combo * (target_vol / cv.replace(0, np.nan)).clip(upper=3.0).fillna(1.0)
    out = df.copy()
    out["combined_equal_risk"] = combo
    out["combined_vol_targeted"] = scaled
    return out


def run(families: list[str] | None = None) -> dict:
    files = sorted(VAL_OUT.glob("daily_VAL_*.csv"))
    rets = {}
    for f in files:
        fam = f.stem.replace("daily_VAL_", "")
        if families and fam not in families:
            continue
        rets[fam] = pd.read_csv(f, index_col=0, parse_dates=True)["net_ret"]
    if len(rets) < 2:
        return {"note": "fewer than two surviving families; no combination"}
    out = equal_risk_combination(rets)
    res = {"correlations": out[list(rets)].corr().round(3).to_dict(), "sleeves": {}, "combined": {}}
    for k in rets:
        res["sleeves"][k] = summary_table(out[k])
    for k in ("combined_equal_risk", "combined_vol_targeted"):
        s = summary_table(out[k])
        lo, hi, _ = bootstrap_sharpe_ci(out[k].to_numpy(), n_boot=1000, block_mean=10, seed=11)
        s["sharpe_ci95_ann"] = [lo * np.sqrt(252), hi * np.sqrt(252)]
        res["combined"][k] = s
    out.to_csv(VAL_OUT / "combined_book_daily.csv")
    with open(VAL_OUT / "combined_book.json", "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1, default=float)
    return res
