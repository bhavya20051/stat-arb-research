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
    val_fund = _load_json(RES / "validation" / "validation_results_fund.json") or {}
    cap_used = cap.get("primary_capital", 1e6) if cap else 1e6
    P(f"<b>Cost profile of every headline number: market maker (exchange member: closing-auction fee, clearing, SEC 31 and FINRA TAF on sales, 0.3% borrow, Almgren impact on closing-auction volume; no spread on auction fills).</b> Capital ${cap_used/1e6:.0f}M (pre-specified capacity rule), 10% volatility target, gross ≤ 3×, drawdown brake. The prime-brokered-fund profile (auction fee passed through a broker, no rebates) is shown in the last two columns; retail costs were dropped as not applicable to the target firms. Sharpe ratios are annualised from daily net returns.")
    summ_rows = []
    for fam, s in val.items():
        hf = hold.get("families", {}).get(fam, {}) if hold else {}
        hv = hf.get("variants", {}) if hf else {}
        summ_rows.append({"strategy": fam, "DEV net SR": sel.get(fam, {}).get("dev", {}).get("net_sr"), "VAL net SR": s["net"]["sharpe_ann"],
                          "VAL 95% CI": f"{s['net']['sharpe_ci95_ann'][0]:.2f} .. {s['net']['sharpe_ci95_ann'][1]:.2f}", "VAL net ret/yr": s["net"]["ann_return"],
                          "VAL max DD": s["net"]["max_drawdown"], "turnover/day": s["avg_turnover"], "DSR (DEV)": sel.get(fam, {}).get("multiple_testing", {}).get("dsr"),
                          "HOLDOUT net SR": hf.get("holdout_net_sharpe"), "HOLDOUT gross SR": hv.get("base", {}).get("gross_sharpe"), "HOLDOUT net ret/yr": hf.get("holdout_net_ann"), "HOLDOUT max DD": hf.get("holdout_max_dd"),
                          "VAL net SR (fund profile)": val_fund.get(fam, {}).get("net", {}).get("sharpe_ann"), "HOLDOUT net SR (fund profile)": hv.get("profile_prime_brokered_fund", {}).get("net_sharpe")})
    parts.append(_table(pd.DataFrame(summ_rows)))
    P("<b>Locked holdout = 2023-01-03 → 2026-08-31, single pre-declared batch of the frozen configuration; validation = 2019-01-02 → 2022-12-15, one shot; development = 2005–2018 (see the audit notice below on the development window).</b>")

    # ---- second table: prime-brokered-fund profile (same configurations, per-share broker fee, no exchange rebates)
    H(3, "Prime-brokered-fund profile (same frozen configurations)")
    P("Fee schedule (configs/costs.yaml): $0.0012 per share all-in through a prime broker, SEC 31 and FINRA TAF on sales, NSCC clearing, 0.3% borrow, the same Almgren impact on closing-auction volume, no exchange rebates. DEV figures come from the fund-profile rerun of the same 140-candidate grid (results/dev/grid/grid_results_prime_brokered_fund.csv); the robustness column is the fund-profile row of the kill-test suite on 2005–2022; the holdout column is the pre-declared fund-profile variant of the single holdout batch.")
    fund_grid_p = RES / "dev" / "grid" / "grid_results_prime_brokered_fund.csv"
    fund_grid = pd.read_csv(fund_grid_p).set_index("id") if fund_grid_p.exists() else None
    fund_rows = []
    for fam, s in val.items():
        cid = sel.get(fam, {}).get("id")
        hf = hold.get("families", {}).get(fam, {}) if hold else {}
        hv = hf.get("variants", {}).get("profile_prime_brokered_fund", {}) if hf else {}
        kt_p = RES / "robustness" / fam / "kill_tests.csv"
        kt = pd.read_csv(kt_p).set_index("variant") if kt_p.exists() else None
        rob = kt.loc["profile_prime_brokered_fund"] if (kt is not None and "profile_prime_brokered_fund" in kt.index) else None
        g = fund_grid.loc[cid] if (fund_grid is not None and cid in fund_grid.index) else None
        vf = val_fund.get(fam, {})
        fund_rows.append({"strategy": fam, "DEV net SR (fund)": None if g is None else g["net_sr"], "DEV net ret/yr (fund)": None if g is None else g["net_ann"],
                          "DEV cost bp/day (fund)": None if g is None else g["cost_bp"],
                          "VAL net SR (fund)": vf.get("net", {}).get("sharpe_ann"), "VAL net ret/yr (fund)": vf.get("net", {}).get("ann_return"),
                          "VAL max DD (fund)": vf.get("net", {}).get("max_drawdown"), "VAL cost bp/day (fund)": vf.get("cost_bp_per_day"),
                          "DEV+VAL robustness net SR (fund)": None if rob is None else rob["net_sr"],
                          "HOLDOUT net SR (fund)": hv.get("net_sharpe"), "HOLDOUT net ret/yr (fund)": hv.get("net_ann"), "HOLDOUT max DD (fund)": hv.get("max_dd")})
    parts.append(_table(pd.DataFrame(fund_rows)))
    P("Reading the two tables together: the fund profile costs about 0.07 bp/day more than the exchange-member profile at $1M (per-share fee $0.0012 vs $0.0008 plus no rebates), which moves net Sharpe by roughly 0.02–0.05; the difference between profiles is immaterial next to the difference between windows.")

    # ---- audit notice and post-audit table
    pa = _load_json(RES / "post_audit" / "post_audit_results.json") or {}
    H(3, "Red-team audit notice (2026-09-06) — read before using any number above")
    P("An independent, fresh-context red-team review (reports/RED_TEAM_AUDIT.md; 22 findings, 2 critical, 6 high) found that the pre-audit numbers in the two tables above were produced by code with four material defects: (F1) the SPY hedge and the net-exposure correction were themselves gated by the limit-on-close fill rule, so the realized book carried an unhedged market exposure with standard deviation 0.20 of capital (target 0.05) whose sign flipped with the closing tape — about half of the 2005–2022 gross P&L was the product of that exposure and the next day's market return; (F2) the development grid ran from 2005 although the pre-registered rule set the start at the first date with ≥80% intraday coverage (2013-10-23), and the selected configuration's net Sharpe is 1.55 on 2005–2011 versus −0.35 on 2012–2018; (F3) the 15:40 eligibility mask used the full-day residual of day t (an end-of-day quantity); (F4) 'limit-on-close' entries that were cancelled became unconditional market-on-close fills the next day, so only ~20% of entries were actually LOC fills. Further findings: delisting rules were implemented in the engine but never wired into the research runs (F15), pre-split dividends were mis-scaled on split-adjusted intraday series (F9), and several documents overclaimed ('beta-neutral', 'leakage-free', 'validation confirmed development almost exactly'). <b>The reviewer's classification: D for the positive DEV/VAL claims as originally stated; the negative holdout conclusion stands; after repairs the study is a research-quality C.</b> All four code defects plus F9 and F15 were repaired on 2026-09-06 (six new unit tests), the documents were corrected, and the whole pipeline was rerun; the results are below and in the audit section. <b>The locked holdout file was not touched and is not re-run</b>: the 2023–2026 numbers in the post-audit table are a labelled diagnostic of the repaired code, not a second holdout.")
    if pa:
        rows = []
        for key, fr in pa.get("families", {}).items():
            fam, tag = key.split("@")
            vm, vf = fr.get("val_market_maker", {}), fr.get("val_prime_brokered_fund", {})
            dm, dfu = fr.get("diag_2023_2026_market_maker", {}), fr.get("diag_2023_2026_prime_brokered_fund", {})
            rows.append({"strategy": fam, "DEV window": pa["dev_windows"].get(tag), "selected id": fr["selected_id"].replace("C-moc-", ""),
                         "DEV net SR": fr["dev"]["net_sr"], "DSR (DEV)": fr["multiple_testing"].get("dsr"), "DEV net SR 2012–18": fr["dev_era"].get("sr_2012_2018"),
                         "VAL net SR (mm)": vm.get("net_sr"), "VAL net ret/yr (mm)": vm.get("net_ann"), "VAL SR ex-2020–21": vm.get("era", {}).get("sr_ex_2020_2021"),
                         "VAL net SR (fund)": vf.get("net_sr"),
                         "2023–26 net SR (mm, diagnostic)": dm.get("net_sr"), "2023–26 net ret/yr (mm)": dm.get("net_ann"), "2023–26 max DD": dm.get("max_dd"),
                         "2023–26 net SR (fund)": dfu.get("net_sr"), "realized net-exposure std (VAL)": vm.get("exposures", {}).get("net_std"),
                         "market-component share of gross (VAL)": vm.get("market_component", {}).get("share")})
        H(3, "Post-audit results (repaired pipeline; mm = market-maker profile)")
        parts.append(_table(pd.DataFrame(rows)))
        P("Selection on each development window used the unchanged pre-specified rule (max DEV net Sharpe subject to gross ≤ 3, turnover ≤ 2.5, neighbour stability). The pre-registered window (2013-10-23 → 2018-12-14) is the primary; the 2005 window is shown because the pre-audit numbers were produced on it.")
    else:
        P("<i>Post-audit rerun pending (results/post_audit/post_audit_results.json not found).</i>")
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
    cbp = RES / "dev" / "capacity_curve_by_profile.csv"
    if cbp.exists():
        H(3, "Capacity curve by cost profile (development sample, selected configuration, pre-audit code)")
        parts.append(_table(pd.read_csv(cbp)))
        P("Fees scale with traded shares and are flat per unit of capital; impact scales with participation in closing-auction volume raised to the 0.6 power, so it grows with size while the gross edge does not. That is why net Sharpe falls monotonically with capital under both profiles, and why the two profiles converge at large sizes where impact dominates. Caveat from the audit (F11): the participation caps in the config are not enforced in construction, so this curve is a cost-model extrapolation, not a constrained-size simulation.")
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

    # ---------------- red-team audit and post-audit re-analysis
    H(2, "Red-team audit (2026-09-06) and post-audit re-analysis")
    P("Reviewer: an independent fresh-context agent with a hostile brief, read-only access to the repository and the processed data, and its own verification scripts (reports/RED_TEAM_AUDIT.md, verification log with 23 checks). Findings and their disposition:")
    findings = [
        ("F1", "CRITICAL", "SPY hedge and net-exposure correction gated by the LOC fill rule; realized net-exposure std 0.20 vs 0.05 target; ~53% of 2005–2022 gross P&L = net exposure × next-day SPY", "FIXED: hedge re-sized to the filled book and executed MOC, dollar-net clipped to ±5% after the fill decision (limit_orders.loc_fills); test asserts realized |net| ≤ band"),
        ("F2", "CRITICAL", "DEV grid ran from 2005 although the pre-registered start was the first date with ≥80% intraday coverage; selected config SR 1.55 (2005–11) vs −0.35 (2012–18)", "FIXED: coverage table added; selection rerun on the pre-registered window 2013-10-23 → 2018-12-14 (primary) and on the 2005 window (for comparison); era decomposition reported for every window"),
        ("F3", "HIGH", "15:40 eligibility used the full-day residual of day t (jump rule)", "FIXED: daily eligibility lagged one day plus an ex-ante partial-day jump rule at 15:45 (build_moc.ex_ante_eligibility); invariance test added"),
        ("F4", "HIGH", "'LOC' entries classified against previous targets, so cancelled entries became unconditional MOC fills next day (37% of cancellations); fill condition on the intraday bar, not the official close", "FIXED: entries classified against held weights, cancelled entries are re-submitted as LOC, condition evaluated on the official close; fill rate and effective gross reported"),
        ("F5", "HIGH", "Survivorship gap 16% (2005) → 1.2% (2018); 2008 failures missing from the panel; membership keyed on raw ticker", "DOCUMENTED / PARTLY ADDRESSED: the pre-registered window starts where the gap is 5.8% and falls to 1.2%; gap table shown with every result; permanent-id keying remains open"),
        ("F6", "HIGH", "Overclaims in README, interview brief, résumé bullets, FINAL_DECISION ('beta-neutral', 'leakage-free', 'delisting rules applied', 'VAL confirmed DEV almost exactly')", "FIXED: documents rewritten from the post-audit numbers; era decomposition replaces the 'confirmed' sentence"),
        ("F7", "HIGH", "DSR/PBO counted 72 rank-family candidates; ≥140 candidates and ~50 preview/ablation runs influenced the design (DSR 0.62 → 0.51 at N=140, 0.38 at N=300)", "DOCUMENTED: pooled-N DSR figures reported here; registry unchanged (nothing deleted)"),
        ("F8", "HIGH", "Three cost/construction changes made on DEV after observing results (impact model, market-maker profile, pre-earnings exclusion off); holdout config hash describes a config the run did not use", "DOCUMENTED: pre-earnings-exclusion-ON and fund-profile variants are in every robustness table; the retail profile was dropped by the user's directive (target firms are market makers/funds) and is stated as such; StrategySpec defaults vs base.yaml drift recorded as open"),
        ("F9", "MEDIUM", "Raw dividend subtracted from a split-adjusted intraday series (AAPL 2019-08-09 phantom +1.13%)", "FIXED: dividend rescaled to the intraday basis (build_moc.dividend_on_intraday_basis); test on the AAPL case"),
        ("F10", "MEDIUM", "Sector labels not point-in-time; XLC/XLRE names silently ineligible before ETF inception", "OPEN (documented limitation)"),
        ("F11", "MEDIUM", "Liquidity filter is a no-op; participation caps, min positions, sector-net and beta limits in base.yaml are not enforced; Tier-2 article filter never applied", "DOCUMENTED: capacity curve labelled as a cost extrapolation; constraints listed as not implemented; Tier-2 ablation remains a next step"),
        ("F12", "MEDIUM", "P&L concentrated by era (2008; 2020–21) and by day (holdout ex-best-day SR 0.01)", "FIXED: yearly Sharpe, ex-2008, ex-2020–21 and ex-best-day reported for every window"),
        ("F13", "MEDIUM", "Share counts derived from adjusted prices (commissions/TAF mis-scaled in early years; mostly conservative)", "OPEN"),
        ("F14", "MEDIUM", "Best-tier auction fee assumed at $1M; SEC 31 rate constant", "DOCUMENTED (≈0.1 bp/day)"),
        ("F15", "MEDIUM", "Delisting engine path never fed by the pipeline", "FIXED: delisting_events wired into load_feats; rules refined (post-bankruptcy 'Q' tickers → −100%, ticker changes → 0); test added"),
        ("F16", "MEDIUM", "'Single run' should read 'single pre-declared batch of 30 runs'", "FIXED (wording)"),
        ("F17", "MEDIUM", "Validation gate (net SR > 0) is vacuous", "DOCUMENTED; not applied retroactively"),
        ("F18–F22", "LOW", "Reliability tolerance, 15:40 vs 15:45 label, config/doc drift, drawdown rule path, registration mechanics", "DOCUMENTED; decision time now stated as 15:45 with a 15:50 submission cutoff"),
    ]
    parts.append(_table(pd.DataFrame(findings, columns=["#", "severity", "finding (condensed)", "disposition"]), floatfmt="{}"))
    if pa:
        P(f"<b>Post-audit rerun.</b> Generated {pa.get('generated_utc','')[:19]} UTC with the repaired code. Feature panels rebuilt; delisting events wired ({'; '.join(f'{k}: {v}' for k, v in pa.get('loc_fill_stats', {}).items())}).")
        for key, fr in pa.get("families", {}).items():
            fam, tag = key.split("@")
            H(3, f"{fam} — development window {pa['dev_windows'].get(tag)} → 2018-12-14")
            P(f"Selected: <code>{fr['selected_id']}</code>; DEV net SR {fr['dev']['net_sr']:.2f} (gross {fr['dev']['gross_sr']:.2f}), DSR {fr['multiple_testing'].get('dsr', float('nan')):.2f}, PBO {fr['multiple_testing'].get('pbo_cscv') if fr['multiple_testing'].get('pbo_cscv') is not None else 'n/a'}; DEV era: 2005–11 {fr['dev_era'].get('sr_2005_2011')}, 2012–18 {fr['dev_era'].get('sr_2012_2018')}, ex-2008 {fr['dev_era'].get('sr_ex_2008')}.")
            era_rows = []
            for wname in ("val_market_maker", "val_prime_brokered_fund", "diag_2023_2026_market_maker", "diag_2023_2026_prime_brokered_fund"):
                w = fr.get(wname, {})
                if not w:
                    continue
                era_rows.append({"window/profile": wname, "net SR": w.get("net_sr"), "95% CI": f"{w['sharpe_ci95'][0]:.2f} .. {w['sharpe_ci95'][1]:.2f}", "gross SR": w.get("gross_sr"),
                                 "net ret/yr": w.get("net_ann"), "net vol": w.get("net_vol"), "max DD": w.get("max_dd"), "turnover/day": w.get("turnover"), "cost bp/day": w.get("cost_bp"),
                                 "SR ex-2020–21": w.get("era", {}).get("sr_ex_2020_2021"), "SR ex-best day": w.get("era", {}).get("sr_ex_best_day"),
                                 "gross exp": w.get("exposures", {}).get("gross_mean"), "net-exp std": w.get("exposures", {}).get("net_std"),
                                 "market-component share": w.get("market_component", {}).get("share"), "net SR ex-market": w.get("market_component", {}).get("net_sr_ex_market")})
            parts.append(_table(pd.DataFrame(era_rows)))
            yr = {}
            for wname in ("val_market_maker", "diag_2023_2026_market_maker"):
                yr.update(fr.get(wname, {}).get("era", {}).get("yearly_sr", {}))
            yr = {**{k: v for k, v in fr["dev_era"].get("yearly_sr", {}).items()}, **yr}
            if yr:
                parts.append(fig_bar(pd.Series(yr), f"{fam} ({tag}): net Sharpe by year, DEV → VAL → 2023–26 diagnostic (market-maker profile)", f"pa_yearly_{fam}_{tag}"))
            for wname in ("val", "diag_2023_2026"):
                f = RES / "post_audit" / f"daily_{fam}_{tag}_market_maker_{wname}.csv"
                if f.exists():
                    d = pd.read_csv(f, index_col=0, parse_dates=True)
                    parts.append(fig_equity(d, f"{fam} ({tag}) {wname}: gross vs net, repaired pipeline", f"pa_equity_{fam}_{tag}_{wname}"))
        kt_p = RES / "post_audit" / "robustness" / "rank_reversal" / "kill_tests.csv"
        if kt_p.exists():
            H(3, "Post-audit robustness (rank reversal, pre-registered development window + validation)")
            parts.append(_table(pd.read_csv(kt_p)))
        cbp2 = RES / "post_audit" / "capacity_curve_by_profile.csv"
        if cbp2.exists():
            H(3, "Post-audit capacity curve by cost profile (pre-registered development window)")
            parts.append(_table(pd.read_csv(cbp2)))
    else:
        P("<i>Post-audit rerun pending.</i>")

    # ---------------- complete PM data set (post-audit, all families x both profiles)
    fm = _load_json(RES / "post_audit" / "full_metrics.json") or {}
    H(2, "Complete performance data set: three strategies × two institutional profiles (repaired pipeline)")
    if fm:
        P(f"Development windows: pre-registered {fm['dev_window'][0]} → {fm['dev_window'][1]} and, for comparison, 2005-01-03 → {fm['dev_window'][1]} (each family is shown with the configuration selected on each window); validation {fm['val_window'][0]} → {fm['val_window'][1]}, diagnostic {fm['diagnostic_window'][0]} → {fm['diagnostic_window'][1]} (not a holdout; see the audit notice). Capital ${fm['capital']/1e6:.0f}M, 10% vol target, gross ≤ 3×, drawdown brake. Every statistic is computed from the daily net return series of the run (results/post_audit/daily_full_*.csv).")
        def _row(fam, prof, wname, d):
            n, g = d["net"], d["gross"]
            return {"strategy": fam, "profile": prof, "window": wname, "net ret/yr": n["ann_return"], "net vol": n["ann_vol"], "net SR": n["sharpe_ann"],
                    "SR 95% CI": f"{d['sharpe_ci95_ann'][0]:.2f} .. {d['sharpe_ci95_ann'][1]:.2f}", "SR SE (Lo)": n.get("sharpe_se_autocorr_ann"), "gross SR": g["sharpe_ann"],
                    "Sortino": n.get("sortino_ann"), "Calmar": n.get("calmar"), "max DD": d["max_drawdown"], "longest DD (days)": d["longest_drawdown_days"], "time in DD": d["time_in_drawdown"],
                    "hit rate": n.get("hit_rate"), "profit factor": n.get("profit_factor"), "% +months": d["pct_positive_months"], "skew": n.get("skew"), "kurtosis": n.get("kurtosis"), "PSR>0": n.get("psr_vs_zero"),
                    "gross exp": d["avg_gross_exposure"], "net exp mean": d["avg_net_exposure"], "net exp std": d["net_exposure_std"], "beta SPY": d["beta_to_spy"],
                    "mkt-component share": d["market_component_share"], "SR ex-market": d["net_sharpe_ex_market"], "turnover/day": d["turnover_per_day"], "cost bp/day": d["cost_bp_total"],
                    "fees bp": d["cost_bp_per_day"].get("commission"), "reg+clearing bp": d["cost_bp_per_day"].get("fees"), "impact bp": d["cost_bp_per_day"].get("impact"), "borrow bp": d["cost_bp_per_day"].get("borrow"),
                    "best day": f"{d['best_day'][0]} {d['best_day'][1]*100:+.2f}%", "worst day": f"{d['worst_day'][0]} {d['worst_day'][1]*100:+.2f}%", "n days": n["n_days"]}
        rows = []
        for key, fr in fm["families"].items():
            fam, tag = key.split("@")
            for prof, pr in fr["profiles"].items():
                for wname in ("dev", "val", "diag_2023_2026"):
                    rows.append({**_row(fam, prof, wname, pr[wname]), "DEV window": fr["dev_window"][0]})
        parts.append(_table(pd.DataFrame(rows)))
        for key, fr in fm["families"].items():
            fam, tag = key.split("@")
            H(3, f"{fam} (selected on {fr['dev_window'][0]} → {fr['dev_window'][1]}): <code>{fr['selected_id'].replace('C-moc-', '')}</code> — DSR {fr['multiple_testing'].get('dsr', float('nan')):.2f}, PBO {fr['multiple_testing'].get('pbo_cscv') if fr['multiple_testing'].get('pbo_cscv') is not None else 'n/a'}")
            yrows = []
            for prof, pr in fr["profiles"].items():
                yr = {}
                for wname in ("dev", "val", "diag_2023_2026"):
                    yr.update(pr[wname]["yearly_net"])
                yrows.append({"profile": prof, **{k: v for k, v in sorted(yr.items())}})
            P("Net return by calendar year (fraction of capital):")
            parts.append(_table(pd.DataFrame(yrows), floatfmt="{:+.3f}"))
            srr = []
            for prof, pr in fr["profiles"].items():
                yr = {}
                for wname in ("dev", "val", "diag_2023_2026"):
                    yr.update({k: v for k, v in pr[wname]["yearly_sharpe"].items()})
                srr.append({"profile": prof, **{k: v for k, v in sorted(yr.items())}})
            P("Net Sharpe by calendar year:")
            parts.append(_table(pd.DataFrame(srr), floatfmt="{:.2f}"))
            mm = fr["profiles"]["market_maker"]
            monthly = {}
            for wname in ("dev", "val", "diag_2023_2026"):
                monthly.update(mm[wname]["monthly_net"])
            ms = pd.Series(monthly)
            ms.index = pd.to_datetime(ms.index)
            heat = ms.groupby([ms.index.year, ms.index.month]).sum().unstack()
            heat.columns = [f"{m:02d}" for m in heat.columns]
            P("Monthly net returns, market-maker profile (rows = years):")
            parts.append(_table((heat * 100).round(2).rename_axis("year").reset_index(), floatfmt="{:+.2f}"))
            for prof, pr in fr["profiles"].items():
                kt = pd.DataFrame(pr["kill_tests"])
                if not kt.empty:
                    P(f"Kill tests, {prof} profile, development + validation ({fr['dev_window'][0]} → {fm['val_window'][1]}):")
                    parts.append(_table(kt))
                capd = pd.DataFrame(pr["capacity"])
                if not capd.empty:
                    P(f"Capacity curve, {prof} profile, development window:")
                    parts.append(_table(capd))
            for prof in ("market_maker",):
                for wname in ("val", "diag_2023_2026"):
                    f = RES / "post_audit" / f"daily_full_{key}_{prof}_{wname}.csv"
                    if f.exists():
                        d = pd.read_csv(f, index_col=0, parse_dates=True)
                        parts.append(fig_equity(d, f"{fam} [{tag}] ({prof}) {wname}: gross vs net", f"paf_equity_{key}_{prof}_{wname}"))
    else:
        P("<i>results/post_audit/full_metrics.json not found; run statarb.research.run_post_audit_full.</i>")

    # ---------------- discussion
    H(2, "Discussion: what worked, what did not, failure modes, limitations")
    P("<b>Outcome.</b> Classification <b>C — research-quality negative result</b>, reached twice: by the frozen pipeline on the locked holdout (net Sharpe 0.16, 95% CI −1.06 .. 1.46) and, after the red-team audit, by the repaired pipeline on every window (post-audit tables above). The pre-audit development and validation Sharpes (0.89 / 0.93) are withdrawn as evidence of an edge: roughly half of that gross P&L was an unintended market-timing exposure created by the fill rule, the development window violated its own pre-registration and the number rested on 2005–2011, and the validation number rested on 2020–2021 (ex-2020–21: −0.82). See reports/RED_TEAM_AUDIT.md and reports/FINAL_DECISION.md.")
    P("<b>What the evidence supports.</b> A day-one, no-news residual reversal existed in the 2005–2011 large-cap panel and reappeared in the 2020–2021 stress period; it rises with lagged VIX; earnings-8-K movers continue rather than reverse; auction fills matter because the edge is a few basis points. It does not support a tradeable edge at this horizon in this universe after 2012 under either cost profile.")
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
    # artifact variant: no document skeleton; token-based light/dark theme; Google Fonts
    art = """<title>Residual Reversal Holdout Study</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Source+Serif+4:wght@600;700&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
:root{--ground:#f7f8fa;--surface:#ffffff;--ink:#1b2433;--ink-2:#5b6573;--rule:#d7dce4;--accent:#1f5fbf;--accent-soft:#e8eef9;--neg:#c8404f;--code:#eef1f5}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--ground:#12161c;--surface:#181d25;--ink:#e6e9ee;--ink-2:#9aa4b2;--rule:#2b323c;--accent:#7aa6ec;--accent-soft:#1d2a40;--neg:#e0717d;--code:#1f252e}}
:root[data-theme="dark"]{--ground:#12161c;--surface:#181d25;--ink:#e6e9ee;--ink-2:#9aa4b2;--rule:#2b323c;--accent:#7aa6ec;--accent-soft:#1d2a40;--neg:#e0717d;--code:#1f252e}
body{background:var(--ground);color:var(--ink);font-family:"IBM Plex Sans",Segoe UI,Helvetica,Arial,sans-serif;font-size:15px;line-height:1.55;margin:0}
.wrap{max-width:960px;margin:0 auto;padding:36px 22px 60px}
h1{font-family:"Source Serif 4",Georgia,serif;font-weight:700;font-size:30px;line-height:1.2;text-wrap:balance;margin:0 0 6px;border-bottom:2px solid var(--accent);padding-bottom:10px}
h2{font-family:"Source Serif 4",Georgia,serif;font-weight:600;font-size:21px;margin:40px 0 10px;color:var(--accent);text-wrap:balance}
h3{font-size:16px;font-weight:600;margin:24px 0 8px}
p{max-width:72ch}
.muted{color:var(--ink-2)}
.tbl-wrap{overflow-x:auto}
.tbl{border-collapse:collapse;font-size:12.5px;margin:10px 0;font-family:"IBM Plex Mono",Consolas,monospace;font-variant-numeric:tabular-nums}
.tbl th{background:var(--accent-soft);text-align:left;padding:6px 9px;font-family:"IBM Plex Sans",sans-serif;font-weight:600;letter-spacing:.02em;text-transform:uppercase;font-size:11px}
.tbl td{padding:5px 9px;border-bottom:1px solid var(--rule);vertical-align:top}
pre.doc{background:var(--code);padding:12px 14px;font-size:12px;white-space:pre-wrap;border-left:3px solid var(--rule);font-family:"IBM Plex Mono",Consolas,monospace;max-width:100%;overflow-x:auto}
code{background:var(--code);padding:1px 5px;border-radius:3px;font-family:"IBM Plex Mono",Consolas,monospace;font-size:12.5px}
img{margin:8px 0;background:#fff;border:1px solid var(--rule);border-radius:4px}
hr{border:0;border-top:1px solid var(--rule);margin:36px 0}
</style>
<div class="wrap">""" + "".join(parts).replace('<table border="0" class="dataframe tbl">', '<div class="tbl-wrap"><table border="0" class="dataframe tbl">').replace("</table>", "</table></div>") + """
<hr><p class="muted">stat-arb-research - generated by statarb.reporting.html_report - all statistics computed from daily strategy returns; Sharpe ratios inside PSR/DSR are per-period, annualised only for display.</p></div>"""
    (REP / "artifact_report.html").write_text(art, encoding="utf-8")
    return out


if __name__ == "__main__":
    print(build_report())
