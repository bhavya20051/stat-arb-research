"""Simulation tests for the statistics module (acceptance gates from the plan, section 9)."""

import numpy as np
from scipy import stats

from statarb.statistics.metrics import (
    EULER_GAMMA,
    bootstrap_sharpe_ci,
    dsr,
    dsr_threshold,
    pbo_cscv,
    psr,
    sharpe,
    sharpe_se_iid,
)


def test_psr_uniform_under_null():
    rng = np.random.default_rng(0)
    vals = np.array([psr(rng.normal(0, 0.01, 500)) for _ in range(300)])
    assert stats.kstest(vals, "uniform").pvalue > 0.01


def test_psr_high_for_true_positive_sharpe():
    rng = np.random.default_rng(1)
    r = rng.normal(0.001, 0.01, 2000)  # per-period SR 0.1 -> annualised ~1.6
    assert psr(r) > 0.99


def test_dsr_threshold_formula():
    var_sr, n = 0.01, 100
    z1 = stats.norm.ppf(1 - 1 / n)
    z2 = stats.norm.ppf(1 - 1 / (n * np.e))
    expected = np.sqrt(var_sr) * ((1 - EULER_GAMMA) * z1 + EULER_GAMMA * z2)
    assert np.isclose(dsr_threshold(var_sr, n), expected)
    assert dsr_threshold(var_sr, 1) == 0.0


def test_dsr_rejects_best_of_noise_at_nominal_rate():
    rng = np.random.default_rng(2)
    rejections = 0
    trials = 120
    for _ in range(trials):
        R = rng.normal(0, 0.01, size=(400, 25))
        srs = np.array([sharpe(R[:, k]) for k in range(25)])
        best = int(np.argmax(srs))
        if dsr(R[:, best], srs) > 0.95:
            rejections += 1
    # naive PSR of the best would exceed 0.95 far more often than 5%; DSR should stay near nominal
    assert rejections / trials < 0.15


def test_pbo_near_half_for_noise():
    rng = np.random.default_rng(3)
    M = rng.normal(0, 0.01, size=(800, 10))
    res = pbo_cscv(M, n_blocks=8)
    assert res["n_combinations"] == 70
    assert 0.25 <= res["pbo"] <= 0.75


def test_pbo_low_for_one_genuinely_good_strategy():
    rng = np.random.default_rng(4)
    M = rng.normal(0, 0.01, size=(800, 10))
    M[:, 0] += 0.004  # strong true edge
    assert pbo_cscv(M, n_blocks=8)["pbo"] < 0.1


def test_bootstrap_ci_covers_true_sharpe():
    rng = np.random.default_rng(5)
    r = rng.normal(0.0005, 0.01, 1500)  # true per-period SR 0.05
    lo, hi, _ = bootstrap_sharpe_ci(r, n_boot=300, block_mean=5, seed=5)
    assert lo < 0.05 < hi
    assert np.isclose(sharpe_se_iid(0.0, 100), 0.1)
