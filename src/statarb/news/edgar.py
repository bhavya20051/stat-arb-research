"""SEC EDGAR 8-K event table via the submissions API (acceptance timestamps to the second, 8-K item codes).

Point-in-time rule: an event is known at the moment of `acceptanceDateTime` (UTC -> America/New_York).
Materiality categories are mapped from 8-K item codes (Regulation S-K):
  2.02 results of operations (earnings); 7.01 Reg FD; 1.01/1.02/2.01 agreements & acquisitions;
  2.03/2.04 debt & triggering events; 2.05/2.06 exit costs & impairments; 1.03 bankruptcy; 3.01 delisting notice;
  4.01/4.02 auditor / non-reliance (restatement); 5.01/5.02 control & officer changes; 8.01 other events.
SEC fair-access policy: declared User-Agent, <= 10 requests/second.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pandas as pd
import requests

from statarb.config import data_dir

UA = {"User-Agent": "stat-arb research project bhavn008@gmail.com", "Accept-Encoding": "gzip, deflate"}
ITEM_CATEGORY = {
    "2.02": "earnings", "7.01": "guidance_regfd", "1.01": "agreement", "1.02": "agreement", "2.01": "m_and_a",
    "2.03": "debt", "2.04": "debt_trigger", "2.05": "exit_costs", "2.06": "impairment", "1.03": "bankruptcy",
    "3.01": "delisting_notice", "4.01": "auditor", "4.02": "restatement", "5.01": "control_change",
    "5.02": "management", "8.01": "other_event", "9.01": "exhibits", "5.07": "shareholder_vote",
    "5.03": "bylaws", "3.02": "unregistered_sales", "3.03": "security_holder_rights", "5.08": "shareholder_nominations",
}
NON_MATERIAL = {"9.01", "5.07", "5.03", "5.08", "3.03"}


class EdgarClient:
    def __init__(self, rps: float = 8.0):
        self.min_interval = 1.0 / rps
        self._last = 0.0
        self.cache_dir = data_dir() / "raw" / "edgar"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()

    def _get_json(self, url: str, cache_name: str, refresh: bool = False):
        cp = self.cache_dir / cache_name
        if cp.exists() and not refresh:
            with open(cp, encoding="utf-8") as f:
                return json.load(f)
        for attempt in range(5):
            wait = self.min_interval - (time.time() - self._last)
            if wait > 0:
                time.sleep(wait)
            r = self.session.get(url, headers=UA, timeout=60)
            self._last = time.time()
            if r.status_code == 200:
                data = r.json()
                with open(cp, "w", encoding="utf-8") as f:
                    json.dump(data, f)
                return data
            time.sleep(2**attempt)
        raise RuntimeError(f"EDGAR fetch failed: {url}")

    def filings_for_cik(self, cik: int | str, refresh: bool = False) -> pd.DataFrame:
        cik10 = f"{int(cik):010d}"
        j = self._get_json(f"https://data.sec.gov/submissions/CIK{cik10}.json", f"CIK{cik10}.json", refresh)
        frames = [pd.DataFrame(j["filings"]["recent"])]
        for extra in j["filings"].get("files", []):
            name = extra["name"]
            jj = self._get_json(f"https://data.sec.gov/submissions/{name}", name, refresh)
            frames.append(pd.DataFrame(jj))
        df = pd.concat(frames, ignore_index=True)
        df["cik"] = int(cik)
        return df

    def eight_k_events(self, cik: int | str, refresh: bool = False) -> pd.DataFrame:
        df = self.filings_for_cik(cik, refresh)
        df = df[df["form"].isin(["8-K", "8-K/A"])].copy()
        if df.empty:
            return df
        ts = pd.to_datetime(df["acceptanceDateTime"], utc=True, errors="coerce")
        df["accepted_et"] = ts.dt.tz_convert("America/New_York")
        df["items_list"] = df["items"].fillna("").apply(lambda s: [x.strip() for x in s.split(",") if x.strip()])
        df["categories"] = df["items_list"].apply(lambda L: sorted({ITEM_CATEGORY.get(i, "other") for i in L}))
        df["material"] = df["items_list"].apply(lambda L: any(i not in NON_MATERIAL for i in L))
        return df[["cik", "accessionNumber", "form", "filingDate", "accepted_et", "items_list", "categories", "material"]]


def assign_event_day(accepted_et: pd.Series, trading_days: pd.DatetimeIndex, decision_time: str = "15:40") -> pd.Series:
    """Map acceptance timestamps to the trading day on which the event first affects a decision.

    If accepted before the decision time on a trading day t, the event belongs to t; otherwise to the next trading
    day.  Non-trading days roll to the next trading day."""
    hh, mm = (int(x) for x in decision_time.split(":"))
    out = []
    td = pd.DatetimeIndex(trading_days).tz_localize(None)
    for ts in accepted_et:
        if pd.isna(ts):
            out.append(pd.NaT)
            continue
        day = pd.Timestamp(ts.date())
        after_cutoff = (ts.hour, ts.minute) >= (hh, mm)
        pos = td.searchsorted(day)
        if pos < len(td) and td[pos] == day and not after_cutoff:
            out.append(td[pos])
        else:
            pos2 = td.searchsorted(day + pd.Timedelta(days=1)) if (pos < len(td) and td[pos] == day) else pos
            out.append(td[pos2] if pos2 < len(td) else pd.NaT)
    return pd.Series(out, index=accepted_et.index)
