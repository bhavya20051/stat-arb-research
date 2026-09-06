"""Stage 3 (unattended): after stage 2 -> freeze -> locked holdout batch (once) -> final HTML report."""

from __future__ import annotations

import os
import time
import warnings

warnings.filterwarnings("ignore")
LOG = lambda *a: print(time.strftime("%H:%M:%S"), *a, flush=True)
S2_LOG = r"C:\Users\bhavy\statarb_data\pipeline_stage2.log"


def main():
    while True:
        try:
            if "STAGE 2 DONE" in open(S2_LOG, encoding="utf-8", errors="ignore").read():
                break
        except FileNotFoundError:
            pass
        LOG("waiting for stage 2 ...")
        time.sleep(120)
    from statarb.research.holdout import freeze, run_holdout
    frozen = freeze()
    LOG("frozen: " + ", ".join(f"{k}: {v['status']}" for k, v in frozen["families"].items()))
    t = time.time()
    res = run_holdout(frozen)
    for fam, r in res["families"].items():
        if r.get("status") == "run":
            LOG(f"HOLDOUT {fam}: net SR {r['holdout_net_sharpe']:.2f} net ann {r['holdout_net_ann']:.3f} maxDD {r['holdout_max_dd']:.2f}")
        else:
            LOG(f"HOLDOUT {fam}: {r.get('status')}")
    LOG(f"holdout batch done in {time.time()-t:.0f}s")
    from statarb.reporting.html_report import build_report
    LOG("report: " + str(build_report()))
    LOG("STAGE 3 DONE")


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
    main()
