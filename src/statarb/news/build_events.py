"""Build the 8-K event table for every CIK in the security master -> processed/events_8k.parquet."""

from __future__ import annotations

import pandas as pd

from statarb.data.load import PROC
from statarb.news.edgar import EdgarClient


def build(refresh: bool = False) -> pd.DataFrame:
    sm = pd.read_csv(PROC / "security_master.csv")
    ciks = sm.dropna(subset=["cik"])[["symbol", "cik"]]
    ciks["cik"] = ciks["cik"].astype(str).str.replace(r"\.0$", "", regex=True).str.lstrip("0")
    ciks = ciks[ciks["cik"].str.isdigit()]
    c = EdgarClient(rps=8.0)
    frames = []
    for i, (sym, cik) in enumerate(ciks.itertuples(index=False)):
        try:
            ev = c.eight_k_events(int(cik), refresh)
        except Exception as e:  # network / missing CIK: record and continue
            print(f"  {sym} CIK {cik}: {e}")
            continue
        if not ev.empty:
            ev = ev.assign(symbol=sym)
            frames.append(ev)
        if (i + 1) % 100 == 0:
            print(f"  edgar {i + 1}/{len(ciks)}")
    out = pd.concat(frames, ignore_index=True)
    out["items_list"] = out["items_list"].apply(lambda L: ",".join(L))
    out["categories"] = out["categories"].apply(lambda L: ",".join(L))
    out.to_parquet(PROC / "events_8k.parquet", index=False)
    print("events:", len(out), "symbols:", out["symbol"].nunique())
    return out


if __name__ == "__main__":
    build()
