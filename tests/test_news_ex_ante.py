"""News flags must be assigned to the first decision time at which they were public (ET), never earlier."""

import pandas as pd

from statarb.news.edgar import assign_event_day

TD = pd.bdate_range("2016-01-25", "2016-01-29")


def _ts(s):
    return pd.Timestamp(s, tz="America/New_York")


def test_after_hours_filing_flags_next_day():
    acc = pd.Series([_ts("2016-01-26 16:30"), _ts("2016-01-26 15:39"), _ts("2016-01-26 15:40")])
    out = assign_event_day(acc, TD, "15:40")
    assert out.iloc[0] == pd.Timestamp("2016-01-27")  # after decision time -> next day
    assert out.iloc[1] == pd.Timestamp("2016-01-26")  # before decision time -> same day
    assert out.iloc[2] == pd.Timestamp("2016-01-27")  # at the cutoff counts as not yet known


def test_weekend_and_utc_conversion():
    acc = pd.Series([_ts("2016-01-30 10:00"), pd.Timestamp("2016-01-26 21:30", tz="UTC")])
    out = assign_event_day(acc, TD, "15:40")
    assert out.iloc[0] == pd.Timestamp("2016-02-01") or pd.isna(out.iloc[0])  # Saturday -> next trading day (outside TD -> NaT)
    # 21:30 UTC = 16:30 ET (EST) -> next day
    assert out.iloc[1] == pd.Timestamp("2016-01-27")


def test_missing_timestamp_is_unknown():
    out = assign_event_day(pd.Series([pd.NaT]), TD)
    assert pd.isna(out.iloc[0])
