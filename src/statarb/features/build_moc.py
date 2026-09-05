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
from statarb.features.intraday import auction_volume_proxy, decision_price_panel, moc_score, rolling_betas
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
    # decision-time prices (split-adjusted like `close`; convert to the adj_close scale via close ratio)
    p1545_raw = decision_price_panel(stocks + etfs, "15:30", "close")
    close_sa = wide("close")  # split-adjusted close, same basis as intraday bars
    scale = (adj_close / close_sa).reindex(index=p1545_raw.index, columns=p1545_raw.columns)
    p1545 = p1545_raw * scale  # now on the total-return-adjusted basis, consistent with adj_close(t-1)
    have = [s for s in stocks if s in p1545.columns]
    sm = pd.read_csv(PROC / "security_master.csv")
    smap = sector_map()
    sector_of = {r["symbol"]: smap.get(r["sector"], "SPY") for _, r in sm.iterrows()}
    fac_cols = [e for e in etfs if e in ret.columns]
    betas = rolling_betas(ret[have], ret[fac_cols], window=120)
    betas_lag = {k: v.shift(1) for k, v in betas.items()}
    feats = {"p1545": p1545}
    idx = p1545.index.intersection(ret.index)
    for k in lookbacks:
        sc = moc_score(p1545[have].reindex(idx), adj_close[have].reindex(idx), p1545[fac_cols].reindex(idx),
                       adj_close[fac_cols].reindex(idx), {kk: v.reindex(idx) for kk, v in betas_lag.items()},
                       sector_of, resid[have].reindex(idx), resid_vol[have].shift(1).reindex(idx), lookback=k)
        feats[f"score_moc_k{k}"] = sc
    flag, cat = tier1_8k_flags(idx, have, decision_time)
    earn = earnings_days_from_8k(idx, have, decision_time)
    feats["news_flag_1540"] = flag
    feats["earnings_flag_1540"] = earn
    feats["eligible_moc"] = elig[have].reindex(idx).fillna(False) & p1545[have].reindex(idx).notna() & ~flag
    feats["auction_vol_proxy"] = auction_volume_proxy(have).reindex(idx)
    for name, df in feats.items():
        df.to_parquet(OUT / f"{name}.parquet")
    return feats


def load_moc(name: str) -> pd.DataFrame:
    return pd.read_parquet(OUT / f"{name}.parquet")
