"""Command-line workflows: probe | ingest | validate | features | backtest | robustness | holdout | forward | report."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone

from statarb.config import REPO_ROOT, config_hash, load_config


def git_hash() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, text=True).strip()
    except Exception:
        return "unknown"


def manifest(stage: str, extra: dict | None = None) -> dict:
    m = {
        "stage": stage,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "git": git_hash(),
        "config_hash": config_hash("base", "costs", "universe", "splits"),
    }
    if extra:
        m.update(extra)
    return m


def cmd_probe(args):
    from statarb.data.fmp import FMPClient
    from statarb.data.ingest import probe_tier

    c = FMPClient()
    print(json.dumps(probe_tier(c), indent=1))


def cmd_ingest(args):
    from statarb.data import ingest as ing
    from statarb.data.fmp import FMPClient

    cfg = load_config("splits")
    c = FMPClient()
    print("== membership ==")
    mem = ing.build_sp500_membership(c)
    syms = sorted(set(mem["symbol"].dropna()))
    print(f"symbols with membership intervals: {len(syms)}")
    print("== security master ==")
    ing.build_security_master(c, syms)
    start = cfg["secondary_daily"]["dev"]["start"]
    end = cfg["primary_intraday"]["holdout"]["end"]
    print("== daily prices ==")
    ing.pull_daily(c, syms + ing.FACTOR_ETFS, start, end)
    if args.intraday:
        print("== intraday ==")
        ing.pull_intraday(c, syms + ["SPY"], args.intraday_start, end)
    if args.news:
        print("== news ==")
        ing.pull_news(c, syms, "2010-01-01", end)
    print("manifest:", ing.write_manifest())
    print(json.dumps(manifest("ingest", {"api_calls": c.n_calls}), indent=1))


def main(argv=None):
    p = argparse.ArgumentParser(prog="statarb")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("probe").set_defaults(fn=cmd_probe)
    pi = sub.add_parser("ingest")
    pi.add_argument("--intraday", action="store_true")
    pi.add_argument("--intraday-start", default="2013-01-01")
    pi.add_argument("--news", action="store_true")
    pi.set_defaults(fn=cmd_ingest)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
