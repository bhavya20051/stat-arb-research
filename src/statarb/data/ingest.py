"""Ingestion pipeline (M2): tier probe -> security master -> point-in-time universe -> daily prices & actions ->
intraday bars -> 8-K events -> news articles -> snapshot manifest.

Every stage writes parquet/CSV under STATARB_DATA_DIR/processed and is restartable (raw JSON is cached).
Nothing here looks at prices to decide membership: the universe is FMP's historical S&P 500 change list.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from statarb.config import data_dir, load_config
from statarb.data.fmp import FMPClient

PROC = data_dir() / "processed"
PROC.mkdir(parents=True, exist_ok=True)

FACTOR_ETFS = ["SPY", "XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY", "XLRE", "XLC"]


def probe_tier(c: FMPClient) -> dict:
    """Read-only probe of the key's history depth and endpoint access (never prints the key)."""
    out = {}
    out["eod_1995"] = len(c.eod_full("AAPL", "1995-01-03", "1995-01-10") or [])
    out["eod_2015"] = len(c.eod_full("AAPL", "2015-01-05", "2015-01-09") or [])
    out["delisted_twtr_2022"] = len(c.eod_full("TWTR", "2022-10-20", "2022-10-27") or [])
    out["intraday_2013"] = len(c.intraday_5min("SPY", "2013-01-03", "2013-01-03") or [])
    out["intraday_2019"] = len(c.intraday_5min("SPY", "2019-01-02", "2019-01-02") or [])
    try:
        out["sp500_history_rows"] = len(c.sp500_history() or [])
    except RuntimeError as e:
        out["sp500_history_rows"] = f"ERR {e}"
    try:
        out["delisted_rows_page0"] = len(c.delisted(0, 5) or [])
    except RuntimeError as e:
        out["delisted_rows_page0"] = f"ERR {e}"
    return out


# ---------------------------------------------------------------- universe / security master
def build_sp500_membership(c: FMPClient) -> pd.DataFrame:
    """Point-in-time membership intervals from FMP's historical constituent change list + current list.

    FMP rows look like {dateAdded, addedSecurity, removedTicker, removedSecurity, date, symbol, reason}.
    Output: one row per (symbol, start, end) interval; end is NaT for current members."""
    hist = pd.DataFrame(c.sp500_history() or [])
    cur = pd.DataFrame(c.sp500_current() or [])
    cur_syms = set(cur["symbol"]) if not cur.empty else set()
    hist["date"] = pd.to_datetime(hist["date"], errors="coerce")
    hist = hist.sort_values("date")
    intervals = {}
    # walk backwards from the current list: removals define the end of an interval, additions its start
    adds = hist[hist["symbol"].notna() & (hist["symbol"] != "")][["date", "symbol"]]
    rems = hist[hist["removedTicker"].notna() & (hist["removedTicker"] != "")][["date", "removedTicker"]]
    rems = rems.rename(columns={"removedTicker": "symbol"})
    events = pd.concat([adds.assign(kind="add"), rems.assign(kind="remove")]).sort_values(["date", "kind"])
    rows = []
    open_start = {}
    for _, e in events.iterrows():
        s = e["symbol"]
        if e["kind"] == "add":
            open_start[s] = e["date"]
        else:
            start = open_start.pop(s, pd.NaT)
            rows.append({"symbol": s, "start": start, "end": e["date"]})
    for s, start in open_start.items():
        rows.append({"symbol": s, "start": start, "end": pd.NaT})
    for s in cur_syms:
        if s not in open_start and not any(r["symbol"] == s and pd.isna(r["end"]) for r in rows):
            rows.append({"symbol": s, "start": pd.NaT, "end": pd.NaT})  # member since before the list starts
    df = pd.DataFrame(rows)
    df.to_csv(PROC / "sp500_membership_intervals.csv", index=False)
    return df


def build_security_master(c: FMPClient, symbols: list[str]) -> pd.DataFrame:
    """Permanent id per symbol history: symbol changes bridged, delisting date/reason, CIK, sector."""
    changes = pd.DataFrame(c.symbol_changes() or [])
    delisted = []
    page = 0
    while True:
        chunk = c.delisted(page, 100) or []
        if not chunk:
            break
        delisted.extend(chunk)
        page += 1
        if page > 400:
            break
    delisted = pd.DataFrame(delisted)
    rows = []
    for s in symbols:
        prof = c.profile(s) or []
        p = prof[0] if prof else {}
        rows.append({
            "symbol": s,
            "company": p.get("companyName"),
            "cik": p.get("cik"),
            "isin": p.get("isin"),
            "exchange": p.get("exchange"),
            "sector": p.get("sector"),
            "industry": p.get("industry"),
            "ipo_date": p.get("ipoDate"),
            "is_actively_trading": p.get("isActivelyTrading"),
        })
    sm = pd.DataFrame(rows)
    if not changes.empty:
        chg = changes.rename(columns={"oldSymbol": "old_symbol", "newSymbol": "new_symbol"})
        sm = sm.merge(chg[["old_symbol", "new_symbol", "date"]].rename(columns={"date": "symbol_change_date"}),
                      left_on="symbol", right_on="old_symbol", how="left").drop(columns=["old_symbol"])
    if not delisted.empty:
        dl = delisted.rename(columns={"delistedDate": "delisted_date", "ipoDate": "ipo_date_dl"})
        sm = sm.merge(dl[["symbol", "delisted_date"]], on="symbol", how="left")
    sm["permanent_id"] = sm.apply(lambda r: r["cik"] if pd.notna(r.get("cik")) and r.get("cik") not in ("", None) else f"SYM:{r['symbol']}", axis=1)
    sm.to_csv(PROC / "security_master.csv", index=False)
    changes.to_csv(PROC / "symbol_changes.csv", index=False)
    delisted.to_csv(PROC / "delisted_companies.csv", index=False)
    return sm


# ---------------------------------------------------------------- prices
def _eod_frame(rows: list, symbol: str) -> pd.DataFrame:
    df = pd.DataFrame(rows or [])
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    df["symbol"] = symbol
    return df.sort_values("date")


def pull_daily(c: FMPClient, symbols: list[str], start: str, end: str) -> pd.DataFrame:
    """Full (adjusted) and non-split-adjusted daily bars plus dividends/splits per symbol -> long parquet."""
    frames, div_frames, split_frames = [], [], []
    for i, s in enumerate(symbols):
        full = _eod_frame(c.eod_full(s, start, end), s)
        if full.empty:
            continue
        raw = _eod_frame(c.eod_unadjusted(s, start, end), s)
        if not raw.empty:
            raw = raw.rename(columns={"open": "open_raw", "high": "high_raw", "low": "low_raw", "close": "close_raw",
                                      "volume": "volume_raw"})
            full = full.merge(raw[["date", "open_raw", "high_raw", "low_raw", "close_raw", "volume_raw"]], on="date", how="left")
        frames.append(full)
        d = pd.DataFrame(c.dividends(s) or [])
        if not d.empty:
            d["symbol"] = s
            div_frames.append(d)
        sp = pd.DataFrame(c.splits(s) or [])
        if not sp.empty:
            sp["symbol"] = s
            split_frames.append(sp)
        if (i + 1) % 50 == 0:
            print(f"  daily {i + 1}/{len(symbols)} symbols, {c.n_calls} API calls")
    px = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    px.to_parquet(PROC / "daily_prices.parquet", index=False)
    if div_frames:
        pd.concat(div_frames, ignore_index=True).to_parquet(PROC / "dividends.parquet", index=False)
    if split_frames:
        pd.concat(split_frames, ignore_index=True).to_parquet(PROC / "splits.parquet", index=False)
    return px


def pull_intraday(c: FMPClient, symbols: list[str], start: str, end: str, window_days: int = 28) -> None:
    """15-min bars (the 15:30 bar closes at 15:45 = same information as the 15:40 5-min bar), pulled in
    28-calendar-day windows because one FMP request returns at most ~30 trading days (verified 2026-09-05).
    Full days are kept in per-symbol parquet files."""
    out_dir = PROC / "intraday_15min"
    out_dir.mkdir(exist_ok=True)
    edges = list(pd.date_range(start, end, freq=f"{window_days}D")) + [pd.Timestamp(end)]
    for i, s in enumerate(symbols):
        target = out_dir / f"{s}.parquet"
        if target.exists():
            continue
        frames = []
        for a_ts, b_ts in zip(edges[:-1], edges[1:]):
            a = str(a_ts.date())
            b = str((b_ts - pd.Timedelta(days=1)).date()) if b_ts != edges[-1] else str(b_ts.date())
            rows = c.get("historical-chart/15min", symbol=s, **{"from": a, "to": b}) or []
            if rows:
                df = pd.DataFrame(rows)
                df["ts"] = pd.to_datetime(df["date"])
                frames.append(df.drop(columns=["date"]))
        if frames:
            df = pd.concat(frames, ignore_index=True).sort_values("ts").drop_duplicates("ts")
            df["symbol"] = s
            df.to_parquet(target, index=False)
        if (i + 1) % 25 == 0:
            print(f"  intraday {i + 1}/{len(symbols)} symbols, {c.n_calls} API calls")


def pull_news(c: FMPClient, symbols: list[str], start: str, end: str) -> None:
    """FMP stock-news metadata (no full text except title) per symbol, paged; ET timestamps as delivered."""
    out_dir = PROC / "news_fmp"
    out_dir.mkdir(exist_ok=True)
    for i, s in enumerate(symbols):
        target = out_dir / f"{s}.parquet"
        if target.exists():
            continue
        rows = []
        page = 0
        while True:
            chunk = c.stock_news(s, start, end, page=page, limit=250) or []
            if not chunk:
                break
            rows.extend({k: r.get(k) for k in ("symbol", "publishedDate", "publisher", "site", "title", "url")} for r in chunk)
            page += 1
            if len(chunk) < 250 or page > 200:
                break
        if rows:
            df = pd.DataFrame(rows).drop_duplicates(["title", "publishedDate"])
            df["published_et"] = pd.to_datetime(df["publishedDate"], errors="coerce").dt.tz_localize("America/New_York", ambiguous="NaT", nonexistent="NaT")
            df.to_parquet(target, index=False)
        if (i + 1) % 50 == 0:
            print(f"  news {i + 1}/{len(symbols)} symbols, {c.n_calls} API calls")


def write_manifest(name: str = "snapshot_manifest.json") -> Path:
    """SHA-256 of every processed file, plus counts, for the reproducibility claim."""
    entries = {}
    for p in sorted(PROC.rglob("*")):
        if p.is_file():
            h = hashlib.sha256()
            with open(p, "rb") as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    h.update(chunk)
            entries[str(p.relative_to(PROC))] = {"sha256": h.hexdigest(), "bytes": p.stat().st_size}
    man = {"created": str(date.today()), "files": entries}
    path = Path(__file__).resolve().parents[3] / "data" / name
    with open(path, "w", encoding="utf-8") as f:
        json.dump(man, f, indent=1)
    return path
