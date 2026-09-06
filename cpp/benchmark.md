# C++ engine benchmark

Component: the daily simulation engine (fills, delistings, mark-vs-fill execution P&L, all cost components) — the loop every
grid, robustness and holdout run repeats (cpp/engine.cpp, C ABI, built with `python -m ziglang c++ -shared -O2 -std=c++17`;
ctypes wrapper src/statarb/backtest/engine_cpp.py).

Parity: tests/test_engine_cpp.py — hand-computed case and a 300x25 random panel with delistings, mark/fill split, commissions,
regulatory fees, clearing, impact, spread and borrow; all columns agree with the Python engine to 1e-9.

Benchmark (synthetic panel T=3500 days x N=782 symbols, one delisting, market-maker costs, Windows 11, Python 3.14):

| engine | wall time | peak traced memory (Python side) | sum of net returns |
|---|---|---|---|
| python (numpy per-day loop) | 3.96 s | 3 MB | -2.121004 |
| cpp (ziglang/clang -O2) | 0.59 s | 89 MB | -2.121004 |

Speed-up 6.7x on the engine step. Honest assessment: after the feature-caching fixes the engine is
~40% of a strategy run (the rest is weight construction in pandas), so end-to-end runs gain ~1.5-2x; the C++ engine is
used for the robustness/grid batches via STATARB_ENGINE=cpp and the Python engine remains the reference implementation.
