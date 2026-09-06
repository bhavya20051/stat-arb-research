"""Closing-auction (MOC) model features: signal at 15:45 ET on day t, fill at the close of day t.

Inputs: daily features (build.py), 15-min bar panels (intraday.py), 8-K flags at the 15:40 decision time.
Outputs (processed/features_moc/*.parquet): p1545 (stocks+ETFs), score_moc_k1/k2/k3, eligible_moc, news_flag_1540,
earnings_flag_1540.

Point-in-time guarantees: betas and residual vols are lagged one day (.shift(1)); partial-day returns use only the
15:30 bar close (15:45 price); news flags use acceptance timestamps <= 15:40 ET on day t.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from statarb.data.load import PROC, wide
from statarb.features.build import SECTOR_ETFS, load_feature, sector_map
from statarb.features.intraday import auction_volume_proxy, decision_price_panel, moc_score, rolling_betas, volume_until
from statarb.news.flags import earnings_days_from_8k, tier1_8k_flags

OUT = PROC / "features_moc"


def build(lookbacks=(1, 2, 3), decision_time: str = "15:40") -> dict[str, pd.DataFrame]:
    OUT.mkdir(exist_ok=True)
    ret = load_feature("ret")
    resid = load_feature("resid")
    resid_vol = load_feature("resid_vol")
    elig = load_feature("eligible")
    stocks = list(resid.columns)
    etfs = ["SPY"] + SECTOR_ETFS
    adj_close = wide("adj_close")
    # decision-time prices and the previous day's last-bar close, both from the intraday series (same basis).
    p1545 = decision_price_panel(stocks + etfs, "15:30", "close")
    last_bar = decision_price_panel(stocks + etfs, "15:45", "close").reindex(p1545.index)
    # dividend adjustment on ex-dates (known in advance): prev_close_adj = prev_close - dividend.
    # Post-audit (F9): the raw cash dividend is rescaled to the basis of the intraday series (split-adjusted for some
    # symbols) using yesterday's intraday-close / raw-close ratio, so a pre-split dividend is not subtracted at full
    # size from a split-adjusted price.
    try:
        dv = pd.read_parquet(PROC / "dividends.parquet")
        dv["date"] = pd.to_datetime(dv["date"])
        div_raw = dv.pivot_table(index="date", columns="symbol", values="dividend", aggfunc="sum").reindex(index=p1545.index, columns=p1545.columns).fillna(0.0)
        div = dividend_on_intraday_basis(div_raw, last_bar, wide("close_raw").reindex(index=p1545.index, columns=p1545.columns))
    except FileNotFoundError:
        div = 0.0
    # moc_score divides by basis.shift(1); we want yesterday's last-bar close minus today's ex-dividend, so pre-shift:
    prev_close_basis = (last_bar.shift(1) - div).shift(-1)
    have = [s for s in stocks if s in p1545.columns]
    sm = pd.read_csv(PROC / "security_master.csv")
    smap = sector_map()
    sector_of = {r["symbol"]: smap.get(r["sector"], "SPY") for _, r in sm.iterrows()}
    fac_cols = [e for e in etfs if e in ret.columns]
    betas = rolling_betas(ret[have], ret[fac_cols], window=250)  # 250d: RES-1 showed 120d betas too noisy
    betas_lag = {k: v.shift(1) for k, v in betas.items()}
    feats = {"p1545": p1545, "last_bar_close": last_bar}
    idx = p1545.index.intersection(ret.index)
    for k in lookbacks:
        sc = moc_score(p1545[have].reindex(idx), prev_close_basis[have].reindex(idx), p1545[fac_cols].reindex(idx),
                       prev_close_basis[fac_cols].reindex(idx), {kk: v.reindex(idx) for kk, v in betas_lag.items()},
                       sector_of, resid[have].reindex(idx), resid_vol[have].shift(1).reindex(idx), lookback=k)
        feats[f"score_moc_k{k}"] = sc
    flag, cat = tier1_8k_flags(idx, have, decision_time)
    earn = earnings_days_from_8k(idx, have, decision_time)
    feats["news_flag_1540"] = flag
    feats["earnings_flag_1540"] = earn
    partial = p1545[have].reindex(idx) / prev_close_basis[have].reindex(idx).shift(1) - 1.0
    sane = (partial.abs() <= 0.25) & (feats["score_moc_k1"].abs() <= 8.0)   # data-sanity mask (bad bars / spin-offs)
    # ex-ante intraday reliability: trailing 60-day agreement (through t-1) between the intraday-derived close-to-close
    # return and the daily total return; ticker reuse/splicing in FMP intraday histories fails this (audit item).
    r_int = last_bar[have].reindex(idx) / prev_close_basis[have].reindex(idx).shift(1) - 1.0
    r_day = adj_close[have].reindex(idx).pct_change()
    agree = ((r_int - r_day).abs() <= 0.01).where(r_int.notna() & r_day.notna())
    reliability = agree.rolling(60, min_periods=30).mean().shift(1)
    feats["intraday_reliability"] = reliability
    # Post-audit (F3): the daily `eligible` panel at t uses the full-day residual of t (jump rule), which is not known
    # at 15:45. Use it lagged one day and add the ex-ante partial-day jump rule (|score_k1| < 3 sigma at 15:45).
    elig_1545 = ex_ante_eligibility(elig[have].reindex(idx), feats["score_moc_k1"], n_sigma=3.0)
    base = (elig_1545 & p1545[have].reindex(idx).notna()
            & sane.fillna(False) & (reliability >= 0.95).fillna(False))
    feats["eligible_base"] = base          # data-quality eligibility WITHOUT the news exclusion (drift strategy)
    feats["eligible_moc"] = base & ~flag   # reversal strategies: no-news names only
    feats["auction_vol_proxy"] = auction_volume_proxy(have).reindex(idx)
    feats["beta_spy"] = betas["SPY"].reindex(idx)  # runner shifts by one day
    sec_panel = pd.DataFrame({s: sector_of.get(s, "SPY") for s in have}, index=idx)
    feats["sector"] = sec_panel
    # ex-ante expected earnings dates: each past 2.02 event day implies an expected event ~1 year later (+/- 3 trading days)
    ex = pd.DataFrame(False, index=idx, columns=have)
    e_arr = earn.to_numpy()
    pos = {d: i for i, d in enumerate(idx)}
    for j, s in enumerate(have):
        days = idx[e_arr[:, j]]
        for d in days:
            target = d + pd.Timedelta(days=364)
            i = idx.searchsorted(target)
            for off in range(-3, 4):
                if 0 <= i + off < len(idx):
                    ex.iat[i + off, j] = True
    feats["expected_earnings"] = ex
    # ex-ante abnormal intraday turnover: volume through 15:45 today / trailing 60-day mean of the same quantity (t-1)
    v1545 = volume_until(have, "15:45").reindex(index=idx, columns=have)
    feats["abn_turnover_1545"] = v1545 / v1545.shift(1).rolling(60, min_periods=20).mean().replace(0, np.nan)
    # earnings-filing timing bucket at the decision day: "after_hours" (accepted after 15:40 on the prior day or
    # before 09:30 today) vs "intraday" (accepted 09:30-15:40 today)
    from statarb.news.edgar import assign_event_day
    ev = pd.read_parquet(PROC / "events_8k.parquet")
    ev = ev[ev["symbol"].isin(have) & ev["items_list"].str.contains("2.02")].copy()
    ev["accepted_et"] = pd.to_datetime(ev["accepted_et"], utc=True).dt.tz_convert("America/New_York")
    ev["event_day"] = assign_event_day(ev["accepted_et"], idx, decision_time)
    ev = ev.dropna(subset=["event_day"])
    hm = ev["accepted_et"].dt.hour * 60 + ev["accepted_et"].dt.minute
    same_day = ev["accepted_et"].dt.tz_localize(None).dt.normalize() == pd.to_datetime(ev["event_day"])
    ev["timing"] = np.where(same_day & (hm >= 9 * 60 + 30), "intraday", "after_hours")
    timing = pd.DataFrame("", index=idx, columns=have, dtype=object)
    for r in ev.itertuples(index=False):
        if r.event_day in timing.index:
            timing.at[r.event_day, r.symbol] = r.timing
    feats["earnings_timing_1540"] = timing
    for name, df in feats.items():
        df.to_parquet(OUT / f"{name}.parquet")
    return feats


def load_moc(name: str) -> pd.DataFrame:
    return pd.read_parquet(OUT / f"{name}.parquet")


def ex_ante_eligibility(elig_daily: pd.DataFrame, score_k1: pd.DataFrame, n_sigma: float = 3.0) -> pd.DataFrame:
    """Eligibility known at 15:45 on day t: the daily eligibility panel of day t-1 (membership, price, jump rule over
    residuals through t-1) intersected with the partial-day jump rule |z_partial(t)| < n_sigma. Nothing from the close
    of day t enters."""
    lagged = elig_daily.shift(1).fillna(False).astype(bool)
    z = score_k1.reindex_like(elig_daily)
    return lagged & (z.abs() < n_sigma).fillna(False)


def dividend_on_intraday_basis(div_raw: pd.DataFrame, last_bar_close: pd.DataFrame, close_raw: pd.DataFrame) -> pd.DataFrame:
    """Rescale a raw cash dividend (per share, unadjusted) to the price basis of the intraday series: multiply by
    yesterday's (intraday last-bar close / raw daily close). Ratio 1 if the intraday series is raw, 1/split factor if it
    is split-adjusted; missing ratios fall back to 1."""
    ratio = (last_bar_close.shift(1) / close_raw.shift(1).replace(0.0, np.nan)).reindex_like(div_raw)
    ratio = ratio.where(np.isfinite(ratio) & (ratio > 0), 1.0)
    return (div_raw * ratio).fillna(0.0)
