"""Financial Modeling Prep stable-API client with rate limiting, retries and an on-disk JSON cache.

Endpoints used (https://financialmodelingprep.com/stable/...):
  historical-price-eod/full, historical-price-eod/non-split-adjusted, historical-price-eod/dividend-adjusted,
  historical-chart/5min, historical-sp500-constituent, delisted-companies, symbol-change, dividends, splits,
  profile, search-stock-news, earnings, earnings-surprises, index quotes (VIX).
The key is never logged.  Every raw response is cached under STATARB_DATA_DIR/raw/fmp/<endpoint>/<hash>.json so
that ingestion is restartable and the snapshot manifest can hash the raw inputs.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

import requests

from statarb.config import data_dir, fmp_api_key

BASE = "https://financialmodelingprep.com/stable/"


class FMPClient:
    def __init__(self, calls_per_minute: int = 700, cache: bool = True, timeout: int = 60):
        self._key = fmp_api_key()
        self.min_interval = 60.0 / calls_per_minute
        self._last = 0.0
        self.cache = cache
        self.cache_dir = data_dir() / "raw" / "fmp"
        self.timeout = timeout
        self.session = requests.Session()
        self.n_calls = 0

    def _cache_path(self, endpoint: str, params: dict) -> Path:
        h = hashlib.sha256(json.dumps([endpoint, params], sort_keys=True).encode()).hexdigest()[:20]
        d = self.cache_dir / endpoint.replace("/", "_")
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{h}.json"

    def get(self, endpoint: str, refresh: bool = False, **params) -> Any:
        params = {k: v for k, v in params.items() if v is not None}
        cp = self._cache_path(endpoint, params)
        if self.cache and cp.exists() and not refresh:
            with open(cp, encoding="utf-8") as f:
                return json.load(f)
        q = dict(params)
        q["apikey"] = self._key
        for attempt in range(5):
            wait = self.min_interval - (time.time() - self._last)
            if wait > 0:
                time.sleep(wait)
            try:
                r = self.session.get(BASE + endpoint, params=q, timeout=self.timeout)
            except requests.RequestException:
                time.sleep(2**attempt)
                continue
            self._last = time.time()
            self.n_calls += 1
            if r.status_code == 200:
                try:
                    data = r.json()
                except ValueError:
                    data = None
                if self.cache:
                    with open(cp, "w", encoding="utf-8") as f:
                        json.dump(data, f)
                return data
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(2**attempt + 1)
                continue
            body = r.text.replace(self._key, "***")[:200]
            raise RuntimeError(f"FMP {endpoint} -> HTTP {r.status_code}: {body}")
        raise RuntimeError(f"FMP {endpoint}: retries exhausted")

    # ---- convenience wrappers ----
    def eod_full(self, symbol: str, start: str, end: str):
        return self.get("historical-price-eod/full", symbol=symbol, **{"from": start, "to": end})

    def eod_unadjusted(self, symbol: str, start: str, end: str):
        return self.get("historical-price-eod/non-split-adjusted", symbol=symbol, **{"from": start, "to": end})

    def eod_div_adjusted(self, symbol: str, start: str, end: str):
        return self.get("historical-price-eod/dividend-adjusted", symbol=symbol, **{"from": start, "to": end})

    def intraday_5min(self, symbol: str, start: str, end: str):
        return self.get("historical-chart/5min", symbol=symbol, **{"from": start, "to": end})

    def sp500_history(self):
        return self.get("historical-sp500-constituent")

    def sp500_current(self):
        return self.get("sp500-constituent")

    def delisted(self, page: int = 0, limit: int = 100):
        return self.get("delisted-companies", page=page, limit=limit)

    def symbol_changes(self, limit: int = 10000):
        return self.get("symbol-change", limit=limit)

    def dividends(self, symbol: str, limit: int = 1000):
        return self.get("dividends", symbol=symbol, limit=limit)

    def splits(self, symbol: str, limit: int = 1000):
        return self.get("splits", symbol=symbol, limit=limit)

    def profile(self, symbol: str):
        return self.get("profile", symbol=symbol)

    def stock_news(self, symbol: str, start: str, end: str, page: int = 0, limit: int = 250):
        return self.get("news/stock", symbols=symbol, page=page, limit=limit, **{"from": start, "to": end})

    def earnings(self, symbol: str, limit: int = 200):
        return self.get("earnings", symbol=symbol, limit=limit)
