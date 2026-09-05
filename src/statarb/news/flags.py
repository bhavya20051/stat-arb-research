"""News/event flags per stock-day, point-in-time at the decision time.

news_flag[t, s] = True if a material 8-K for s was accepted after the previous decision time and at/before the
current one (Tier 1), or (Tier 2) at least one FMP article about s was published in that window.
Both tiers are known at the decision time; article timestamps are ET as delivered by FMP (verified).
"""

from __future__ import annotations

import pandas as pd

from statarb.data.load import PROC
from statarb.news.edgar import assign_event_day


def tier1_8k_flags(dates: pd.DatetimeIndex, symbols: list[str], decision_time: str = "15:40", material_only: bool = True) -> tuple[pd.DataFrame, pd.DataFrame]:
    ev = pd.read_parquet(PROC / "events_8k.parquet")
    if material_only:
        ev = ev[ev["material"]]
    ev = ev[ev["symbol"].isin(symbols)].copy()
    ev["accepted_et"] = pd.to_datetime(ev["accepted_et"], utc=True).dt.tz_convert("America/New_York")
    ev["event_day"] = assign_event_day(ev["accepted_et"], dates, decision_time)
    ev = ev.dropna(subset=["event_day"])
    flag = pd.DataFrame(False, index=dates, columns=symbols)
    cat = pd.DataFrame("", index=dates, columns=symbols, dtype=object)
    for r in ev.itertuples(index=False):
        if r.event_day in flag.index:
            flag.at[r.event_day, r.symbol] = True
            cat.at[r.event_day, r.symbol] = (cat.at[r.event_day, r.symbol] + "|" + r.categories).strip("|")
    return flag, cat


def tier2_article_counts(dates: pd.DatetimeIndex, symbols: list[str], decision_time: str = "15:40") -> pd.DataFrame:
    d = PROC / "news_fmp"
    counts = pd.DataFrame(0, index=dates, columns=symbols, dtype=int)
    for s in symbols:
        f = d / f"{s}.parquet"
        if not f.exists():
            continue
        a = pd.read_parquet(f)
        ts = pd.to_datetime(a["published_et"], utc=True, errors="coerce").dt.tz_convert("America/New_York")
        day = assign_event_day(ts, dates, decision_time).dropna()
        vc = day.value_counts()
        counts.loc[vc.index, s] = vc.values
    return counts


def earnings_days_from_8k(dates: pd.DatetimeIndex, symbols: list[str], decision_time: str = "15:40") -> pd.DataFrame:
    """Earnings-release day (2.02) mapped to the first decision day at which it is known."""
    ev = pd.read_parquet(PROC / "events_8k.parquet")
    ev = ev[ev["symbol"].isin(symbols) & ev["items_list"].str.contains("2.02")].copy()
    ev["accepted_et"] = pd.to_datetime(ev["accepted_et"], utc=True).dt.tz_convert("America/New_York")
    ev["event_day"] = assign_event_day(ev["accepted_et"], dates, decision_time)
    out = pd.DataFrame(False, index=dates, columns=symbols)
    for r in ev.dropna(subset=["event_day"]).itertuples(index=False):
        if r.event_day in out.index:
            out.at[r.event_day, r.symbol] = True
    return out
