// C++ port of statarb.backtest.engine.run_backtest (daily simulation with fills, delistings, costs).
// C ABI, built as a shared library with `python -m ziglang c++ -shared -O2 -std=c++17 -o engine.dll engine.cpp`.
// Semantics are identical to the Python engine (see engine.py docstring); parity is tested in tests/test_engine_cpp.py.
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <algorithm>

#if defined(_WIN32)
#define EXPORT extern "C" __declspec(dllexport)
#else
#define EXPORT extern "C"
#endif

struct Costs {
    double commission_per_share, min_commission_per_order, max_commission_pct;
    double sec_fee_rate, finra_taf_per_share, finra_taf_max, clearing_pct_notional;
    double borrow_annual, impact_k, impact_exponent, spread_multiplier, extra_slippage_bp;
    int trading_days, pay_spread;
};

static inline bool fin(double x) { return std::isfinite(x); }

// Arrays are row-major T x N (double). NaN allowed. mark may be null (fill doubles as mark).
// delist_pos: per symbol day index (or -1); delist_ret: per symbol return.
// Outputs (length T): gross_ret, commission, fees, spread, impact, borrow, turnover, gross_exp, net_exp.
EXPORT int run_backtest_c(int T, int N, int lag, const double* W, const double* P, const double* V, const double* M,
                          const double* HS, const double* SIG, const double* ADV, const int* delist_pos, const double* delist_ret,
                          double capital, const Costs* c, double* gross_ret, double* commission, double* fees, double* spread,
                          double* impact, double* borrow, double* turnover, double* gross_exp, double* net_exp) {
    double* held = new double[N]();
    double* new_held = new double[N];
    char* dead = new char[N]();
    for (int i = 0; i < T; ++i) {
        int fi = i + lag;
        double gross = 0.0;
        if (fi < T && fi - 1 >= 0) {
            for (int j = 0; j < N; ++j) {
                double pp = M ? M[(fi - 1) * N + j] : P[(fi - 1) * N + j];
                double pn = M ? M[fi * N + j] : P[fi * N + j];
                double ret = (fin(pp) && fin(pn) && pp > 0) ? pn / pp - 1.0 : 0.0;
                if (delist_pos[j] == fi && !dead[j]) ret = delist_ret[j];
                if (fin(held[j])) gross += held[j] * ret;
                held[j] = held[j] * (1.0 + ret);
                if (delist_pos[j] == fi && !dead[j]) { held[j] = 0.0; dead[j] = 1; }
            }
        }
        int out_idx = i;  // one output row per decision day, in order (Python appends sequentially)
        if (fi >= T) {
            gross_ret[i] = gross; commission[i] = fees[i] = spread[i] = impact[i] = borrow[i] = 0.0; turnover[i] = 0.0;
            double ge = 0, ne = 0; for (int j = 0; j < N; ++j) { ge += std::fabs(held[j]); ne += held[j]; }
            gross_exp[i] = ge; net_exp[i] = ne;
            continue;
        }
        double c_comm = 0, c_fees = 0, c_spread = 0, c_imp = 0, c_borrow = 0, turn = 0;
        for (int j = 0; j < N; ++j) {
            double tgt = W[i * N + j]; if (!fin(tgt)) tgt = 0.0; if (dead[j]) tgt = 0.0;
            double price = P[fi * N + j], vol = V[fi * N + j];
            bool can = fin(price) && price > 0 && fin(vol) && vol > 0 && !dead[j];
            double nh = can ? tgt : held[j];
            double tw = nh - held[j];
            if (M) {
                double mark = M[fi * N + j];
                if (can && fin(mark) && mark > 0) { gross += tw * (mark / price - 1.0); nh = nh * (mark / price); }
            }
            double notional = tw * capital;
            double shares = (can && price > 0) ? notional / price : 0.0;
            turn += std::fabs(tw);
            double sh = std::fabs(shares);
            double comm = sh * c->commission_per_share;
            if (sh > 0) comm = std::max(comm, c->min_commission_per_order);
            comm = std::min(comm, c->max_commission_pct * std::fabs(notional));
            c_comm += comm;
            if (shares < 0) {
                c_fees += c->sec_fee_rate * std::fabs(notional) + std::min(sh * c->finra_taf_per_share, c->finra_taf_max);
            }
            c_fees += c->clearing_pct_notional * std::fabs(notional);
            if (c->pay_spread) {
                double hs = HS ? HS[i * N + j] : 0.0; if (!fin(hs)) hs = 0.0;
                c_spread += std::fabs(notional) * (hs * c->spread_multiplier + c->extra_slippage_bp / 1e4);
            }
            if (ADV && SIG) {
                double adv = ADV[fi * N + j]; if (!fin(adv)) adv = INFINITY;
                double part = adv > 0 ? sh / adv : 0.0;
                double sg = SIG[i * N + j]; if (!fin(sg)) sg = 0.0;
                c_imp += c->impact_k * sg * std::pow(std::max(part, 0.0), c->impact_exponent) * std::fabs(notional);
            }
            held[j] = nh;
        }
        for (int j = 0; j < N; ++j) if (held[j] < 0) c_borrow += -held[j] * capital * c->borrow_annual / c->trading_days;
        gross_ret[out_idx] = gross; commission[out_idx] = c_comm / capital; fees[out_idx] = c_fees / capital;
        spread[out_idx] = c_spread / capital; impact[out_idx] = c_imp / capital; borrow[out_idx] = c_borrow / capital; turnover[out_idx] = turn;
        double ge = 0, ne = 0; for (int j = 0; j < N; ++j) { ge += std::fabs(held[j]); ne += held[j]; }
        gross_exp[out_idx] = ge; net_exp[out_idx] = ne;
    }
    delete[] held; delete[] new_held; delete[] dead;
    return 0;
}
