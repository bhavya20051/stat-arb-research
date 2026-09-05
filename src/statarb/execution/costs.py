"""Transaction-cost model: commissions, regulatory fees on sells, spread, impact, borrow.

All functions are pure and vectorised over symbols for one trading day.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class CostParams:
    commission_per_share: float = 0.0035
    min_commission_per_order: float = 0.35
    max_commission_pct: float = 0.01
    sec_fee_rate: float = 0.0  # fraction of sell notional; set per year at M3
    finra_taf_per_share: float = 0.0
    finra_taf_max: float = 0.0
    borrow_annual: float = 0.005
    impact_k: float = 1.0
    spread_multiplier: float = 1.0
    extra_slippage_bp: float = 0.0
    trading_days: int = 252
    pay_spread: bool = True  # False for auction (MOC/MOO) fills
    extra: dict = field(default_factory=dict)


def commission(shares: np.ndarray, notional: np.ndarray, p: CostParams) -> np.ndarray:
    """Per-order commission for |shares| traded; zero for zero-size orders."""
    sh = np.abs(shares)
    c = sh * p.commission_per_share
    c = np.where(sh > 0, np.maximum(c, p.min_commission_per_order), 0.0)
    c = np.minimum(c, p.max_commission_pct * np.abs(notional))
    return c


def regulatory_fees(shares: np.ndarray, notional: np.ndarray, p: CostParams) -> np.ndarray:
    """SEC Section 31 fee and FINRA TAF apply to sells only (negative shares)."""
    sells = shares < 0
    sec = np.where(sells, p.sec_fee_rate * np.abs(notional), 0.0)
    taf = np.where(sells, np.minimum(np.abs(shares) * p.finra_taf_per_share, p.finra_taf_max), 0.0)
    return sec + taf


def spread_cost(notional: np.ndarray, half_spread: np.ndarray, p: CostParams) -> np.ndarray:
    """Half-spread paid per side on continuous-session fills; zero when pay_spread is False (auction fills)."""
    if not p.pay_spread:
        return np.zeros_like(notional, dtype=float)
    hs = np.nan_to_num(half_spread, nan=0.0) * p.spread_multiplier + p.extra_slippage_bp / 1e4
    return np.abs(notional) * hs


def impact_cost(notional: np.ndarray, participation: np.ndarray, sigma_daily: np.ndarray, p: CostParams) -> np.ndarray:
    """Square-root impact: k * sigma_daily * sqrt(participation) * |notional|."""
    part = np.nan_to_num(participation, nan=0.0)
    sig = np.nan_to_num(sigma_daily, nan=0.0)
    return p.impact_k * sig * np.sqrt(np.clip(part, 0, None)) * np.abs(notional)


def borrow_cost(short_notional: np.ndarray, p: CostParams) -> np.ndarray:
    """One day of borrow on short notional (positive number)."""
    return np.abs(np.minimum(short_notional, 0.0)) * p.borrow_annual / p.trading_days
