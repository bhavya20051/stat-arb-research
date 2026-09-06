"""Client-facing due-diligence report for quantitative portfolio managers (revised after reports/REPORT_REVIEW.md).

Reads only frozen result files (results/post_audit/full_metrics.json, results/post_audit/post_audit_results.json,
results/post_audit/daily_full_*.csv, results/holdout/holdout_results.json, results/validation/*) and writes
reports/PM_REPORT.html (standalone) and reports/pm_artifact.html (no document skeleton, for hosting).
Nothing in this module computes a new strategy result; every number is read from disk or derived arithmetically
from the daily return series of a recorded run.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from statarb.reporting.html_report import RES, REP, _load_json, _table, fig_bar, fig_equity, fig_monthly_heatmap

FAM_LABEL = {"rank_reversal": "Rank residual reversal", "event_reversal": "Event residual reversal", "earnings_drift": "Earnings-8-K drift"}
PROF_LABEL = {"market_maker": "Exchange member (market maker)", "prime_brokered_fund": "Prime-brokered fund"}
PROF_SHORT = {"market_maker": "market maker", "prime_brokered_fund": "fund"}
WIN_SHORT = {"dev": "DEV", "val": "VAL", "diag_2023_2026": "2023–26"}


def _isnan(v):
    return v is None or (isinstance(v, float) and np.isnan(v))


def _pct(v, d=1, signed=True):
    if _isnan(v):
        return ""
    return f"{v*100:+.{d}f}%" if signed else f"{v*100:.{d}f}%"


def _f(v, d=2):
    return "" if _isnan(v) else f"{v:.{d}f}"


def _unlev(d):
    g = d.get("avg_gross_exposure") or 0.0
    return d["net"]["ann_return"] / g if g > 1e-6 else None


def _lev10(d):
    v = d["net"].get("ann_vol") or 0.0
    return d["net"]["ann_return"] * (0.10 / v) if v > 1e-9 else None


def _gross_for_10(d):
    v = d["net"].get("ann_vol") or 0.0
    g = d.get("avg_gross_exposure") or 0.0
    return g * (0.10 / v) if v > 1e-9 else None


def _sr(x: pd.Series):
    x = x.dropna()
    return float(x.mean() / x.std(ddof=1) * np.sqrt(252)) if len(x) > 20 and x.std(ddof=1) > 0 else None


def _daily(key, prof, w):
    f = RES / "post_audit" / f"daily_full_{key}_{prof}_{w}.csv"
    return pd.read_csv(f, index_col=0, parse_dates=True) if f.exists() else None


def _active(d: pd.DataFrame) -> dict:
    """Share of days with a position, hit rate over days with a non-zero net return, Sharpe without the best day."""
    act = (d["gross_exposure"] > 1e-9)
    nz = d["net_ret"][d["net_ret"] != 0]
    return {"days_in_market": float(act.mean()), "hit_rate_active": float((nz > 0).mean()) if len(nz) else None,
            "sr_ex_best_day": _sr(d["net_ret"].drop(d["net_ret"].idxmax())) if len(d) > 30 else None}


def _yearly(key, prof) -> pd.DataFrame:
    """Per-year net return, that year's own average gross, active days, row count and Sharpe across the three windows."""
    frames = [x for w in ("dev", "val", "diag_2023_2026") if (x := _daily(key, prof, w)) is not None]
    if not frames:
        return pd.DataFrame()
    d = pd.concat(frames)
    d = d[~d.index.duplicated()]
    g = d.groupby(d.index.year)
    out = pd.DataFrame({"net": g["net_ret"].sum(), "gross": g["gross_exposure"].mean(),
                        "active": g["gross_exposure"].apply(lambda s: int((s > 1e-9).sum())), "rows": g.size(), "sr": g["net_ret"].apply(_sr)})
    out["partial"] = out["rows"] < 200
    return out


def _capacity_rule(rows: list) -> str:
    df = pd.DataFrame(rows)
    if df.empty or df["net_SR"].max() <= 0:
        return "none (no positive net Sharpe at any size)"
    ok = df[df["net_SR"] >= 0.9 * df["net_SR"].max()]
    return f"${ok['capital_$M'].max():.0f}M"


def build_pm_report():
    fm = _load_json(RES / "post_audit" / "full_metrics.json") or {}
    pa = _load_json(RES / "post_audit" / "post_audit_results.json") or {}
    hold = _load_json(RES / "holdout" / "holdout_results.json") or {}
    val_pre = _load_json(RES / "validation" / "validation_results.json") or {}
    sel_pre = _load_json(RES / "validation" / "selection.json") or {}
    parts = []
    H = lambda lvl, t, cls="": parts.append(f"<h{lvl}{' class=' + chr(34) + cls + chr(34) if cls else ''}>{t}</h{lvl}>")
    P = lambda t, cls="": parts.append(f"<p{' class=' + chr(34) + cls + chr(34) if cls else ''}>{t}</p>")
    T = lambda df: parts.append("<div class='tbl-wrap'>" + _table(df, "{}") + "</div>")
    fams = fm.get("families", {})
    cap = fm.get("capital", 1e6)
    vintage = (fm.get("generated_utc") or "")[:16].replace("T", " ")
    act = {}
    for key, fr in fams.items():
        for prof in fr["profiles"]:
            for w in ("dev", "val", "diag_2023_2026"):
                d = _daily(key, prof, w)
                act[(key, prof, w)] = _active(d) if d is not None else {}

    def label(key):
        fam, tag = key.split("@")
        return FAM_LABEL.get(fam, fam), ("pre-registered 2013-10-23 → 2018" if tag == "prereg_2013" else "2005-01-03 → 2018 (rejected by the audit)")

    def cell(key, prof, w):
        return fams[key]["profiles"][prof][w]

    # ------------------------------------------------------------------ 1. bottom line
    parts.append(f"<div class='eyebrow'>Due-diligence report · stat-arb-research · results generated {vintage} UTC</div>")
    H(1, "Residual short-term reversal in U.S. large caps")
    P("Three closing-auction strategies on the point-in-time S&P 500, tested under two institutional cost profiles with a pre-registered protocol, a locked holdout, an independent adversarial audit of the code, a full rerun after the audit's repairs, and an independent review of this report against the result files.", "lede")
    H(2, "1. Bottom line")
    P("<b>Recommendation: do not allocate.</b> No configuration selected under the pre-registered protocol holds a positive net Sharpe ratio across the development, validation and 2023–2026 windows under either cost profile; the positive cells that do appear are single windows whose confidence intervals span zero, or configurations selected on the 2005–2018 window that the audit rejected. The pre-audit in-sample figures that had looked attractive (development 0.89, validation 0.93) are withdrawn: roughly half of that gross P&amp;L was an unintended market-timing exposure created by a fill-rule defect. The single locked holdout (frozen before the audit, never re-run) returned a net Sharpe of 0.16 with a confidence interval spanning zero. Classification: <b>C — research-quality negative result</b>.")
    ev = fams.get("event_reversal@full_2005")
    if ev:
        dv, dd = ev["profiles"]["market_maker"]["val"], ev["profiles"]["market_maker"]["diag_2023_2026"]
        era = pa.get("families", {}).get("event_reversal@full_2005", {}).get("dev_era", {})
        P(f"<b>The one cell an allocator will ask about.</b> The event-reversal configuration selected on the 2005–2018 window (|z| ≥ 2, hold 3, limit-on-close) earned a net Sharpe of {dv['net']['sharpe_ann']:.2f} on validation and {dd['net']['sharpe_ann']:.2f} on 2023–2026 ({_pct(dd['net']['ann_return'])} per year as run at {_pct(dd['net']['ann_vol'])} realized volatility, {_pct(_unlev(dd))} unlevered per 1× gross, max drawdown {_pct(dd['max_drawdown'])}) after the repairs, against −0.02 for the same configuration on the frozen holdout. That result was selected outside the pre-registered window (its development Sharpe is {_f(era.get('sr_2005_2011'))} on 2005–2011 and {_f(era.get('sr_2012_2018'))} on 2012–2018), it is one of six family × window cells examined once on a spent window after four simultaneous code changes, and its book runs at {_f(dd['avg_gross_exposure'])}× gross. It is a forward-test candidate, not evidence; see sections 8 and 9.")
    if fams:
        rows = []
        for key, fr in fams.items():
            fam_l, sel_l = label(key)
            for prof, pr in fr["profiles"].items():
                r = {"strategy": fam_l, "selected on": sel_l, "profile": PROF_SHORT[prof]}
                for w in ("dev", "val", "diag_2023_2026"):
                    d = pr[w]
                    r[f"{WIN_SHORT[w]} net SR"] = _f(d["net"]["sharpe_ann"])
                    r[f"{WIN_SHORT[w]} ret/yr as run"] = _pct(d["net"]["ann_return"])
                    r[f"{WIN_SHORT[w]} unlevered"] = _pct(_unlev(d))
                    r[f"{WIN_SHORT[w]} at 10% vol"] = _pct(_lev10(d))
                    r[f"{WIN_SHORT[w]} max DD"] = _pct(d["max_drawdown"])
                rows.append(r)
        T(pd.DataFrame(rows))
        g_all = [pr[w]["avg_gross_exposure"] for fr in fams.values() for pr in fr["profiles"].values() for w in ("dev", "val", "diag_2023_2026")]
        g10 = [_gross_for_10(pr[w]) for fr in fams.values() for pr in fr["profiles"].values() for w in ("dev", "val", "diag_2023_2026")]
        g10 = [x for x in g10 if x is not None]
        rank_g = [pr[w]["avg_gross_exposure"] for k, fr in fams.items() if k.startswith("rank") for pr in fr["profiles"].values() for w in ("dev", "val", "diag_2023_2026")]
        ev_g = [pr[w]["avg_gross_exposure"] for k, fr in fams.items() if not k.startswith("rank") for pr in fr["profiles"].values() for w in ("dev", "val", "diag_2023_2026")]
        dim = [act[(k, p, w)].get("days_in_market") for k, fr in fams.items() if not k.startswith("rank") for p in fr["profiles"] for w in ("dev", "val", "diag_2023_2026") if act.get((k, p, w))]
        P("Windows: DEV = the development window on which the configuration was selected (the pre-registered 2013-10-23 → 2018-12-14 window, and for comparison the 2005-01-03 → 2018-12-14 window that the pre-audit study used; both are shown because the selections differ and the difference is itself a finding); VAL = one-shot validation 2019-01-02 → 2022-12-15; 2023–26 = post-audit diagnostic run of the repaired pipeline on 2023-01-03 → 2026-08-31 (the frozen holdout on the same dates is in section 6). Capital $" + f"{cap/1e6:.0f}" + "M, 10% volatility target, gross ≤ 3×, drawdown brake (halve at −10%, restore at −5%).", "muted")
        P(f"<b>Three return bases are shown for every window.</b> <i>As run</i> = the backtest's net return on capital under the leverage policy actually applied (annualised geometrically from the uncompounded daily series). <i>Unlevered</i> = as-run return divided by the window-average realized gross exposure, i.e. the return per 1× gross book, on the capital the strategy actually deploys. <i>At 10% vol</i> = as-run return × (10% / realized volatility), the return the same book would earn if scaled linearly to the volatility target; the gross exposure that requires is in section 4 ({min(g10):.1f}×–{max(g10):.1f}× across all cells, inside the 3× cap) and the figure is an upper bound because impact grows faster than linearly with size. Realized books are small: the rank books run at {min(rank_g):.2f}×–{max(rank_g):.2f}× gross because only about 19% of limit-on-close entries fill and the volatility target is computed on the targeted rather than the filled book; the event and earnings books run at {min(ev_g):.2f}×–{max(ev_g):.2f}× gross because they are episodic, sized by an ex-ante expected entrant count and in the market on {min(dim)*100:.0f}–{max(dim)*100:.0f}% of days.", "muted")
    else:
        P("<i>Complete data set not yet generated (results/post_audit/full_metrics.json missing).</i>")

    # ------------------------------------------------------------------ 2. strategies
    H(2, "2. What was tested")
    T(pd.DataFrame([
        {"strategy": FAM_LABEL["rank_reversal"], "signal": "z-scored residual return (market + sector betas, 250-day window) over the last k days incl. the partial day to 15:45 ET", "book": "long bottom quantile / short top quantile among no-news, non-jump names; k overlapping daily tranches; dollar-, sector- and beta-hedged (SPY)", "execution": "limit-on-close orders at 15:45, fill at the official close only if the close extends the move by δσ; exits MOC", "candidates": "72 (lookback × holding × quantiles × VIX gate × execution)"},
        {"strategy": FAM_LABEL["event_reversal"], "signal": "same residual score, but only names whose |z| exceeds an entry threshold", "book": "equal-weight event positions sized by an ex-ante expected entrant count; held k days; episodic (flat when no name qualifies)", "execution": "MOC or LOC (registered variants)", "candidates": "48"},
        {"strategy": FAM_LABEL["earnings_drift"], "signal": "sign of the residual move on a day with an earnings 8-K (item 2.02) accepted before 15:40 ET; continuation, not reversal; volume- and timing-conditioned variants", "book": "event positions in the direction of the move, held k days; episodic", "execution": "market-on-close", "candidates": "20"},
    ]))
    P("Universe: point-in-time S&P 500 membership from the change list (1,525 events, delisted names included, delisting returns applied). Data: FMP daily and 15-minute bars, SEC EDGAR 8-K acceptance timestamps (255,058 filings), FMP articles for the news layer. Decision time 15:45 ET (signal from the 15:30–15:45 bar), submission before the 15:50 NYSE cutoff.")

    # ------------------------------------------------------------------ 3. cost profiles
    H(2, "3. Cost profiles")
    T(pd.DataFrame([
        {"component": "Closing-auction execution fee", PROF_LABEL["market_maker"]: "$0.0008 / share (exchange member, tiered)", PROF_LABEL["prime_brokered_fund"]: "$0.0012 / share all-in through the prime broker"},
        {"component": "Exchange rebates", PROF_LABEL["market_maker"]: "none on auction fills (add $0.0025 / take $0.0029 on continuous, not used)", PROF_LABEL["prime_brokered_fund"]: "none"},
        {"component": "Clearing (NSCC)", PROF_LABEL["market_maker"]: "2.6e-6 of notional", PROF_LABEL["prime_brokered_fund"]: "same"},
        {"component": "SEC 31 / FINRA TAF (sales)", PROF_LABEL["market_maker"]: "20.6e-6 of notional / $0.000195 per share (cap $9.79)", PROF_LABEL["prime_brokered_fund"]: "same"},
        {"component": "Stock borrow", PROF_LABEL["market_maker"]: "0.3% / yr on short notional", PROF_LABEL["prime_brokered_fund"]: "0.3% / yr"},
        {"component": "Market impact", PROF_LABEL["market_maker"]: "Almgren et al. (2005): η = 0.142, β = 0.6 on participation in closing-auction volume", PROF_LABEL["prime_brokered_fund"]: "same"},
        {"component": "Spread", PROF_LABEL["market_maker"]: "none on auction fills (stress: +5 bp per side)", PROF_LABEL["prime_brokered_fund"]: "none (stress: +5 bp)"},
    ]))
    P("Sources are documented in reports/market_maker_cost_research.md (exchange fee schedules, NSCC, SEC and FINRA notices). The retail profile was dropped at the sponsor's request as irrelevant to institutional deployment. The two profiles differ by 0.01–0.03 in net Sharpe in every cell.")

    # ------------------------------------------------------------------ 4. full data set
    H(2, "4. Performance data set (repaired pipeline)")
    if fams:
        for key, fr in fams.items():
            fam, tag = key.split("@")
            fam_l, sel_l = label(key)
            H(3, f"{fam_l}, selected on {sel_l} — <code>{fr['selected_id'].replace('C-moc-', '')}</code>")
            mt = fr.get("multiple_testing", {})
            dsr_txt = _f(mt.get("dsr")) if not _isnan(mt.get("dsr")) else "not computable (several candidates in this family traded nothing, so the family's Sharpe dispersion is undefined)"
            pbo = mt.get("pbo_cscv")
            pbo_txt = _f(pbo) + (" (a value near 0 for an episodic book that is flat most days reflects near-identical candidate paths, not an absence of selection risk)" if (pbo is not None and pbo < 0.05) else "")
            P(f"Selected by the pre-specified rule on this development window from {mt.get('n_candidates', '?')} registered candidates. Deflated Sharpe ratio {dsr_txt}; probability of backtest overfitting (CSCV) {pbo_txt}; PSR vs zero on DEV {_f(mt.get('psr_vs_zero'))}.", "muted")
            rows = []
            for prof, pr in fr["profiles"].items():
                for w in ("dev", "val", "diag_2023_2026"):
                    d = pr[w]
                    n, g = d["net"], d["gross"]
                    a = act.get((key, prof, w), {})
                    rows.append({"profile": PROF_SHORT[prof], "window": WIN_SHORT[w], "days in market": _pct(a.get("days_in_market"), 0, signed=False),
                                 "net ret/yr as run": _pct(n["ann_return"]), "avg gross (leverage used)": _f(d["avg_gross_exposure"]) + "×", "unlevered ret/yr (per 1× gross)": _pct(_unlev(d)),
                                 "ret/yr at 10% vol": _pct(_lev10(d)), "gross needed for 10% vol": _f(_gross_for_10(d), 1) + "×",
                                 "net vol as run": _pct(n["ann_vol"]), "net SR": _f(n["sharpe_ann"]), "SR 95% CI": f"{d['sharpe_ci95_ann'][0]:.2f} .. {d['sharpe_ci95_ann'][1]:.2f}",
                                 "gross SR": _f(g["sharpe_ann"]), "Sortino": _f(n.get("sortino_ann")), "Calmar": _f(n.get("calmar")), "max DD": _pct(d["max_drawdown"]),
                                 "longest DD": f"{d['longest_drawdown_days']} d", "hit rate (active days)": _pct(a.get("hit_rate_active"), 1, signed=False), "+months": _pct(d["pct_positive_months"], 0, signed=False),
                                 "profit factor": _f(n.get("profit_factor")), "skew": _f(n.get("skew")), "kurtosis": _f(n.get("kurtosis"), 1), "PSR>0": _f(n.get("psr_vs_zero")),
                                 "net-exp std": _f(d["net_exposure_std"], 3), "β SPY": _f(d["beta_to_spy"], 3),
                                 "turnover/day": _f(d["turnover_per_day"]), "cost bp/day": _f(d["cost_bp_total"]), "worst day": f"{d['worst_day'][0]} {d['worst_day'][1]*100:+.2f}%"})
            T(pd.DataFrame(rows))
            P("Hit rate is computed over days on which the book had a non-zero return; 'days in market' is the share of trading days with any position. Sortino, Calmar, skew and kurtosis are computed on all days including flat ones.", "muted")
            yrows = []
            for prof in fr["profiles"]:
                y = _yearly(key, prof)
                if y.empty:
                    continue
                yl = {f"{yr}{'*' if p else ''}": _pct(v) for yr, v, p in zip(y.index, y["net"], y["partial"])}
                yu = {f"{yr}{'*' if p else ''}": (_pct(v / g) if (g > 1e-6 and a >= 20) else "") for yr, v, g, a, p in zip(y.index, y["net"], y["gross"], y["active"], y["partial"])}
                yrows.append({"profile": PROF_SHORT[prof], "basis": "as run (policy leverage)", **yl})
                yrows.append({"profile": PROF_SHORT[prof], "basis": "unlevered (per 1× gross, that year's own average gross; blank if < 20 active days)", **yu})
            if yrows:
                P("Net return by calendar year, as run and unlevered (* = partial year: 2013 has 46 trading days after the pre-registered start; 2026 ends 2026-08-31):")
                T(pd.DataFrame(yrows))
            y = _yearly(key, "market_maker")
            if not y.empty:
                full = y[~y["partial"]]["sr"].dropna()
                if len(full):
                    parts.append(fig_bar(full, f"{fam_l} (selected on {sel_l}): net Sharpe by full calendar year, DEV → VAL → 2023–26 (market-maker profile; partial years excluded)", f"pm_yearly_{key}"))
            for w in ("dev", "val", "diag_2023_2026"):
                d = _daily(key, "market_maker", w)
                if d is not None:
                    wl = {"dev": f"development {fr['dev_window'][0]} → {fr['dev_window'][1]}", "val": "validation 2019-01-02 → 2022-12-15", "diag_2023_2026": "2023-01-03 → 2026-08-31 diagnostic"}[w]
                    parts.append(fig_equity(d, f"{fam_l} (selected on {sel_l}): {wl}, gross vs net, compounded (market-maker profile)", f"pm_eq_{key}_{w}"))
            if fam == "rank_reversal":
                d = _daily(key, "market_maker", "dev")
                if d is not None:
                    parts.append(fig_monthly_heatmap(d, f"pm_heat_{key}_dev"))
            P("Equity figures compound the daily net returns; the tables use the uncompounded path, so drawdowns in the figures can differ from the tables by a few tenths of a percent.", "muted")

    # ------------------------------------------------------------------ 5. costs, capacity, robustness
    H(2, "5. Cost decomposition, capacity and stress tests")
    if fams:
        rows = []
        for key, fr in fams.items():
            fam_l, sel_l = label(key)
            for prof, pr in fr["profiles"].items():
                c = pr["val"]["cost_bp_per_day"]
                rows.append({"strategy": fam_l, "selected on": sel_l, "profile": PROF_SHORT[prof], "fees": _f(c.get("commission"), 3), "reg + clearing": _f(c.get("fees"), 3), "impact": _f(c.get("impact"), 3), "borrow": _f(c.get("borrow"), 3),
                             "total bp/day": _f(pr["val"]["cost_bp_total"], 3), "gross SR": _f(pr["val"]["gross"]["sharpe_ann"]), "net SR": _f(pr["val"]["net"]["sharpe_ann"])})
        P("Daily cost in basis points of capital by component (validation window):")
        T(pd.DataFrame(rows))
        rows = []
        caps = {}
        for key, fr in fams.items():
            fam_l, sel_l = label(key)
            for prof, pr in fr["profiles"].items():
                caps[(key, prof)] = _capacity_rule(pr["capacity"])
                for r in pr["capacity"]:
                    rows.append({"strategy": fam_l, "selected on": sel_l, "profile": PROF_SHORT[prof], "capital $M": f"{r['capital_$M']:.0f}", "gross SR": _f(r["gross_SR"]), "net SR": _f(r["net_SR"]),
                                 "net ret/yr": _pct(r["net_ann"]), "impact bp/day": _f(r["impact_bp"], 3), "total cost bp/day": _f(r["total_bp"], 3), "capacity by the ≥90%-of-peak rule": caps[(key, prof)]})
        cap_txt = "; ".join(f"{label(k)[0]} ({'pre-reg' if k.endswith('prereg_2013') else '2005'}, {PROF_SHORT[p]}): {v}" for (k, p), v in caps.items())
        P(f"Capacity: net Sharpe on the development window as a function of capital. Fees are flat per unit of capital; impact grows with participation in closing-auction volume to the 0.6 power, so net Sharpe falls with size. The pre-specified rule keeps the largest size with at least 90% of the peak net Sharpe: {cap_txt}. Gross Sharpe is not exactly constant across sizes because impact enters the net return that drives the drawdown brake, which rescales the book. Caveat: participation caps are charged as cost but not enforced as a size constraint, so the curve is a cost-model extrapolation.")
        T(pd.DataFrame(rows))
        for key, fr in fams.items():
            fam_l, sel_l = label(key)
            for prof, pr in fr["profiles"].items():
                kt = pd.DataFrame(pr["kill_tests"])
                if kt.empty:
                    continue
                out = pd.DataFrame({"variant": kt["variant"],
                                    "net SR": [(_f(v) if not _isnan(v) else "no trades") for v in kt["net_sr"]],
                                    "net ret/yr": [_pct(v) for v in kt["net_ann"]], "max DD": [_pct(v) for v in kt["max_dd"]],
                                    "gross SR": [(_f(v) if not _isnan(v) else "no trades") for v in kt["gross_sr"]],
                                    "turnover/day": [_f(v) for v in kt["turnover"]], "cost bp/day": [_f(v, 3) for v in kt["cost_bp"]]})
                P(f"Kill tests — {fam_l} selected on {sel_l}, {PROF_LABEL[prof]}, development + validation ({fr['dev_window'][0]} → 2022-12-15):")
                T(out)

    # ------------------------------------------------------------------ 6. pre-audit, holdout
    H(2, "6. Pre-audit results and the locked holdout (for the record)")
    P("The pipeline as it stood on 2026-09-06 04:57 UTC selected its configurations on a 2005–2018 development window, validated once on 2019–2022, froze, and ran a single pre-declared batch of 30 backtests on 2023-01-03 → 2026-08-31. Those files are immutable and are reproduced here unchanged. The independent audit (section 7) later established that the development and validation figures overstate the edge; the holdout figures are unaffected in direction (the defects were neutral-to-negative in 2023–2026).")
    rows = []
    for fam, s in val_pre.items():
        hf = hold.get("families", {}).get(fam, {})
        hv = hf.get("variants", {})
        rows.append({"strategy": FAM_LABEL.get(fam, fam), "pre-audit DEV net SR (2005–18)": _f(sel_pre.get(fam, {}).get("dev", {}).get("net_sr")),
                     "pre-audit VAL net SR": _f(s["net"]["sharpe_ann"]), "VAL 95% CI": f"{s['net']['sharpe_ci95_ann'][0]:.2f} .. {s['net']['sharpe_ci95_ann'][1]:.2f}",
                     "HOLDOUT net SR (market maker)": _f(hf.get("holdout_net_sharpe")), "HOLDOUT gross SR": _f(hv.get("base", {}).get("gross_sharpe")),
                     "HOLDOUT net ret/yr": _pct(hf.get("holdout_net_ann")), "HOLDOUT net vol": _pct(hv.get("base", {}).get("net_vol")), "HOLDOUT max DD": _pct(hf.get("holdout_max_dd")),
                     "HOLDOUT net SR (fund)": _f(hv.get("profile_prime_brokered_fund", {}).get("net_sharpe")),
                     "HOLDOUT +5 bp slippage": _f(hv.get("slippage_+5bp", {}).get("net_sharpe")), "HOLDOUT costs ×2": _f(hv.get("costs_x2.0", {}).get("net_sharpe"))})
    T(pd.DataFrame(rows))
    if hold:
        m = hold.get("manifest", {})
        P(f"Holdout manifest: git {m.get('git')}, config hash {m.get('config_hash')}, data snapshot {m.get('data_snapshot_sha256')}, frozen {m.get('frozen_at_utc', '')[:19]} UTC, run {hold.get('run_at_utc', '')[:19]} UTC.", "muted")
    f = RES / "holdout" / "daily_HOLDOUT_rank_reversal.csv"
    if f.exists():
        parts.append(fig_equity(pd.read_csv(f, index_col=0, parse_dates=True), "Rank residual reversal: locked holdout 2023-01-03 → 2026-08-31, compounded (frozen pre-audit pipeline)", "pm_hold_rank"))

    # ------------------------------------------------------------------ 7. audit
    H(2, "7. Independent adversarial audit and what changed")
    P("A fresh-context reviewer with a hostile brief and read-only access examined the repository and the processed data (reports/RED_TEAM_AUDIT.md; 22 findings, 23 numeric checks). A second independent review then checked this report's every table cell against the result files (reports/REPORT_REVIEW.md; 1,788 comparisons, 30 findings, all addressed in this version). The findings that changed the numbers, and their repairs:")
    T(pd.DataFrame([
        {"finding": "Hedge not executed (critical)", "what was wrong": "The SPY hedge and net-exposure correction were gated by the limit-on-close fill rule, so the realized book carried ±20% of capital in unhedged market exposure whose sign flipped with the closing tape; ~53% of 2005–2022 gross P&L was net exposure × next-day market return.", "repair": "Hedge re-sized to the filled book and executed market-on-close; dollar-net clipped to ±5% after the fill decision. Realized net-exposure std now ≈ 0.04."},
        {"finding": "Development window (critical)", "what was wrong": "Pre-registered rule: start where ≥ 80% of the universe has intraday bars (2013-10-23). The grid ran from 2005; the chosen configuration had net SR 1.55 on 2005–2011 and −0.35 on 2012–2018.", "repair": "Selection rerun on the pre-registered window (primary) and on the 2005 window (comparison); era decomposition reported everywhere."},
        {"finding": "End-of-day information in the 15:45 mask (high)", "what was wrong": "The jump filter used the full-day residual of day t.", "repair": "Daily mask lagged one day plus an ex-ante partial-day jump rule; invariance test added."},
        {"finding": "Limit-on-close semantics (high)", "what was wrong": "Cancelled entries became unconditional MOC fills the next day (37% of cancellations); the limit was checked on the intraday bar, not the official close.", "repair": "Entries classified against held weights and re-submitted as LOC; condition evaluated on the official close."},
        {"finding": "Delisting rules, dividend basis (medium)", "what was wrong": "Delisting rules were never wired into research runs; pre-split dividends mis-scaled on split-adjusted intraday series.", "repair": "Both wired/fixed, with tests (bankruptcy 'Q' tickers → −100%, ticker changes → 0)."},
        {"finding": "Overclaims (high)", "what was wrong": "'Beta-neutral', 'leakage-free', 'delisting rules applied', 'validation confirmed development almost exactly'.", "repair": "Documents rewritten from the post-audit data; this report is the corrected statement."},
        {"finding": "Earnings-drift conditioning dropped (report review, blocker)", "what was wrong": "The volume/timing conditioning of the selected earnings-drift configurations was silently dropped when the selected configuration was re-instantiated, so the first data set described a different book.", "repair": "Parameter propagation fixed; all earnings-drift cells rerun; this version carries the corrected figures."},
    ]))
    P("Open items the sponsor should know: sector labels are not point-in-time (names mapped to XLC/XLRE are ineligible before those ETFs existed); the liquidity filter and participation caps in the configuration are not enforced in construction; share counts derive from adjusted prices (conservative on fees); the volatility target is computed on the targeted rather than the filled book; the survivorship gap of the price panel is 5.8% of members in 2013 falling to 1.2% in 2018 and 0% after 2020. On multiple testing: the pre-audit deflated Sharpe ratio of the rank family was 0.62 over 72 candidates and, in the auditor's recomputation, 0.51 at a pooled 140 and 0.38 at 300 effective trials; the post-audit deflated Sharpe ratios are given in section 4 for each selection.")
    if pa:
        rows = []
        for key, fr in pa.get("families", {}).items():
            fam_l, sel_l = label(key)
            vm, dm = fr.get("val_market_maker", {}), fr.get("diag_2023_2026_market_maker", {})
            mc = vm.get("market_component", {})
            share = mc.get("share") if abs(mc.get("cum_gross", 0) or 0) >= 0.01 else None
            rows.append({"strategy": fam_l, "selected on": sel_l, "DEV net SR": _f(fr["dev"]["net_sr"]), "DEV 2005–11": _f(fr["dev_era"].get("sr_2005_2011")), "DEV 2012–18": _f(fr["dev_era"].get("sr_2012_2018")),
                         "VAL net SR": _f(vm.get("net_sr")), "VAL ex-2020–21": _f(vm.get("era", {}).get("sr_ex_2020_2021")), "2023–26 net SR": _f(dm.get("net_sr")), "2023–26 ex-best day": _f(dm.get("era", {}).get("sr_ex_best_day")),
                         "VAL market-component share of gross P&L": (_f(share) if share is not None else "n/a (gross ≈ 0)")})
        P("Repaired pipeline on both development windows (exchange-member profile). The market-component share is Σ realized net exposure × next-day SPY return over cumulative gross P&L; it is shown as n/a where cumulative gross P&L is within ±1% of capital because the ratio is then meaningless.")
        T(pd.DataFrame(rows))

    # ------------------------------------------------------------------ 8. evidence and risks
    H(2, "8. What the evidence supports, and the risks of trading it anyway")
    P("<b>Mechanism (pre-audit diagnostics, to be read with the hedge caveat).</b> On the pre-audit daily-model diagnostics the no-news residual reversal was a day-one effect (6.8 bp per day on day one, 1.7 bp per day afterwards on the decile spread), it was absent for earnings-8-K movers (which continued at about −15 bp per day), and the pre-audit rank backtest's net Sharpe rose with lagged VIX (0.52 / 0.97 / 1.11 by tercile on 2005–2022). The decile-spread diagnostics do not depend on the fill rule; the VIX-tercile Sharpes come from a backtest the audit showed carried an unhedged market component. They are consistent with compensation for supplying liquidity in stressed markets, not with a steady-state anomaly, and they have not been recomputed on the repaired pipeline.")
    if pa:
        rows = []
        for key, fr in pa.get("families", {}).items():
            fam_l, sel_l = label(key)
            vm, dm = fr.get("val_market_maker", {}), fr.get("diag_2023_2026_market_maker", {})
            rows.append({"strategy": fam_l, "selected on": sel_l, "VAL net SR": _f(vm.get("net_sr")), "VAL ex-2020–21": _f(vm.get("era", {}).get("sr_ex_2020_2021")),
                         "VAL yearly SR": ", ".join(f"{k}: {v}" for k, v in vm.get("era", {}).get("yearly_sr", {}).items()),
                         "2023–26 net SR": _f(dm.get("net_sr")), "2023–26 yearly SR": ", ".join(f"{k}: {v}" for k, v in dm.get("era", {}).get("yearly_sr", {}).items())})
        ex = {k: fr.get("val_market_maker", {}).get("era", {}).get("sr_ex_2020_2021") for k, fr in pa.get("families", {}).items()}
        P("<b>Regime concentration.</b> Every configuration earns most of its historical profit in 2008 and 2020–2021 where those years are in its sample. Excluding 2020–2021 from the validation window leaves the pre-registered rank selection at " + _f(ex.get("rank_reversal@prereg_2013")) + ", the pre-registered event selection at " + _f(ex.get("event_reversal@prereg_2013")) + ", and the 2005-window rank and event selections at " + _f(ex.get("rank_reversal@full_2005")) + " and " + _f(ex.get("event_reversal@full_2005")) + ". Per cell:")
        T(pd.DataFrame(rows))
    if fams:
        turn = [pr[w]["turnover_per_day"] for fr in fams.values() for pr in fr["profiles"].values() for w in ("dev", "val", "diag_2023_2026")]
        rk = [(pr[w]["turnover_per_day"] / pr[w]["avg_gross_exposure"]) for k, fr in fams.items() if k.startswith("rank") for pr in fr["profiles"].values() for w in ("dev", "val", "diag_2023_2026") if pr[w]["avg_gross_exposure"] > 1e-6]
        P(f"<b>Execution dependence.</b> The edge is a few basis points per day. Turnover is {min(turn):.2f}–{max(turn):.2f} of capital per day, which is {min(rk):.1f}–{max(rk):.1f}× the realized book per day for the rank strategies. Five basis points of slippage per side turns every cell negative (kill-test rows 'slippage_+5bp' in section 5); only auction fills that pay no spread keep it near zero. Capacity by the pre-specified rule is listed per cell in section 5.")
        P(f"<b>Leverage.</b> The policy is a 10% volatility target with gross ≤ 3× and a drawdown brake. Because the limit-on-close filter fills only about a fifth of entries and the event books are episodic, the realized books run at {min(g_all):.2f}×–{max(g_all):.2f}× gross and {min(pr[w]['net']['ann_vol'] for fr in fams.values() for pr in fr['profiles'].values() for w in ('dev','val','diag_2023_2026'))*100:.1f}–{max(pr[w]['net']['ann_vol'] for fr in fams.values() for pr in fr['profiles'].values() for w in ('dev','val','diag_2023_2026'))*100:.1f}% volatility, so the unlevered return per 1× gross is several times the as-run return. Scaling to 10% volatility would require {min(g10):.1f}×–{max(g10):.1f}× gross depending on the cell, inside the 3× cap; the binding constraint on size is closing-auction participation (section 5), not the gross cap. The 'at 10% vol' column assumes linear cost scaling and no capacity constraint and is therefore an upper bound.")
        rows = []
        for key, fr in fams.items():
            fam_l, sel_l = label(key)
            for w in ("val", "diag_2023_2026"):
                d = fr["profiles"]["market_maker"][w]
                a = act.get((key, "market_maker", w), {})
                rows.append({"strategy": fam_l, "selected on": sel_l, "window": WIN_SHORT[w], "net SR": _f(d["net"]["sharpe_ann"]), "SR ex-best day": _f(a.get("sr_ex_best_day")),
                             "skew": _f(d["net"].get("skew")), "kurtosis": _f(d["net"].get("kurtosis"), 1), "worst day": f"{d['worst_day'][0]} {d['worst_day'][1]*100:+.2f}%", "best day": f"{d['best_day'][0]} {d['best_day'][1]*100:+.2f}%",
                             "max DD": _pct(d["max_drawdown"]), "longest DD": f"{d['longest_drawdown_days']} d"})
        ku = [fr["profiles"]["market_maker"]["diag_2023_2026"]["net"]["kurtosis"] for fr in fams.values()]
        rk05 = fams.get("rank_reversal@full_2005", {}).get("profiles", {}).get("market_maker", {}).get("diag_2023_2026", {})
        a05 = act.get(("rank_reversal@full_2005", "market_maker", "diag_2023_2026"), {})
        ev05 = act.get(("event_reversal@full_2005", "market_maker", "diag_2023_2026"), {})
        P(f"<b>Tail behaviour (market-maker profile).</b> Daily net returns are fat-tailed in every cell (excess kurtosis {min(ku):.0f}–{max(ku):.0f} on 2023–2026), and in the rank books single days carry much of the cumulative return: the 2005-window rank selection falls from {_f(rk05.get('net', {}).get('sharpe_ann'))} to {_f(a05.get('sr_ex_best_day'))} on 2023–2026 without its best day, and the frozen holdout from 0.16 to 0.01. The event configuration selected on the 2005 window is less concentrated ({_f(fams.get('event_reversal@full_2005', {}).get('profiles', {}).get('market_maker', {}).get('diag_2023_2026', {}).get('net', {}).get('sharpe_ann'))} → {_f(ev05.get('sr_ex_best_day'))}). Drawdowns are shallow because realized volatility is low, not because the strategies are safe at target volatility.")
        T(pd.DataFrame(rows))

    # ------------------------------------------------------------------ 9. recommendation
    H(2, "9. Recommendation and next steps")
    P("<b>Do not allocate</b> to any of the three strategies in their current form. Two candidates deserve a pre-registered forward paper test from 2026-09 with the repaired code, the live news layer (EDGAR real-time feed, FMP articles, web search for same-day cause-of-move), exchange-member execution, size at or below the capacity rule, and a kill rule (trailing 12-month net Sharpe below zero): (a) the event-reversal configuration |z| ≥ 2 / hold 3 / limit-on-close, whose 2023–2026 diagnostic result is the only economically interesting cell but is not out-of-sample; (b) a rank reversal traded only when lagged VIX is in its top tercile, which is an untested hypothesis motivated by the pre-audit VIX-tercile diagnostics and must be registered as such. The 2023–2026 window is spent and cannot serve as a holdout again. Before any capital: point-in-time sector history, enforced participation caps, permanent-id keying of membership, volatility targeting on the filled book, and a further adversarial review of the forward-test design.")
    H(2, "Appendix: reproducibility and controls")
    T(pd.DataFrame([
        {"control": "Pre-registration", "detail": "Hypotheses H1–H8 and the fallback registered before any data pull; 140 grid configurations plus every diagnostic in 04_HYPOTHESIS_REGISTRY.csv; nothing deleted."},
        {"control": "Point-in-time", "detail": "Membership effective the day after the change; betas, volatilities, VIX, expected earnings, drawdown state lagged; 8-K flags by acceptance timestamp with a 15:40 cutoff; article flags by ET publication time."},
        {"control": "Leakage tests", "detail": "Perfect-foresight signal earns nothing under the engine's lag; past outputs invariant to future prices; after-hours filing flags the next day; 15:45 eligibility invariant to the close (added post-audit). 48 unit tests."},
        {"control": "Multiple testing", "detail": "Deflated Sharpe ratio, CSCV probability of backtest overfitting, stationary block-bootstrap confidence intervals, one-shot validation, single locked holdout."},
        {"control": "Independent review", "detail": "Fresh-context adversarial audit of the code with its own verification scripts (all critical and high code findings repaired, pipeline rerun); fresh-context review of this report against the result files (all 30 findings addressed)."},
        {"control": "Engineering", "detail": "Python 3.14 research package with YAML configs and per-run manifests (git hash, config hash, data-snapshot hash); C++ simulation engine with a file-based parity harness and benchmark (cpp/benchmark.md: 1e-9 parity, 6.7× faster than the Python engine)."},
    ]))
    parts.append("<p class='muted'>All statistics are computed from the daily net return series of recorded runs; Sharpe ratios are annualised from daily figures (√252); annual returns are geometric annualisations of the uncompounded daily path, and yearly returns are sums of daily returns. Source files: results/post_audit/full_metrics.json, results/post_audit/daily_full_*.csv, results/post_audit/post_audit_results.json, results/holdout/holdout_results.json, reports/RED_TEAM_AUDIT.md, reports/REPORT_REVIEW.md.</p>")

    body = "".join(parts)
    css = """
:root{--ground:#f3f5f8;--surface:#ffffff;--ink:#17202b;--ink-2:#5a6676;--rule:#d5dbe4;--accent:#0f6e6b;--accent-soft:#e3f0ef;--neg:#b3403a;--code:#eaeef3}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--ground:#101418;--surface:#171c22;--ink:#e4e8ed;--ink-2:#98a3b1;--rule:#2a323c;--accent:#5fc2bd;--accent-soft:#16302f;--neg:#e2766f;--code:#1e252d}}
:root[data-theme="dark"]{--ground:#101418;--surface:#171c22;--ink:#e4e8ed;--ink-2:#98a3b1;--rule:#2a323c;--accent:#5fc2bd;--accent-soft:#16302f;--neg:#e2766f;--code:#1e252d}
body{background:var(--ground);color:var(--ink);font-family:"IBM Plex Sans",Segoe UI,Helvetica,Arial,sans-serif;font-size:15px;line-height:1.55;margin:0}
.wrap{max-width:980px;margin:0 auto;padding:36px 22px 64px}
.eyebrow{font-family:"IBM Plex Mono",Consolas,monospace;font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--ink-2)}
h1{font-family:"Source Serif 4",Georgia,serif;font-size:34px;line-height:1.15;margin:8px 0 10px;text-wrap:balance}
h2{font-family:"Source Serif 4",Georgia,serif;font-size:22px;margin:40px 0 10px;padding-top:14px;border-top:1px solid var(--rule);color:var(--accent);text-wrap:balance}
h3{font-size:16px;margin:26px 0 8px;font-weight:600}
p{max-width:72ch;margin:8px 0}p.lede{font-size:17px;color:var(--ink-2);max-width:78ch}p.muted{color:var(--ink-2);font-size:13.5px}
code{font-family:"IBM Plex Mono",Consolas,monospace;font-size:12.5px;background:var(--code);padding:1px 5px;border-radius:3px}
.tbl-wrap{overflow-x:auto;background:var(--surface);border:1px solid var(--rule);border-radius:6px;margin:12px 0}
.tbl{border-collapse:collapse;font-size:12.5px;width:100%;font-variant-numeric:tabular-nums}
.tbl th{background:var(--accent-soft);text-align:left;padding:7px 9px;font-weight:600;white-space:nowrap;position:sticky;top:0}
.tbl td{padding:5px 9px;border-top:1px solid var(--rule);vertical-align:top;white-space:nowrap}
img{max-width:100%;display:block;margin:12px 0;border-radius:4px}
@media (prefers-reduced-motion: reduce){*{animation:none!important;transition:none!important}}
"""
    fonts = '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Source+Serif+4:wght@600;700&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">'
    REP.mkdir(exist_ok=True)
    standalone = f"<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Residual Reversal Due-Diligence Report</title>{fonts}<style>{css}</style></head><body><div class='wrap'>{body}</div></body></html>"
    (REP / "PM_REPORT.html").write_text(standalone, encoding="utf-8")
    art = f"<title>Residual Reversal Due Diligence</title>{fonts}<style>{css}</style><div class='wrap'>{body}</div>"
    (REP / "pm_artifact.html").write_text(art, encoding="utf-8")
    return REP / "PM_REPORT.html"


if __name__ == "__main__":
    print(build_pm_report())
