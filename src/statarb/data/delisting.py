"""Map index-removal reasons and delisting records to the pre-registered delisting returns (configs/universe.yaml).

Rules: merger/acquisition/exchange of shares -> 0.0 (position closed at last exchange price);
bankruptcy / receivership / regulatory closure -> -1.0; other/unknown when the stock stops trading -> -0.30.
A symbol only gets a delisting event if its price history actually ends before the sample end.
"""

from __future__ import annotations

import re

import pandas as pd

from statarb.data.load import PROC, daily_long, membership_intervals

MA = re.compile(r"acqui|merg|taken private|bought|purchas|combin|exchange", re.I)
FAIL = re.compile(r"bankrupt|receivership|chapter 11|seized|fdic|failed|liquidat|insolven|fraud", re.I)


def delisting_events(sample_end: str) -> dict[str, tuple[pd.Timestamp, float]]:
    px = daily_long()
    last = px.groupby("symbol")["date"].max()
    end = pd.Timestamp(sample_end)
    m = membership_intervals()
    reasons = {}
    try:
        hist = pd.read_csv(PROC / "sp500_history_raw.csv")
    except FileNotFoundError:
        hist = None
    events = {}
    for sym, last_date in last.items():
        if last_date >= end - pd.Timedelta(days=7):
            continue  # still trading at sample end
        reason_text = ""
        if hist is not None:
            rr = hist[hist["removedTicker"] == sym]
            if not rr.empty:
                reason_text = " ".join(rr["reason"].fillna("").astype(str))
        if FAIL.search(reason_text):
            r = -1.0
        elif MA.search(reason_text):
            r = 0.0
        else:
            r = -0.30
        events[sym] = (last_date + pd.Timedelta(days=1), r)
    return events
