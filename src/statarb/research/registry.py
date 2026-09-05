"""Hypothesis / experiment registry helpers: append rows BEFORE running, fill results AFTER. Never delete rows."""

from __future__ import annotations

import csv
from datetime import date

from statarb.config import REPO_ROOT

REG = REPO_ROOT / "04_HYPOTHESIS_REGISTRY.csv"
FIELDS = ["experiment_id", "date", "trial_type", "hypothesis", "signal_definition", "universe", "holding_period",
          "features", "model", "parameters", "train_period", "validation_period", "expected_result",
          "falsification_condition", "actual_result", "decision"]


def _read() -> list[dict]:
    with open(REG, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _write(rows: list[dict]) -> None:
    with open(REG, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


def register(experiment_id: str, trial_type: str, **kw) -> None:
    """Add a row with actual_result/decision = PENDING. Raises if the id exists (no silent overwrite)."""
    rows = _read()
    if any(r["experiment_id"] == experiment_id for r in rows):
        raise ValueError(f"{experiment_id} already registered")
    row = {k: "" for k in FIELDS}
    row.update({"experiment_id": experiment_id, "date": str(date.today()), "trial_type": trial_type,
                "actual_result": "PENDING", "decision": "PENDING"})
    row.update({k: str(v) for k, v in kw.items() if k in FIELDS})
    rows.append(row)
    _write(rows)


def record(experiment_id: str, actual_result: str, decision: str) -> None:
    rows = _read()
    for r in rows:
        if r["experiment_id"] == experiment_id:
            r["actual_result"] = actual_result
            r["decision"] = decision
            _write(rows)
            return
    raise KeyError(experiment_id)


def count(trial_type: str = "candidate") -> int:
    return sum(1 for r in _read() if r["trial_type"] == trial_type)
