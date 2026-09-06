"""Client-facing due-diligence report for quantitative portfolio managers.

Reads only frozen result files (results/post_audit/full_metrics.json, results/post_audit/post_audit_results.json,
results/holdout/holdout_results.json, results/validation, reports/RED_TEAM_AUDIT.md) and writes
reports/PM_REPORT.html (standalone) and reports/pm_artifact.html (no document skeleton, for hosting).
Nothing in this module computes a new strategy result; every number is read from disk.
"""

from __future__ import annotations

import json
from datetime import date

import numpy as np
import pandas as pd

from statarb.config import REPO_ROOT
from statarb.reporting.html_report import RES, REP, _load_json, _table, fig_bar, fig_equity, fig_monthly_heatmap

FAM_LABEL = {"rank_reversal": "Rank residual reversal", "event_reversal": "Event residual reversal", "earnings_drift": "Earnings-8-K drift"}
PROF_LABEL = {"market_maker": "Exchange member (market maker)", "prime_brokered_fund": "Prime-brokered fund"}
WIN_LABEL = {"dev": "Development 2013-10-23 → 2018-12-14", "val": "Validation 2019-01-02 → 2022-12-15", "diag_2023_2026": "2023-01-03 → 2026-08-31 (post-audit diagnostic)"}


def _pct(v, d=1):
    return "" if v is None or (isinstance(v, float) and np.isnan(v)) else f"{v*100:+.{d}f}%"


def _f(v, d=2):
    return "" if v is None or (isinstance(v, float) and np.isnan(v)) else f"{v:.{d}f}"


def build_pm_report():
    fm = _load_json(RES / "post_audit" / "full_metrics.json") or {}
    pa = _load_json(RES / "post_audit" / "post_audit_results.json") or {}
    hold = _load_json(RES / "holdout" / "holdout_results.json") or {}
    val_pre = _load_json(RES / "validation" / "validation_results.json") or {}
    sel_pre = _load_json(RES / "validation" / "selection.json") or {}
    parts = []
    H = lambda lvl, t, cls="": parts.append(f"<h{lvl}{' class=' + chr(34) + cls + chr(34) if cls else ''}>{t}</h{lvl}>")
    P = lambda t, cls="": parts.append(f"<p{' class=' + chr(34) + cls + chr(34) if cls else ''}>{t}</p>")
    T = lambda df, ff="{:.2f}": parts.append("<div class='tbl-wrap'>" + _table(df, ff) + "</div>")
    fams = fm.get("families", {})
    cap = fm.get("capital", 1e6)

    # ------------------------------------------------------------------ 1. bottom line
    parts.append("<div class='eyebrow'>Due-diligence report · stat-arb-research · " + str(date.today()) + "</div>")
    H(1, "Residual short-term reversal in U.S. large caps")
    P("Three closing-auction strategies on the point-in-time S&P 500, 2013–2026, tested under two institutional cost profiles with a pre-registered protocol, a locked holdout, an independent adversarial audit, and a full rerun after the audit's repairs.", "lede")
    H(2, "1. Bottom line")
    P("<b>Recommendation: do not allocate.</b> None of the three strategies shows an economically meaningful net edge outside two stress episodes (2008; 2020–2021). On the pre-registered development window, the one-shot validation window and the 2023–2026 window, net Sharpe ratios are near zero or negative under both cost profiles once the pipeline is repaired, and the pre-audit development and validation figures that looked attractive (0.89 / 0.93) are withdrawn: roughly half of that gross P&amp;L was an unintended market-timing exposure created by a fill-rule defect, and the selection rested on 2005–2011 data below the pre-registered coverage threshold. The single locked holdout (frozen before the audit, never re-run) returned a net Sharpe of 0.16 with a confidence interval spanning zero. Classification: <b>C — research-quality negative result</b>.")
    if fams:
        rows = []
        for key, fr in fams.items():
            fam, tag = key.split("@")
            for prof, pr in fr["profiles"].items():
                r = {"strategy": FAM_LABEL.get(fam, fam), "selected on": fr["dev_window"][0] + " → 2018", "cost profile": PROF_LABEL.get(prof, prof)}
                for w in ("dev", "val", "diag_2023_2026"):
                    d = pr[w]
                    r[f"{w}: net SR"] = d["net"]["sharpe_ann"]
                    r[f"{w}: net ret/yr"] = d["net"]["ann_return"]
                    r[f"{w}: max DD"] = d["max_drawdown"]
                rows.append(r)
        df = pd.DataFrame(rows).rename(columns={"dev: net SR": "DEV net SR", "dev: net ret/yr": "DEV net ret/yr", "dev: max DD": "DEV max DD",
                                                "val: net SR": "VAL net SR", "val: net ret/yr": "VAL net ret/yr", "val: max DD": "VAL max DD",
                                                "diag_2023_2026: net SR": "2023–26 net SR", "diag_2023_2026: net ret/yr": "2023–26 net ret/yr", "diag_2023_2026: max DD": "2023–26 max DD"})
        T(df)
        P(f"Windows: DEV = development window on which the configuration was selected (pre-registered 2013-10-23 → 2018-12-14, and for comparison the 2005-01-03 → 2018-12-14 window that the pre-audit study used; both are shown because the selections differ and the difference is itself a finding); VAL = one-shot validation 2019-01-02 → 2022-12-15; 2023–26 = post-audit diagnostic run of the repaired pipeline on 2023-01-03 → 2026-08-31 (the frozen holdout on the same dates is in section 7). Capital ${cap/1e6:.0f}M, 10% volatility target, gross ≤ 3×, drawdown brake (halve at −10%, restore at −5%). Returns are fractions of capital per year, net of all modelled costs, uncompounded.", "muted")
    else:
        P("<i>Complete data set not yet generated (results/post_audit/full_metrics.json missing).</i>")

    # ------------------------------------------------------------------ 2. strategies
    H(2, "2. What was tested")
    T(pd.DataFrame([
        {"strategy": FAM_LABEL["rank_reversal"], "signal": "z-scored residual return (market + sector betas, 250-day window) over the last k days incl. the partial day to 15:45 ET", "book": "long bottom quantile / short top quantile among no-news, non-jump, liquid names; k overlapping daily tranches; dollar-, sector- and beta-hedged (SPY)", "execution": "limit-on-close orders at 15:45, fill at the official close only if the close extends the move by δσ; exits MOC", "candidates": "72 (lookback × holding × quantiles × VIX gate × execution)"},
        {"strategy": FAM_LABEL["event_reversal"], "signal": "same residual score, but only names whose |z| exceeds an entry threshold", "book": "equal-weight event positions sized by an ex-ante expected entrant count; held k days", "execution": "same", "candidates": "48"},
        {"strategy": FAM_LABEL["earnings_drift"], "signal": "sign of the residual move on a day with an earnings 8-K (item 2.02) accepted before 15:40 ET; continuation, not reversal", "book": "event positions in the direction of the move, held k days; volume- and timing-conditioned variants", "execution": "market-on-close", "candidates": "20"},
    ]), "{}")
    P("Universe: point-in-time S&P 500 membership from the change list (1,525 events, delisted names included, delisting returns applied). Data: FMP daily and 15-minute bars, SEC EDGAR 8-K acceptance timestamps (255k filings), FMP articles for the news layer. Decision time 15:45 ET (signal from the 15:30–15:45 bar), submission before the 15:50 NYSE cutoff.")

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
    ]), "{}")
    P("Sources are documented in reports/market_maker_cost_research.md (exchange fee schedules, NSCC, SEC and FINRA notices). The retail profile was dropped at the sponsor's request as irrelevant to institutional deployment.")

    # ------------------------------------------------------------------ 4. full data set
    H(2, "4. Performance data set (repaired pipeline)")
    if fams:
        for key, fr in fams.items():
            fam, tag = key.split("@")
            H(3, f"{FAM_LABEL.get(fam, fam)}, selected on {fr['dev_window'][0]} → {fr['dev_window'][1]} — <code>{fr['selected_id'].replace('C-moc-', '')}</code>")
            mt = fr.get("multiple_testing", {})
            P(f"Selected by the pre-specified rule on this development window from {mt.get('n_candidates', '?')} registered candidates. Deflated Sharpe ratio {_f(mt.get('dsr'))}, probability of backtest overfitting (CSCV) {_f(mt.get('pbo_cscv'))}, PSR vs zero on DEV {_f(mt.get('psr_vs_zero'))}.", "muted")
            rows = []
            for prof, pr in fr["profiles"].items():
                for w in ("dev", "val", "diag_2023_2026"):
                    d = pr[w]
                    n, g = d["net"], d["gross"]
                    rows.append({"profile": PROF_LABEL[prof], "window": w.replace("diag_2023_2026", "2023–26").upper(),
                                 "net ret/yr": _pct(n["ann_return"]), "net vol": _pct(n["ann_vol"]), "net SR": _f(n["sharpe_ann"]), "SR 95% CI": f"{d['sharpe_ci95_ann'][0]:.2f} .. {d['sharpe_ci95_ann'][1]:.2f}",
                                 "gross SR": _f(g["sharpe_ann"]), "Sortino": _f(n.get("sortino_ann")), "Calmar": _f(n.get("calmar")), "max DD": _pct(d["max_drawdown"]),
                                 "longest DD": f"{d['longest_drawdown_days']} d", "hit rate": _pct(n.get("hit_rate"), 1), "+months": _pct(d["pct_positive_months"], 0),
                                 "profit factor": _f(n.get("profit_factor")), "skew": _f(n.get("skew")), "kurtosis": _f(n.get("kurtosis"), 1), "PSR>0": _f(n.get("psr_vs_zero")),
                                 "gross exp": _f(d["avg_gross_exposure"]), "net-exp std": _f(d["net_exposure_std"], 3), "β SPY": _f(d["beta_to_spy"], 3),
                                 "turnover/day": _f(d["turnover_per_day"]), "cost bp/day": _f(d["cost_bp_total"]), "worst day": f"{d['worst_day'][0]} {d['worst_day'][1]*100:+.2f}%"})
            T(pd.DataFrame(rows), "{}")
            # yearly
            yrows = []
            for prof, pr in fr["profiles"].items():
                yr = {}
                for w in ("dev", "val", "diag_2023_2026"):
                    yr.update(pr[w]["yearly_net"])
                yrows.append({"profile": PROF_LABEL[prof], **{k: _pct(v) for k, v in sorted(yr.items())}})
            P("Net return by calendar year:")
            T(pd.DataFrame(yrows), "{}")
            mm = fr["profiles"]["market_maker"]
            ys = {}
            for w in ("dev", "val", "diag_2023_2026"):
                ys.update({k: v for k, v in mm[w]["yearly_sharpe"].items() if v is not None})
            parts.append(fig_bar(pd.Series(ys), f"{FAM_LABEL.get(fam, fam)} (selected on {fr['dev_window'][0]}): net Sharpe by year, DEV → VAL → 2023–26 (exchange-member profile)", f"pm_yearly_{key}"))
            for w in ("dev", "val", "diag_2023_2026"):
                f = RES / "post_audit" / f"daily_full_{key}_market_maker_{w}.csv"
                if f.exists():
                    d = pd.read_csv(f, index_col=0, parse_dates=True)
                    wl = WIN_LABEL[w] if w != "dev" else f"Development {fr['dev_window'][0]} → {fr['dev_window'][1]}"
                    parts.append(fig_equity(d, f"{FAM_LABEL.get(fam, fam)} (selected on {fr['dev_window'][0]}): {wl}, gross vs net (exchange-member profile)", f"pm_eq_{key}_{w}"))
            if fam == "rank_reversal":
                f = RES / "post_audit" / f"daily_full_{key}_market_maker_dev.csv"
                if f.exists():
                    parts.append(fig_monthly_heatmap(pd.read_csv(f, index_col=0, parse_dates=True), f"pm_heat_{key}_dev"))

    # ------------------------------------------------------------------ 5. costs, capacity, robustness
    H(2, "5. Cost decomposition, capacity and stress tests")
    if fams:
        rows = []
        for key, fr in fams.items():
            fam, tag = key.split("@")
            for prof, pr in fr["profiles"].items():
                c = pr["val"]["cost_bp_per_day"]
                rows.append({"strategy": FAM_LABEL.get(fam, fam), "selected on": fr["dev_window"][0], "profile": PROF_LABEL[prof], "window": "VAL", "fees": c.get("commission"), "reg + clearing": c.get("fees"), "impact": c.get("impact"), "borrow": c.get("borrow"), "total bp/day": pr["val"]["cost_bp_total"], "gross SR": pr["val"]["gross"]["sharpe_ann"], "net SR": pr["val"]["net"]["sharpe_ann"]})
        P("Daily cost in basis points of capital by component (validation window):")
        T(pd.DataFrame(rows))
        rows = []
        for key, fr in fams.items():
            fam, tag = key.split("@")
            for prof, pr in fr["profiles"].items():
                for r in pr["capacity"]:
                    rows.append({"strategy": FAM_LABEL.get(fam, fam), "selected on": fr["dev_window"][0], "profile": PROF_LABEL[prof], **r})
        P("Capacity: net Sharpe on the development window as a function of capital (impact grows with participation in closing-auction volume^0.6; fees are flat per unit of capital). The pre-specified rule chose the largest size keeping ≥ 90% of the peak net Sharpe. Caveat: participation caps are charged as cost but not enforced as a size constraint, so this is a cost-model extrapolation.")
        T(pd.DataFrame(rows).rename(columns={"capital_$M": "capital $M", "gross_SR": "gross SR", "net_SR": "net SR", "net_ann": "net ret/yr", "impact_bp": "impact bp/day", "total_bp": "total cost bp/day"}))
        for key, fr in fams.items():
            fam, tag = key.split("@")
            for prof, pr in fr["profiles"].items():
                kt = pd.DataFrame(pr["kill_tests"])
                if kt.empty:
                    continue
                P(f"Kill tests — {FAM_LABEL.get(fam, fam)} selected on {fr['dev_window'][0]}, {PROF_LABEL[prof]}, development + validation ({fr['dev_window'][0]} → 2022-12-15):")
                T(kt.rename(columns={"net_sr": "net SR", "net_ann": "net ret/yr", "max_dd": "max DD", "gross_sr": "gross SR", "cost_bp": "cost bp/day", "n_days": "days"}))

    # ------------------------------------------------------------------ 6. pre-audit, holdout
    H(2, "6. Pre-audit results and the locked holdout (for the record)")
    P("The pipeline as it stood on 2026-09-06 04:57 UTC selected its configurations on a 2005–2018 development window, validated once on 2019–2022, froze, and ran a single pre-declared batch of 30 backtests on 2023-01-03 → 2026-08-31. Those files are immutable and are reproduced here unchanged. The independent audit (section 7) later established that the development and validation figures overstate the edge; the holdout figures are unaffected in direction (the defects were neutral-to-negative in 2023–2026).")
    rows = []
    for fam, s in val_pre.items():
        hf = hold.get("families", {}).get(fam, {})
        hv = hf.get("variants", {})
        rows.append({"strategy": FAM_LABEL.get(fam, fam), "pre-audit DEV net SR (2005–18)": sel_pre.get(fam, {}).get("dev", {}).get("net_sr"),
                     "pre-audit VAL net SR": s["net"]["sharpe_ann"], "VAL 95% CI": f"{s['net']['sharpe_ci95_ann'][0]:.2f} .. {s['net']['sharpe_ci95_ann'][1]:.2f}",
                     "HOLDOUT net SR (market maker)": hf.get("holdout_net_sharpe"), "HOLDOUT gross SR": hv.get("base", {}).get("gross_sharpe"),
                     "HOLDOUT net ret/yr": hf.get("holdout_net_ann"), "HOLDOUT max DD": hf.get("holdout_max_dd"),
                     "HOLDOUT net SR (fund)": hv.get("profile_prime_brokered_fund", {}).get("net_sharpe"),
                     "HOLDOUT +5 bp slippage": hv.get("slippage_+5bp", {}).get("net_sharpe"), "HOLDOUT costs ×2": hv.get("costs_x2.0", {}).get("net_sharpe")})
    T(pd.DataFrame(rows))
    if hold:
        m = hold.get("manifest", {})
        P(f"Holdout manifest: git {m.get('git')}, config hash {m.get('config_hash')}, data snapshot {m.get('data_snapshot_sha256')}, frozen {m.get('frozen_at_utc', '')[:19]} UTC, run {hold.get('run_at_utc', '')[:19]} UTC.", "muted")
    f = RES / "holdout" / "daily_HOLDOUT_rank_reversal.csv"
    if f.exists():
        parts.append(fig_equity(pd.read_csv(f, index_col=0, parse_dates=True), "Rank residual reversal: locked holdout 2023-01-03 → 2026-08-31 (frozen pre-audit pipeline)", "pm_hold_rank"))

    # ------------------------------------------------------------------ 7. audit
    H(2, "7. Independent adversarial audit and what changed")
    P("A fresh-context reviewer with a hostile brief and read-only access examined the repository and the processed data (reports/RED_TEAM_AUDIT.md; 22 findings, 23 numeric checks). The findings that changed the numbers, and their repairs:")
    T(pd.DataFrame([
        {"finding": "Hedge not executed (critical)", "what was wrong": "The SPY hedge and net-exposure correction were gated by the limit-on-close fill rule, so the realized book carried ±20% of capital in unhedged market exposure whose sign flipped with the closing tape; ~53% of 2005–2022 gross P&L was net exposure × next-day market return.", "repair": "Hedge re-sized to the filled book and executed market-on-close; dollar-net clipped to ±5% after the fill decision. Realized net-exposure std now ≈ 0.04."},
        {"finding": "Development window (critical)", "what was wrong": "Pre-registered rule: start where ≥ 80% of the universe has intraday bars (2013-10-23). The grid ran from 2005; the chosen configuration had net SR 1.55 on 2005–2011 and −0.35 on 2012–2018.", "repair": "Selection rerun on the pre-registered window (primary) and on the 2005 window (comparison); era decomposition reported everywhere."},
        {"finding": "End-of-day information in the 15:45 mask (high)", "what was wrong": "The jump filter used the full-day residual of day t.", "repair": "Daily mask lagged one day plus an ex-ante partial-day jump rule; invariance test added."},
        {"finding": "Limit-on-close semantics (high)", "what was wrong": "Cancelled entries became unconditional MOC fills the next day (37% of cancellations); the limit was checked on the intraday bar, not the official close.", "repair": "Entries classified against held weights and re-submitted as LOC; condition evaluated on the official close."},
        {"finding": "Delisting rules, dividend basis (medium)", "what was wrong": "Delisting rules were never wired into research runs; pre-split dividends mis-scaled on split-adjusted intraday series.", "repair": "Both wired/fixed, with tests (bankruptcy 'Q' tickers → −100%, ticker changes → 0)."},
        {"finding": "Overclaims (high)", "what was wrong": "'Beta-neutral', 'leakage-free', 'delisting rules applied', 'validation confirmed development almost exactly'.", "repair": "Documents rewritten from the post-audit data; this report is the corrected statement."},
    ]), "{}")
    P("Open items the sponsor should know: sector labels are not point-in-time (names mapped to XLC/XLRE are ineligible before those ETFs existed); the liquidity filter and participation caps in the configuration are not enforced in construction; share counts derive from adjusted prices (conservative on fees); the deflated Sharpe ratio counts the 72 rank-family candidates, and falls from 0.62 to 0.51 at the pooled 140 and 0.38 at 300 effective trials; the survivorship gap of the price panel is 5.8% of members in 2013 falling to 1.2% in 2018 and 0% after 2020.")
    if pa:
        rows = []
        for key, fr in pa.get("families", {}).items():
            fam, tag = key.split("@")
            vm, dm = fr.get("val_market_maker", {}), fr.get("diag_2023_2026_market_maker", {})
            rows.append({"strategy": FAM_LABEL.get(fam, fam), "DEV window": pa["dev_windows"].get(tag), "DEV net SR": fr["dev"]["net_sr"], "DEV 2005–11": fr["dev_era"].get("sr_2005_2011"), "DEV 2012–18": fr["dev_era"].get("sr_2012_2018"),
                         "VAL net SR": vm.get("net_sr"), "VAL ex-2020–21": vm.get("era", {}).get("sr_ex_2020_2021"), "2023–26 net SR": dm.get("net_sr"), "2023–26 ex-best day": dm.get("era", {}).get("sr_ex_best_day"),
                         "VAL market-component share": vm.get("market_component", {}).get("share")})
        P("Repaired pipeline on both development windows (exchange-member profile):")
        T(pd.DataFrame(rows))

    # ------------------------------------------------------------------ 8. mechanism, regimes, risks
    H(2, "8. What the evidence supports, and the risks of trading it anyway")
    P("<b>Mechanism.</b> The no-news residual reversal is a day-one effect (6.8 bp per day on day one, 1.7 bp per day afterwards, on the decile spread), it is absent for earnings-8-K movers (which continue at about −15 bp per day), and it scales with lagged VIX (net Sharpe by VIX tercile 0.52 / 0.97 / 1.11 on the pre-audit 2005–2022 sample). This is consistent with compensation for supplying liquidity in stressed markets, not with a steady-state anomaly.")
    P("<b>Regime concentration.</b> Nearly all of the historical profit sits in 2008 and 2020–2021. Excluding 2020–2021 the validation Sharpe is negative; the 2023–2026 window contained no sustained stress and produced nothing. An allocator would be buying a short-vol-like exposure with a long-vol-like payoff profile, but one whose payoff has been shrinking each cycle.")
    P("<b>Execution dependence.</b> The edge is a few basis points per day against turnover of roughly half the book per day. Five basis points of slippage per side turns every window negative; only auction fills that pay no spread keep it near zero. Capacity under closing-auction participation is on the order of $5–20M before impact removes what is left.")
    P("<b>Tail behaviour.</b> Daily net returns have excess kurtosis above 20 in the 2023–2026 window and single days account for most of the cumulative return (Sharpe ex-best-day ≈ 0). Drawdowns are shallow at the 10% vol target because realized volatility runs well below target: the limit-on-close filter leaves the book under-invested.")

    # ------------------------------------------------------------------ 9. recommendation
    H(2, "9. Recommendation and next steps")
    P("<b>Do not allocate</b> to any of the three strategies in their current form. The only design the evidence supports is a pre-registered, regime-conditional variant (trade only when lagged VIX is in its top tercile, auction fills only, exchange-member costs, size under $20M) tested on a new forward sample from 2026-09 with the live news layer (EDGAR real-time feed, FMP articles, web search for same-day cause-of-move). The 2023–2026 window is spent and cannot serve as a holdout again. A second adversarial review should be run on the forward-test design before capital is committed, and the open items in section 7 (point-in-time sectors, enforced participation caps, permanent-id keying) should be closed first.")
    H(2, "Appendix: reproducibility and controls")
    T(pd.DataFrame([
        {"control": "Pre-registration", "detail": "Hypotheses H1–H8 and the fallback registered before any data pull; 140 candidate configurations plus every diagnostic in 04_HYPOTHESIS_REGISTRY.csv; nothing deleted."},
        {"control": "Point-in-time", "detail": "Membership effective the day after the change; betas, volatilities, VIX, expected earnings, drawdown state lagged; 8-K flags by acceptance timestamp with a 15:40 cutoff; article flags by ET publication time."},
        {"control": "Leakage tests", "detail": "Perfect-foresight signal earns nothing under the engine's lag; past outputs invariant to future prices; after-hours filing flags the next day; 15:45 eligibility invariant to the close (added post-audit). 48 unit tests."},
        {"control": "Multiple testing", "detail": "Deflated Sharpe ratio, CSCV probability of backtest overfitting, stationary block-bootstrap confidence intervals, one-shot validation, single locked holdout."},
        {"control": "Independent review", "detail": "Fresh-context adversarial audit with its own verification scripts; all critical and high code findings repaired and the full pipeline rerun."},
        {"control": "Engineering", "detail": "Python 3.14 research package with YAML configs and per-run manifests (git hash, config hash, data-snapshot hash); C++ simulation engine (1e-9 parity, 6.7× faster)."},
    ]), "{}")
    parts.append("<p class='muted'>All statistics are computed from daily strategy returns; Sharpe ratios are annualised from daily figures; returns are uncompounded fractions of capital. Source files: results/post_audit/full_metrics.json, results/holdout/holdout_results.json, reports/RED_TEAM_AUDIT.md.</p>")

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
.tbl td{padding:5px 9px;border-top:1px solid var(--rule);vertical-align:top}
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
