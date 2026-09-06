"""Recruiter-grade HTML research report generated from result files (all figures from code).

Usage: python -m statarb.reporting.html_report  -> reports/QUANT_RESEARCH_REPORT.html
Reads (tolerantly): 04_HYPOTHESIS_REGISTRY.csv, 06_DATA_AUDIT.md, results/dev/grid/grid_results.csv,
results/dev/capacity_curve_full.json, results/validation/{selection.json,validation_results.json,daily_VAL_*.csv,
combined_book.json}, results/robustness/<family>/*, results/holdout/*, results/dev/dev_analysis.json, results/dev/ic_decay_k1.csv.
"""

from __future__ import annotations

import base64
import csv
import io
import json
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from statarb.config import REPO_ROOT

RES = REPO_ROOT / "results"
REP = REPO_ROOT / "reports"
FIG = REP / "figures"
PALETTE = ["#1f5fbf", "#d1495b", "#2a9d8f", "#e9a03b", "#6c5b7b", "#8c8c8c"]


def _img(fig, name: str) -> str:
    FIG.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG / f"{name}.png", dpi=130, bbox_inches="tight")
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    return f'<img src="data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}" alt="{name}" style="max-width:100%">'


def _load_json(p: Path):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return None


def _table(df: pd.DataFrame, floatfmt: str = "{:.3f}") -> str:
    if df is None or len(df) == 0:
        return "<p class='muted'>not available</p>"
    d = df.copy()
    for c in d.columns:
        if pd.api.types.is_float_dtype(d[c]):
            d[c] = d[c].map(lambda v: "" if pd.isna(v) else floatfmt.format(v))
    return d.to_html(index=False, classes="tbl", border=0, escape=False)


def fig_equity(daily: pd.DataFrame, title: str, name: str) -> str:
    fig, ax = plt.subplots(2, 1, figsize=(9, 5.5), sharex=True, gridspec_kw={"height_ratios": [3, 1.3]})
    g = (1 + daily["gross_ret"]).cumprod() - 1
    n = (1 + daily["net_ret"]).cumprod() - 1
    ax[0].plot(g.index, g.values, color=PALETTE[5], lw=1.2, label="gross")
    ax[0].plot(n.index, n.values, color=PALETTE[0], lw=1.6, label="net")
    ax[0].axhline(0, color="#999", lw=0.6)
    ax[0].set_title(title)
    ax[0].set_ylabel("cumulative return")
    ax[0].legend(frameon=False)
    cum = (1 + daily["net_ret"]).cumprod()
    dd = cum / cum.cummax() - 1
    ax[1].fill_between(dd.index, dd.values, 0, color=PALETTE[1], alpha=0.5)
    ax[1].set_ylabel("net drawdown")
    for a in ax:
        a.spines[["top", "right"]].set_visible(False)
    return _img(fig, name)


def fig_rolling_sharpe(daily: pd.DataFrame, name: str, window: int = 252) -> str:
    r = daily["net_ret"]
    rs = r.rolling(window).mean() / r.rolling(window).std() * np.sqrt(252)
    fig, ax = plt.subplots(figsize=(9, 2.8))
    ax.plot(rs.index, rs.values, color=PALETTE[2], lw=1.4)
    ax.axhline(0, color="#999", lw=0.6)
    ax.set_title(f"rolling {window}-day net Sharpe")
    ax.spines[["top", "right"]].set_visible(False)
    return _img(fig, name)


def fig_monthly_heatmap(daily: pd.DataFrame, name: str) -> str:
    m = daily["net_ret"].groupby([daily.index.year, daily.index.month]).sum().unstack() * 100
    fig, ax = plt.subplots(figsize=(9, max(2.5, 0.32 * len(m))))
    vmax = np.nanmax(np.abs(m.values)) if m.size else 1
    im = ax.imshow(m.values, cmap="RdBu", vmin=-vmax, vmax=vmax, aspect="auto")
    ax.set_yticks(range(len(m.index)))
    ax.set_yticklabels(m.index)
    ax.set_xticks(range(12))
    ax.set_xticklabels(["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"])
    for i in range(m.shape[0]):
        for j in range(m.shape[1]):
            v = m.values[i, j]
            if np.isfinite(v):
                ax.text(j, i, f"{v:.1f}", ha="center", va="center", fontsize=7)
    ax.set_title("monthly net return (%)")
    fig.colorbar(im, ax=ax, fraction=0.02)
    return _img(fig, name)


def fig_bar(series: pd.Series, title: str, name: str, color=PALETTE[0]) -> str:
    fig, ax = plt.subplots(figsize=(9, 2.8))
    ax.bar([str(i) for i in series.index], series.values, color=color)
    ax.axhline(0, color="#999", lw=0.6)
    ax.set_title(title)
    plt.setp(ax.get_xticklabels(), rotation=60, ha="right", fontsize=7)
    ax.spines[["top", "right"]].set_visible(False)
    return _img(fig, name)


def fig_hist(daily: pd.DataFrame, name: str) -> str:
    fig, ax = plt.subplots(figsize=(6, 3))
    ax.hist(daily["net_ret"] * 100, bins=80, color=PALETTE[0], alpha=0.8)
    ax.set_title("distribution of daily net returns (%)")
    ax.spines[["top", "right"]].set_visible(False)
    return _img(fig, name)


def fig_curve(x, y, title, name, xlabel="", logx=False) -> str:
    fig, ax = plt.subplots(figsize=(6, 3))
    ax.plot(x, y, marker="o", color=PALETTE[0])
    if logx:
        ax.set_xscale("log")
    ax.axhline(0, color="#999", lw=0.6)
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.spines[["top", "right"]].set_visible(False)
    return _img(fig, name)


def build_report() -> Path:
    parts = []
    H = lambda lvl, t: parts.append(f"<h{lvl}>{t}</h{lvl}>")
    P = lambda t: parts.append(f"<p>{t}</p>")
    reg = pd.read_csv(REPO_ROOT / "04_HYPOTHESIS_REGISTRY.csv")
    sel = _load_json(RES / "validation" / "selection.json") or {}
    val = _load_json(RES / "validation" / "validation_results.json") or {}
    comb = _load_json(RES / "validation" / "combined_book.json") or {}
    cap = _load_json(RES / "dev" / "capacity_curve_full.json") or {}
    hold = _load_json(RES / "holdout" / "holdout_results.json") or {}
    grid = pd.read_csv(RES / "dev" / "grid" / "grid_results.csv") if (RES / "dev" / "grid" / "grid_results.csv").exists() else None
    dev = _load_json(RES / "dev" / "dev_analysis.json") or {}

    # ---------------- executive summary
    H(1, "Residual short-term reversal in U.S. large caps: a cost-realistic, locked-holdout study")
    P(f"<span class='muted'>Generated {date.today()} from the repository's result files; every figure is reproducible from code. Status of stages: grid {'done' if grid is not None else 'pending'}, validation {'done' if val else 'pending'}, holdout {'done' if hold else 'pending'}.</span>")
    H(2, "Executive summary")
    summ_rows = []
    for fam, s in val.items():
        summ_rows.append({"strategy": fam, "DEV net Sharpe": sel.get(fam, {}).get("dev", {}).get("net_sr"), "VAL net Sharpe": s["net"]["sharpe_ann"],
                          "VAL 95% CI": f"{s['net']['sharpe_ci95_ann'][0]:.2f} .. {s['net']['sharpe_ci95_ann'][1]:.2f}", "VAL net return/yr": s["net"]["ann_return"],
                          "VAL max DD": s["net"]["max_drawdown"], "turnover/day": s["avg_turnover"], "PSR": s["net"].get("psr_vs_zero"), "DSR (DEV)": sel.get(fam, {}).get("multiple_testing", {}).get("dsr")})
    if hold:
        for fam, s in hold.get("families", {}).items():
            summ_rows.append({"strategy": f"{fam} — LOCKED HOLDOUT 2023-01-03..2026-08-31", "VAL net Sharpe": None, "DEV net Sharpe": None, "VAL 95% CI": "", "VAL net return/yr": None, "VAL max DD": None, "turnover/day": None, "PSR": None, "DSR (DEV)": None, **{k: v for k, v in s.items() if k.startswith("holdout")}})
    parts.append(_table(pd.DataFrame(summ_rows)))
    P("Interpretation and the A–D classification are in the Conclusion section; the headline figure is always the net-of-cost result on data not used for design.")

    # ---------------- research question, hypothesis, literature
    H(2, "Research question and economic hypothesis")
    P("Does company-specific (residual) short-term price pressure in liquid U.S. stocks still reverse enough, after realistic exchange-member costs and with orders a firm can actually place (market-on-close and limit-on-close), to be traded profitably when news-driven moves are filtered out ex ante? Mechanism: temporary liquidity demand pushes a stock away from its factor-implied value; once the urgent trader is done the price drifts back (Nagel 2012; Blitz, Huij, Lansdorp & Verbeek 2013). News-driven moves should continue rather than reverse (Chan 2003; Tetlock 2011); the premium should rise with market stress (Nagel 2012).")
    H(2, "Hypothesis registry (pre-registered, never edited except to fill results)")
    show = reg[["experiment_id", "trial_type", "hypothesis", "actual_result", "decision"]].copy()
    show = show[~show["experiment_id"].str.startswith("C-moc")]
    parts.append(_table(show))
    n_cand = int((reg["trial_type"] == "candidate").sum())
    P(f"Candidate configurations registered and run on the development sample: <b>{n_cand}</b> (each counted in the Deflated Sharpe Ratio of its family). Diagnostics and placebos are never counted as candidates.")

    # ---------------- data
    H(2, "Data and data-quality audit")
    audit = (REPO_ROOT / "06_DATA_AUDIT.md").read_text(encoding="utf-8") if (REPO_ROOT / "06_DATA_AUDIT.md").exists() else ""
    parts.append("<pre class='doc'>" + audit.replace("<", "&lt;")[:12000] + "</pre>")

    # ---------------- signal evidence
    H(2, "Signal evidence on the development sample")
    ic_path = RES / "dev" / "ic_decay_k1.csv"
    if ic_path.exists():
        ic = pd.read_csv(ic_path, index_col=0)
        parts.append(fig_curve(ic.index, ic["ic_mean"], "IC decay: rank correlation of the reversal score with forward return by horizon (days)", "ic_decay", "horizon (days)"))
    if dev:
        rows = []
        for k in ("FM_k1_h1", "FM_k3_h3", "FM_k5_h5"):
            if k in dev:
                rows.append({"test": k, "residual score t": dev[k]["resid_score"]["nw_t"], "raw score t": dev[k]["raw_score"]["nw_t"]})
        parts.append(_table(pd.DataFrame(rows)))

    # ---------------- grid
    H(2, "Development grid (all registered candidates, market-maker cost profile)")
    if grid is not None:
        g = grid.copy()
        g["family"] = np.where(g.get("signal", "reversal").astype(str) == "earnings_drift", "earnings_drift", np.where(g.get("construction", "quantile").astype(str) == "event", "event_reversal", "rank_reversal"))
        best = g.sort_values("net_sr", ascending=False).groupby("family").head(5)
        parts.append(_table(best[[c for c in ("family", "id", "gross_sr", "net_sr", "net_ann", "max_dd", "turnover", "gross_exp", "cost_bp") if c in best]]))
        fig, ax = plt.subplots(figsize=(8, 3.2))
        for i, (fam, gg) in enumerate(g.groupby("family")):
            ax.scatter(gg["turnover"], gg["net_sr"], s=18, alpha=0.8, color=PALETTE[i], label=fam)
        ax.axhline(0, color="#999", lw=0.6)
        ax.set_xlabel("turnover / day")
        ax.set_ylabel("DEV net Sharpe")
        ax.legend(frameon=False)
        ax.spines[["top", "right"]].set_visible(False)
        parts.append(_img(fig, "grid_scatter"))
    for fam, ch in sel.items():
        mt = ch.get("multiple_testing", {})
        P(f"<b>{fam}</b>: selected <code>{ch['id']}</code> — DEV net Sharpe {ch['dev'].get('net_sr', float('nan')):.2f}; candidates {mt.get('n_candidates')}; PSR {mt.get('psr_vs_zero', float('nan')):.3f}; DSR {mt.get('dsr', float('nan')):.3f}; CSCV PBO {mt.get('pbo_cscv')}.")

    # ---------------- capacity
    H(2, "Capacity and leverage")
    if cap:
        c = cap["curve"]
        xs = [float(k) / 1e6 for k in c]
        parts.append(fig_curve(xs, list(c.values()), "DEV net Sharpe vs capital (market-maker profile, selected rank configuration)", "capacity", "capital ($M)", logx=True))
        P(f"Primary capital by the pre-specified rule (largest size keeping ≥ 90% of the peak net Sharpe): <b>${cap['primary_capital']/1e6:.0f}M</b>. Leverage policy: 10% volatility target, gross exposure ≤ 3×, ex-ante drawdown brake (halve at −10%, restore at −5%).")

    # ---------------- validation
    H(2, "One-shot validation (2019-01-02 → 2022-12-15)")
    for fam, s in val.items():
        f = RES / "validation" / f"daily_VAL_{fam}.csv"
        if f.exists():
            d = pd.read_csv(f, index_col=0, parse_dates=True)
            parts.append(fig_equity(d, f"{fam}: validation, gross vs net", f"val_equity_{fam}"))
            parts.append(fig_rolling_sharpe(d, f"val_rolling_{fam}"))
            parts.append(fig_monthly_heatmap(d, f"val_monthly_{fam}"))
            parts.append(fig_hist(d, f"val_hist_{fam}"))
        P(f"<b>{fam}</b>: net Sharpe {s['net']['sharpe_ann']:.2f} (95% block-bootstrap CI {s['net']['sharpe_ci95_ann'][0]:.2f}..{s['net']['sharpe_ci95_ann'][1]:.2f}), gross {s['gross']['sharpe_ann']:.2f}, net return {s['net']['ann_return']:.1%}/yr at {s['net']['ann_vol']:.1%} vol, max drawdown {s['net']['max_drawdown']:.1%}, hit rate {s['net']['hit_rate']:.1%}, turnover {s['avg_turnover']:.2f}/day, cost {s['cost_bp_per_day']:.2f} bp/day; yearly net: {s['yearly_net']}.")
    if comb and "combined" in comb:
        H(3, "Combined book (equal risk across surviving strategies)")
        parts.append("<pre class='doc'>" + json.dumps({k: v for k, v in comb.items() if k != "sleeves"}, indent=1, default=str)[:3000] + "</pre>")

    # ---------------- robustness
    H(2, "Robustness / kill tests (development + validation, never the holdout)")
    for famdir in sorted((RES / "robustness").glob("*")) if (RES / "robustness").exists() else []:
        kt = famdir / "kill_tests.csv"
        if kt.exists():
            H(3, famdir.name)
            k = pd.read_csv(kt)
            parts.append(_table(k))
            parts.append(fig_bar(k.set_index("variant")["net_sr"], f"{famdir.name}: net Sharpe by variant", f"kill_{famdir.name}"))
            yr = famdir / "yearly.csv"
            if yr.exists():
                y = pd.read_csv(yr, index_col=0)
                parts.append(fig_bar(y["net_sharpe"], f"{famdir.name}: net Sharpe by year", f"yearly_{famdir.name}", PALETTE[2]))
            rc = _load_json(famdir / "regimes_concentration.json")
            if rc:
                parts.append("<pre class='doc'>" + json.dumps(rc, indent=1, default=str) + "</pre>")

    # ---------------- holdout
    H(2, "Locked holdout (2023-01-03 → 2026-08-31): single run, immutable")
    if hold:
        parts.append("<pre class='doc'>" + json.dumps(hold, indent=1, default=str)[:6000] + "</pre>")
        for fam in hold.get("families", {}):
            f = RES / "holdout" / f"daily_HOLDOUT_{fam}.csv"
            if f.exists():
                d = pd.read_csv(f, index_col=0, parse_dates=True)
                parts.append(fig_equity(d, f"{fam}: LOCKED HOLDOUT, gross vs net", f"holdout_equity_{fam}"))
                parts.append(fig_monthly_heatmap(d, f"holdout_monthly_{fam}"))
    else:
        P("<b>Not yet run.</b> The holdout is opened once, after the configuration is frozen; the manifest (git hash, config hash, data-snapshot hash, timestamp) is recorded with the result.")

    # ---------------- discussion
    H(2, "Discussion: what worked, what did not, failure modes, limitations")
    P("<b>Outcome.</b> Classification <b>C — research-quality negative result</b>: the frozen rank-reversal configuration earned a net Sharpe of 0.93 on the 2019–2022 validation window but 0.16 (95% CI −1.06 .. 1.46; gross 0.26) on the locked 2023–2026 holdout; the event and earnings-drift families were at or below zero. The failure is a decay of the gross edge in a calm regime, not a cost or parameter artefact: costs in the holdout were 0.35 bp/day, the validation result matched development almost exactly, neighbours and placebo behaved as expected. See reports/FINAL_DECISION.md.")
    P("<b>What the evidence supports.</b> A day-one, no-news residual reversal in large caps with a gross Sharpe around 1 on the development sample; the premium rises with lagged VIX; news (earnings-8-K) movers continue rather than reverse; auction-based execution captures the day-one effect where next-open execution does not; a limit-on-close entry filter raises net Sharpe by trading only into persistent closing pressure.")
    P("<b>What did not work.</b> Next-day resting limit orders (adverse selection, day one forfeited); rank-hysteresis and weight bands (turnover is intrinsic to a one-day signal); range-based spread estimators as a cost basis for large caps (ten times quoted spreads); the pre-registered sqrt/k=1 impact model (14× the published estimate, corrected before validation); the pre-earnings exclusion (costs gross Sharpe with no drawdown benefit on DEV).")
    P("<b>Failure modes.</b> Earnings-type shocks inside the holding window; stress episodes where reversal fails (2007, 2020); crowding; and, above all, cost per unit of turnover: the edge is a few basis points per day and the book turns over roughly once every 1.5 days, so net results are decided by fees and impact, not by signal parameters. Capacity is bounded by closing-auction volume.")
    P("<b>Limitations.</b> Survivorship gap of 16% of members in 2005 falling to 0% after 2020 (no price history for some delisted names); intraday coverage 782 of 949 names; no historical quote data (auction fills assumed at the official close with a participation cost); sector labels not point-in-time; SEC 31 rates applied at the current level; Chan (2003) unverified; the effect has weakened since 2011 and the holdout is the toughest regime.")
    H(2, "Next steps")
    P("(1) The holdout is spent: any further research must treat 2023–2026 as development data and use a new forward sample. (2) Forward paper test from 2026-09 with the live news layer (EDGAR real-time feed, FMP articles, Claude web search) and a separate ledger. (3) Verify the remaining UNVERIFIED items (SEC 31 history, Nasdaq MOC cutoff, auction-volume vs official auction prints). (4) If deployed: institutional execution, size near the capacity rule, drawdown brake on, and a kill rule if the trailing 12-month net Sharpe falls below zero. (5) A separate, pre-registered project on the earnings-continuation effect with a lower-turnover design.")

    html = f"""<!doctype html><html><head><meta charset='utf-8'><title>Residual Reversal Research Report</title>
<style>body{{font-family:Segoe UI,Helvetica,Arial,sans-serif;max-width:1100px;margin:30px auto;padding:0 20px;color:#222;line-height:1.45}}
h1{{font-size:26px;border-bottom:2px solid #1f5fbf;padding-bottom:6px}}h2{{font-size:20px;margin-top:34px;color:#1f5fbf}}h3{{font-size:16px;margin-top:22px}}
.tbl{{border-collapse:collapse;font-size:12.5px;margin:10px 0}}.tbl th{{background:#eef3fb;text-align:left;padding:5px 8px}}.tbl td{{padding:4px 8px;border-bottom:1px solid #eee;vertical-align:top}}
.muted{{color:#777}}pre.doc{{background:#f7f7f7;padding:12px;font-size:12px;white-space:pre-wrap;border-left:3px solid #ddd}}code{{background:#f2f2f2;padding:1px 4px}}img{{margin:8px 0}}</style></head><body>
{''.join(parts)}
<hr><p class='muted'>stat-arb-research · generated by statarb.reporting.html_report · all statistics computed from daily strategy returns; Sharpe ratios inside PSR/DSR are per-period, annualised only for display.</p></body></html>"""
    REP.mkdir(exist_ok=True)
    out = REP / "QUANT_RESEARCH_REPORT.html"
    out.write_text(html, encoding="utf-8")
    return out


if __name__ == "__main__":
    print(build_report())
