"""Tier-2 article flags (FMP stock news, ~2012+) at the 15:40 decision time, for the H7 filter-ablation ladder.

flag2[t, s] = True if >= min_articles articles about s were published between the previous decision time and the
current one (ET timestamps as delivered by FMP; verified against Apple's 2016-01-26 16:30 ET earnings release).
Also a keyword-category count on titles (deterministic lexicon, versioned here).
"""

from __future__ import annotations

import re

import pandas as pd

from statarb.data.load import PROC
from statarb.news.edgar import assign_event_day

LEXICON = {
    "earnings": r"\b(earnings|eps|quarter(ly)? results|revenue|profit|loss|beats?|misses?)\b",
    "guidance": r"\b(guidance|outlook|forecast|raises|lowers|cuts)\b",
    "rating": r"\b(upgrade|downgrade|price target|initiat|overweight|underweight)\b",
    "deal": r"\b(acqui|merger|takeover|buyout|to buy|deal)\b",
    "legal": r"\b(lawsuit|investigation|probe|settle|sec charges|fine)\b",
    "management": r"\b(ceo|cfo|chief executive|resign|steps down|appoint)\b",
    "capital": r"\b(dividend|buyback|repurchase|offering|debt)\b",
    "product": r"\b(fda|approval|recall|launch)\b",
}


def tier2_flags(dates: pd.DatetimeIndex, symbols: list[str], decision_time: str = "15:40", min_articles: int = 1):
    d = PROC / "news_fmp"
    count = pd.DataFrame(0, index=dates, columns=symbols, dtype=int)
    cats = {k: pd.DataFrame(0, index=dates, columns=symbols, dtype=int) for k in LEXICON}
    for s in symbols:
        f = d / f"{s}.parquet"
        if not f.exists():
            continue
        a = pd.read_parquet(f)
        ts = pd.to_datetime(a["published_et"], utc=True, errors="coerce").dt.tz_convert("America/New_York")
        day = assign_event_day(ts, dates, decision_time)
        ok = day.notna()
        if not ok.any():
            continue
        vc = day[ok].value_counts()
        count.loc[vc.index, s] = vc.values
        titles = a.loc[ok, "title"].fillna("").str.lower()
        for k, pat in LEXICON.items():
            hit = titles.str.contains(pat, regex=True)
            if hit.any():
                vc2 = day[ok][hit.to_numpy()].value_counts()
                cats[k].loc[vc2.index, s] = vc2.values
    flag = count >= min_articles
    return flag, count, cats
