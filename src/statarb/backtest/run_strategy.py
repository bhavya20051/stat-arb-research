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
from statarb.portfolio.construct import apply_no_trade_band, beta_hedge, cap_weights, dollar_neutralize, enforce_limits, event_weights, hysteresis_weights, vol_target
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
    signal_lag_days: int = 0          # 1 = conservative daily-only proxy for MOC (signal from t-1 data, fill close t)
    cost_profile: str = "market_maker"
    gross_max: float = 3.0
    drawdown_rule: bool = True
    beta_hedge: bool = True
    sector_neutral: bool = True
    pre_earnings_exclusion: bool = False   # CONS-1: primary OFF (DEV ablation); ON is a robustness variant
    auction_participation: bool = True
    construction: str = "quantile"    # quantile | hysteresis | event
    signal: str = "reversal"          # reversal | earnings_drift (third strategy: go WITH the move on earnings-8-K days)
    drift_volume_bucket: str | None = None   # STRAT-4: high | low abnormal intraday turnover tercile among earnings movers
    drift_timing: str | None = None          # STRAT-5: after_hours | intraday filing timing
    entry_z: float = 2.0
    limit_delta: float = 0.5
    limit_through: float = 0.0005
    enter_pct: float = 0.2
    exit_pct: float = 0.4


def cost_params_from_config(execution: str, multiplier: float = 1.0, extra_bp: float = 0.0, profile: str = "institutional") -> CostParams:
    c = load_config("costs")
    prof = c.get("profiles", {}).get(profile) or c["commissions"]
    return CostParams(
        commission_per_share=prof["per_share_usd"],
        min_commission_per_order=prof["min_per_order_usd"],
        max_commission_pct=prof["max_pct_of_trade_value"],
        sec_fee_rate=prof.get("sec_fee_rate", c["regulatory_fees_on_sells"].get("sec_fee_rate_default", 27.8e-6)),
        finra_taf_per_share=prof.get("finra_taf_per_share", c["regulatory_fees_on_sells"].get("finra_taf_per_share") or 0.000166),
        finra_taf_max=prof.get("finra_taf_max_per_trade", c["regulatory_fees_on_sells"].get("finra_taf_max_per_trade") or 8.30),
        clearing_pct_notional=prof.get("clearing_pct_notional", 0.0),
        borrow_annual=prof.get("borrow_annual", c["short_borrow"]["general_collateral_annual"]),
        impact_k=c["impact"]["k"],
        impact_exponent=c["impact"].get("exponent", 0.5),
        spread_multiplier=multiplier,
        extra_slippage_bp=extra_bp,
        pay_spread=(execution not in ("moc", "moo", "loc", "limit")),  # auction fills and resting limit orders pay no spread
    )


def build_weights(spec: StrategySpec, feats: dict) -> pd.DataFrame:
    intraday_exec = spec.execution in ("moc", "limit", "loc")
    key = f"score_moc_k{spec.lookback}" if intraday_exec and f"score_moc_k{spec.lookback}" in feats else f"score_k{spec.lookback}"
    elig_key = "eligible_moc" if intraday_exec and "eligible_moc" in feats else "eligible"
    elig = feats[elig_key]
    if spec.signal == "earnings_drift":
        elig = feats["eligible_base"] & feats["earnings_flag_1540"].reindex_like(feats["eligible_base"]).fillna(False)
        if spec.drift_volume_bucket and "abn_turnover_1545" in feats:
            a = feats["abn_turnover_1545"].reindex_like(elig).where(elig)
            tq = a.rank(axis=1, pct=True)
            elig = elig & ((tq > 2 / 3) if spec.drift_volume_bucket == "high" else (tq <= 1 / 3)).fillna(False)
        if spec.drift_timing and "earnings_timing_1540" in feats:
            elig = elig & (feats["earnings_timing_1540"].reindex_like(elig) == spec.drift_timing)
    if spec.pre_earnings_exclusion and spec.signal == "reversal" and "expected_earnings" in feats:
        ee = feats["expected_earnings"].reindex_like(elig).fillna(False)
        # exclude if an expected earnings date falls within the next `holding` trading days (known ex ante)
        upcoming = ee.astype(float)
        for k in range(1, spec.holding + 1):
            upcoming = upcoming + ee.shift(-k).astype(float).fillna(0.0)   # ee is an EX-ANTE expected-date panel (built from last year's dates), so looking ahead in it is not lookahead
        elig = elig & (upcoming == 0)
    score = feats[key].where(elig)
    if spec.signal == "earnings_drift":
        score = -score  # continuation: positive residual move -> long
    if spec.turnover_bucket:
        tq = feats["abn_turnover"].rank(axis=1, pct=True)
        m = tq <= 1 / 3 if spec.turnover_bucket == "low" else tq > 2 / 3
        score = score.where(m)
    if spec.turnover_bucket == "high":
        score = -score  # continuation sleeve: buy high-turnover winners
    if spec.construction == "event":
        w = event_weights(score, spec.entry_z, spec.holding, per_side_gross=spec.gross_max / 2.0, max_name=spec.max_name)
    elif spec.construction == "hysteresis":
        w = hysteresis_weights(score, spec.enter_pct, spec.exit_pct, max_hold=spec.holding) * spec.gross
    else:
        w = decile_weights(score, n_deciles=spec.n_deciles) * (spec.gross / 2.0)
        if spec.holding > 1:  # overlapping tranches: average of the last `holding` days' target books
            w = w.rolling(spec.holding, min_periods=1).mean()
    w = cap_weights(w, spec.max_name)
    if spec.sector_neutral and "sector" in feats:
        from statarb.portfolio.construct import neutralize_sector
        w = neutralize_sector(w, feats["sector"].reindex_like(w))
    if spec.beta_hedge and "beta" in feats:
        w = beta_hedge(w, feats["beta"].reindex_like(w).shift(1).fillna(0.0), "SPY")  # beta known at t-1
    if spec.vol_target_annual:
        port_ret_proxy = (w.shift(1) * feats["ret"].reindex_like(w).fillna(0)).sum(axis=1)
        est = port_ret_proxy.rolling(60, min_periods=20).std(ddof=1).shift(1) * np.sqrt(252)
        w = vol_target(w, est, spec.vol_target_annual, max_lever=spec.gross_max)
    if spec.vix_gate != "none" and "vix" in feats:
        v = feats["vix"].shift(1).reindex(w.index)
        g = (v > v.rolling(252, min_periods=60).quantile(2 / 3)).astype(float) + 1.0 if spec.vix_gate == "step" else (v / v.rolling(252, min_periods=60).mean()).clip(0.5, 2.0)
        w = w.mul(g.fillna(1.0), axis=0)
    w = enforce_limits(w, gross_max=spec.gross_max, net_abs_max=0.05)
    if spec.band:
        w = apply_no_trade_band(w, spec.band)
    return w.fillna(0.0)


def run(spec: StrategySpec, feats: dict | None = None, cost_multiplier: float = 1.0, extra_bp: float = 0.0, write: bool = True) -> tuple[pd.DataFrame, dict]:
    if feats is None:
        feats = {k: load_feature(k) for k in ("ret", "eligible", "abn_turnover", f"score_k{spec.lookback}")}
    if "vix" not in feats:
        try:
            v = pd.read_parquet(load_config("base").get("data_dir_default", "") and (__import__("statarb.data.load", fromlist=["PROC"]).PROC / "vix.parquet")).set_index("date")["vix"]
            feats["vix"] = v
        except Exception:
            pass
    w = build_weights(spec, feats)
    if spec.signal_lag_days:
        w = w.shift(spec.signal_lag_days).fillna(0.0)
    if spec.start or spec.end:
        w = w.loc[spec.start : spec.end]
    syms = [s for s in w.columns]
    adj_close = wide("adj_close").reindex(columns=syms)
    raw_close = wide("close_raw").reindex(columns=syms)
    vol = wide("volume").reindex(columns=syms)
    mark = None
    if spec.execution == "moo":
        adj_open = wide("adj_open").reindex(columns=syms)
        fill = adj_open.reindex(w.index)
        lag = 1
    elif spec.execution in ("limit", "loc"):
        from statarb.execution.limit_orders import loc_fills, resting_limit_fills, session_extremes
        from statarb.features.build_moc import load_moc
        from statarb.features.intraday import decision_price_panel
        p1545 = load_moc("p1545").reindex(index=w.index, columns=syms)
        last_bar = decision_price_panel(syms, "15:45", "close").reindex(index=w.index, columns=syms)
        ac = adj_close.reindex(w.index)
        sigma = feats["ret"].reindex(columns=syms).rolling(60, min_periods=20).std().shift(1).reindex(w.index)
        if spec.execution == "limit":
            lows, highs = session_extremes(syms, "15:45")
            fill, filled = resting_limit_fills(w, last_bar, last_bar, ac, sigma, lows, highs, spec.limit_delta, spec.limit_through)
            lag = 1
        else:
            sig_i = (last_bar / p1545 - 1.0).abs().rolling(60, min_periods=20).mean().shift(1)  # typical 15:45->close move
            fill = loc_fills(w, p1545, last_bar, ac, sig_i, spec.limit_delta)
            lag = 0
        mark = ac
    else:
        fill = adj_close.reindex(w.index)
        lag = 0
    inp = EngineInputs(target_weights=w, fill_price=fill, fill_volume=vol.reindex(w.index), lag=lag, mark_price=mark,
                       half_spread=(feats["spread"].reindex_like(w) / 2) if "spread" in feats else None,
                       sigma_daily=feats["ret"].rolling(60, min_periods=20).std().shift(1).reindex_like(w) if "ret" in feats else None,
                       adv_shares=(feats["auction_vol_proxy"].reindex(index=w.index, columns=syms).rolling(60, min_periods=20).mean().shift(1)
                                   if (spec.auction_participation and spec.execution in ("moc", "loc") and "auction_vol_proxy" in feats)
                                   else vol.rolling(60, min_periods=20).mean().shift(1).reindex(w.index)),
                       delist=feats.get("delist"))
    costs = cost_params_from_config(spec.execution, cost_multiplier, extra_bp, spec.cost_profile)
    out = run_backtest(inp, spec.capital, costs)
    if spec.drawdown_rule:
        cfg_dd = load_config("base")["portfolio"].get("drawdown_rule", {})
        mult = drawdown_scaler(out["net_ret"], cfg_dd.get("trigger", 0.10), cfg_dd.get("scale", 0.5), cfg_dd.get("release", 0.05))
        if (mult < 1.0).any():
            inp.target_weights = w.mul(mult.reindex(w.index).fillna(1.0), axis=0)
            out = run_backtest(inp, spec.capital, costs)
            out["dd_multiplier"] = mult.reindex(out.index).fillna(1.0)
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


def drawdown_scaler(net_ret: pd.Series, trigger: float = 0.10, scale: float = 0.5, release: float = 0.05) -> pd.Series:
    """Exposure multiplier for day t computed from realized net returns through t-1 (ex-ante): halve exposure once the
    cumulative P&L is more than `trigger` below its running peak; restore when back within `release` of the peak."""
    cum = (1 + net_ret.fillna(0)).cumprod()
    peak = cum.cummax()
    dd = cum / peak - 1.0
    mult = pd.Series(1.0, index=net_ret.index)
    state = 1.0
    vals = dd.to_numpy()
    out = np.ones(len(vals))
    for i in range(1, len(vals)):
        d = vals[i - 1]  # information through t-1
        if state == 1.0 and d < -trigger:
            state = scale
        elif state < 1.0 and d > -release:
            state = 1.0
        out[i] = state
    return pd.Series(out, index=net_ret.index)
