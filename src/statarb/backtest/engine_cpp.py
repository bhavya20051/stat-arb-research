"""ctypes wrapper for the C++ engine (cpp/engine.cpp), with the same inputs/outputs as engine.run_backtest."""

from __future__ import annotations

import ctypes
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from statarb.backtest.engine import EngineInputs, _row
from statarb.config import REPO_ROOT
from statarb.execution.costs import CostParams

CPP_DIR = REPO_ROOT / "cpp"
LIB = CPP_DIR / "build" / ("engine.dll" if sys.platform == "win32" else "libengine.so")


class _Costs(ctypes.Structure):
    _fields_ = [("commission_per_share", ctypes.c_double), ("min_commission_per_order", ctypes.c_double), ("max_commission_pct", ctypes.c_double),
                ("sec_fee_rate", ctypes.c_double), ("finra_taf_per_share", ctypes.c_double), ("finra_taf_max", ctypes.c_double), ("clearing_pct_notional", ctypes.c_double),
                ("borrow_annual", ctypes.c_double), ("impact_k", ctypes.c_double), ("impact_exponent", ctypes.c_double), ("spread_multiplier", ctypes.c_double),
                ("extra_slippage_bp", ctypes.c_double), ("trading_days", ctypes.c_int), ("pay_spread", ctypes.c_int)]


def build(force: bool = False) -> Path:
    if LIB.exists() and not force:
        return LIB
    LIB.parent.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "-m", "ziglang", "c++", "-shared", "-O2", "-std=c++17", "-o", str(LIB), str(CPP_DIR / "engine.cpp")]
    subprocess.check_call(cmd)
    return LIB


_lib = None


def _load():
    global _lib
    if _lib is None:
        _lib = ctypes.CDLL(str(build()))
        D = ctypes.POINTER(ctypes.c_double)
        _lib.run_backtest_c.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int, D, D, D, D, D, D, D, ctypes.POINTER(ctypes.c_int), D,
                                        ctypes.c_double, ctypes.POINTER(_Costs)] + [D] * 9
        _lib.run_backtest_c.restype = ctypes.c_int
    return _lib


def _arr(df: pd.DataFrame | None, index, columns):
    if df is None:
        return None
    return np.ascontiguousarray(df.reindex(index=index, columns=columns).to_numpy(dtype=float))


def run_backtest_cpp(inp: EngineInputs, capital: float, costs: CostParams) -> pd.DataFrame:
    lib = _load()
    W = inp.target_weights.sort_index()
    dates, syms = W.index, list(W.columns)
    T, N = W.shape
    Wv = np.ascontiguousarray(W.to_numpy(dtype=float))
    Pv = _arr(inp.fill_price, dates, syms)
    Vv = _arr(inp.fill_volume, dates, syms)
    Mv = _arr(inp.mark_price, dates, syms)
    HS = _arr(inp.half_spread, dates, syms)
    SIG = _arr(inp.sigma_daily, dates, syms)
    ADV = _arr(inp.adv_shares, dates, syms)
    dpos = np.full(N, -1, dtype=np.int32)
    dret = np.zeros(N)
    for s, (d, r) in (inp.delist or {}).items():
        if s in syms:
            dpos[syms.index(s)] = int(dates.searchsorted(pd.Timestamp(d)))
            dret[syms.index(s)] = float(r)
    c = _Costs(costs.commission_per_share, costs.min_commission_per_order, costs.max_commission_pct, costs.sec_fee_rate,
               costs.finra_taf_per_share, costs.finra_taf_max, costs.clearing_pct_notional, costs.borrow_annual, costs.impact_k,
               costs.impact_exponent, costs.spread_multiplier, costs.extra_slippage_bp, costs.trading_days, int(costs.pay_spread))
    outs = [np.zeros(T) for _ in range(9)]
    D = ctypes.POINTER(ctypes.c_double)
    ptr = lambda a: a.ctypes.data_as(D) if a is not None else None
    lib.run_backtest_c(T, N, int(inp.lag), ptr(Wv), ptr(Pv), ptr(Vv), ptr(Mv), ptr(HS), ptr(SIG), ptr(ADV),
                       dpos.ctypes.data_as(ctypes.POINTER(ctypes.c_int)), ptr(dret), float(capital), ctypes.byref(c), *[ptr(o) for o in outs])
    gross, comm, fees, spread, imp, borrow, turn, ge, ne = outs
    # dates: rows are indexed by fill date where fills exist (fi < T), else by decision date (same as Python engine)
    idx = [dates[min(i + inp.lag, T - 1)] if i + inp.lag < T else dates[i] for i in range(T)]
    out = pd.DataFrame({"gross_ret": gross, "commission": comm, "fees": fees, "spread": spread, "impact": imp, "borrow": borrow,
                        "turnover": turn, "gross_exposure": ge, "net_exposure": ne}, index=pd.DatetimeIndex(idx, name="date"))
    out["net_ret"] = out["gross_ret"] - out[["commission", "fees", "spread", "impact", "borrow"]].sum(axis=1)
    return out
