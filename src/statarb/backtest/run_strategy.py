"""Strategy runner: features -> masks -> ranked weights -> constraints -> engine -> summary.

Execution models:
  moo : decision at close t, fill at open t+1 (lag=1), fill price = split-adjusted open (real shares via raw open).
  moc : decision at 15:40 t, fill at close t (lag=0). Requires the 15-min bar file (decision-time price) — when the
        intraday panel is not yet available, `moc_daily_proxy=True` forms the signal from t-1 close data only
        (strictly ex-ante, more conservative) and fills at close t.
All P&L is computed on total-return-consistent prices: fill_price series = adj_close * (close_raw/close) scaling
is avoided by using the dividend-adjusted series for returns and raw prices only for share counts/commissions.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import numpy as np
import pandas as pd

from statarb.backtest.engine import EngineInputs, run_backtest
from statarb.config import REPO_ROOT, load_config
from statarb.data.load import wide
from statarb.execution.costs import CostParams
from statarb.features.build import load_feature
from statarb.portfolio.construct import apply_no_trade_band, beta_hedge, cap_weights, dollar_neutralize, enforce_limits, vol_target
from statarb.signals.reversal import decile_weights
from statarb.statistics.metrics import summary_table


@dataclass
class StrategySpec:
    lookback: int = 1
    holding: int = 1
    execution: str = "moo"            # moo | moc
    n_deciles: int = 10
    max_name: float = 0.02
    vol_target_annual: float | None = 0.10
    gross: float = 1.0                # gross before vol targeting (0.5 long + 0.5 short)
    band: float = 0.002
    turnover_bucket: str | None = None  # None | low | high (sleeves)
    vix_gate: str = "none"            # none | step | linear
    capital: float = 1_000_000
    start: str | None = None
    end: str | None = None
    label: str = "base"


def cost_params_from_config(execution: str, multiplier: float = 1.0, extra_bp: float = 0.0) -> CostParams:
    c = load_config("costs")
    return CostParams(
        commission_per_share=c["commissions"]["per_share_usd"],
        min_commission_per_order=c["commissions"]["min_per_order_usd"],
        max_commission_pct=c["commissions"]["max_pct_of_trade_value"],
        sec_fee_rate=c["regulatory_fees_on_sells"].get("sec_fee_rate_default", 27.8e-6),
        finra_taf_per_share=c["regulatory_fees_on_sells"].get("finra_taf_per_share") or 0.000166,
        finra_taf_max=c["regulatory_fees_on_sells"].get("finra_taf_max_per_trade") or 8.30,
        borrow_annual=c["short_borrow"]["general_collateral_annual"],
        impact_k=c["impact"]["k"],
        spread_multiplier=multiplier,
        extra_slippage_bp=extra_bp,
        pay_spread=(execution not in ("moc", "moo")),
    )


def build_weights(spec: StrategySpec, feats: dict) -> pd.DataFrame:
    score = feats[f"score_k{spec.lookback}"].where(feats["eligible"])
    if spec.turnover_bucket:
        tq = feats["abn_turnover"].rank(axis=1, pct=True)
        m = tq <= 1 / 3 if spec.turnover_bucket == "low" else tq > 2 / 3
        score = score.where(m)
    if spec.turnover_bucket == "high":
        score = -score  # continuation sleeve: buy high-turnover winners
    w = decile_weights(score, n_deciles=spec.n_deciles) * (spec.gross / 2.0)
    if spec.holding > 1:  # overlapping tranches: average of the last `holding` days' target books
        w = w.rolling(spec.holding, min_periods=1).mean()
    w = cap_weights(w, spec.max_name)
    if "beta" in feats:
        w = beta_hedge(w, feats["beta"], "SPY")
    if spec.vol_target_annual:
        port_ret_proxy = (w.shift(1) * feats["ret"].reindex_like(w).fillna(0)).sum(axis=1)
        est = port_ret_proxy.rolling(60, min_periods=20).std(ddof=1).shift(1) * np.sqrt(252)
        w = vol_target(w, est, spec.vol_target_annual, max_lever=2.0)
    if spec.vix_gate != "none" and "vix" in feats:
        v = feats["vix"].shift(1).reindex(w.index)
        g = (v > v.rolling(252, min_periods=60).quantile(2 / 3)).astype(float) + 1.0 if spec.vix_gate == "step" else (v / v.rolling(252, min_periods=60).mean()).clip(0.5, 2.0)
        w = w.mul(g.fillna(1.0), axis=0)
    w = enforce_limits(w, gross_max=2.0, net_abs_max=0.05)
    if spec.band:
        w = apply_no_trade_band(w, spec.band)
    return w.fillna(0.0)


def run(spec: StrategySpec, feats: dict | None = None, cost_multiplier: float = 1.0, extra_bp: float = 0.0, write: bool = True) -> tuple[pd.DataFrame, dict]:
    if feats is None:
        feats = {k: load_feature(k) for k in ("ret", "eligible", "abn_turnover", f"score_k{spec.lookback}")}
    w = build_weights(spec, feats)
    if spec.start or spec.end:
        w = w.loc[spec.start : spec.end]
    syms = [s for s in w.columns]
    adj_close = wide("adj_close").reindex(columns=syms)
    raw_close = wide("close_raw").reindex(columns=syms)
    vol = wide("volume").reindex(columns=syms)
    if spec.execution == "moo":
        adj_open = wide("adj_open").reindex(columns=syms)
        fill = adj_open.reindex(w.index)
        lag = 1
    else:
        fill = adj_close.reindex(w.index)
        lag = 0
    inp = EngineInputs(target_weights=w, fill_price=fill, fill_volume=vol.reindex(w.index), lag=lag,
                       half_spread=(feats["spread"].reindex_like(w) / 2) if "spread" in feats else None,
                       sigma_daily=feats["ret"].rolling(60, min_periods=20).std().shift(1).reindex_like(w) if "ret" in feats else None,
                       adv_shares=vol.rolling(60, min_periods=20).mean().shift(1).reindex(w.index),
                       delist=feats.get("delist"))
    costs = cost_params_from_config(spec.execution, cost_multiplier, extra_bp)
    out = run_backtest(inp, spec.capital, costs)
    summ = {"label": spec.label, "spec": spec.__dict__, "cost_multiplier": cost_multiplier,
            "gross": summary_table(out["gross_ret"]), "net": summary_table(out["net_ret"]),
            "avg_turnover": float(out["turnover"].mean()), "avg_gross_exposure": float(out["gross_exposure"].mean()),
            "avg_net_exposure": float(out["net_exposure"].mean()),
            "cost_bp_per_day": float(1e4 * (out["gross_ret"] - out["net_ret"]).mean())}
    if write:
        d = REPO_ROOT / "results" / "dev"
        d.mkdir(parents=True, exist_ok=True)
        out.to_csv(d / f"daily_{spec.label}.csv")
        with open(d / f"summary_{spec.label}.json", "w", encoding="utf-8") as f:
            json.dump(summ, f, indent=1, default=float)
    return out, summ
