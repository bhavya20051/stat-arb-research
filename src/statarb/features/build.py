"""Build the feature panel from processed daily data (all quantities known at the close of day t or earlier).

Outputs (wide DataFrames, dates x symbols) saved to STATARB_DATA_DIR/processed/features/*.parquet:
  ret      total return close(t-1)->close(t) from adjClose
  resid    residual of ret on SPY + sector ETF returns (rolling OLS, trailing window)
  resid_vol, score_k1/3/5 (reversal scores), abn_turnover, spread (range-based), dollar_vol_60 (median),
  member (PIT membership mask), eligible (member & liquidity & price & jump masks)
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from statarb.config import load_config
from statarb.data.load import PROC, membership_mask, wide
from statarb.features.residual import rolling_ols_residuals
from statarb.features.spreads import rolling_spread
from statarb.signals.reversal import abnormal_turnover, jump_exclusion_mask, reversal_score

SECTOR_ETFS = ["XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY", "XLRE", "XLC"]


def sector_map() -> dict[str, str]:
    """FMP profile sector -> SPDR sector ETF (XLRE/XLC only after inception; earlier mapped to XLF/XLK, XLY/XLK)."""
    return {
        "Basic Materials": "XLB", "Energy": "XLE", "Financial Services": "XLF", "Industrials": "XLI",
        "Technology": "XLK", "Consumer Defensive": "XLP", "Utilities": "XLU", "Healthcare": "XLV",
        "Consumer Cyclical": "XLY", "Real Estate": "XLRE", "Communication Services": "XLC",
    }


def build(window: int = 120, zwin: int = 60) -> dict[str, pd.DataFrame]:
    cfg = load_config("base")
    sm = pd.read_csv(PROC / "security_master.csv")
    close = wide("adjClose")
    close_raw = wide("close")
    high, low, vol = wide("high"), wide("low"), wide("volume")
    ret = close.pct_change()
    etfs = ["SPY"] + SECTOR_ETFS
    stocks = [s for s in close.columns if s not in etfs]
    smap = sector_map()
    sec_of = {r["symbol"]: smap.get(r["sector"], "SPY") for _, r in sm.iterrows()}
    # residualize by sector group: each stock on SPY + its sector ETF (fallback SPY only if ETF missing/young)
    resid = pd.DataFrame(np.nan, index=ret.index, columns=stocks)
    groups: dict[str, list[str]] = {}
    for s in stocks:
        groups.setdefault(sec_of.get(s, "SPY"), []).append(s)
    for etf, syms in groups.items():
        fac = ret[["SPY"]].copy()
        if etf != "SPY" and etf in ret.columns:
            fac[etf] = ret[etf]
        r = rolling_ols_residuals(ret[syms], fac.fillna(0.0), window=window)
        resid[syms] = r
    resid_vol = resid.rolling(zwin, min_periods=20).std(ddof=1)
    feats = {"ret": ret, "resid": resid, "resid_vol": resid_vol}
    for k in (1, 3, 5):
        feats[f"score_k{k}"] = reversal_score(resid, k, zwin)
    feats["abn_turnover"] = abnormal_turnover(vol[stocks], 60)
    feats["spread"] = rolling_spread(close_raw[stocks], high[stocks], low[stocks], window=21, cap=0.01)
    dv = (close_raw * vol)[stocks]
    feats["dollar_vol_60"] = dv.rolling(60, min_periods=30).median().shift(1)  # known at t-1
    member = membership_mask(ret.index, stocks, lag_days=1)
    feats["member"] = member
    liquid = feats["dollar_vol_60"] >= feats["dollar_vol_60"].quantile(0.0, axis=1).to_numpy()[:, None]
    price_ok = close_raw[stocks].shift(1) >= cfg["filters"]["min_price"]
    jump_ok = jump_exclusion_mask(resid, zwin, cfg["filters"]["jump_exclusion_sigma"], cfg["filters"]["jump_exclusion_days"])
    feats["eligible"] = member & price_ok.fillna(False) & jump_ok.fillna(False) & resid.notna()
    out = PROC / "features"
    out.mkdir(exist_ok=True)
    for name, df in feats.items():
        df.to_parquet(out / f"{name}.parquet")
    return feats


def load_feature(name: str) -> pd.DataFrame:
    return pd.read_parquet(PROC / "features" / f"{name}.parquet")
