"""Configuration, paths and secrets. The FMP key is read from a file or env var and never logged."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = REPO_ROOT / "configs"
KEY_FILE = Path.home() / ".fmp_api_key"


def data_dir() -> Path:
    base = os.environ.get("STATARB_DATA_DIR")
    if not base:
        cfg = load_config("base")
        base = cfg.get("data_dir_default", str(Path.home() / "statarb_data"))
    p = Path(base)
    p.mkdir(parents=True, exist_ok=True)
    return p


def load_config(name: str) -> dict[str, Any]:
    path = CONFIG_DIR / f"{name}.yaml"
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def config_hash(*names: str) -> str:
    h = hashlib.sha256()
    for n in names:
        h.update(json.dumps(load_config(n), sort_keys=True, default=str).encode())
    return h.hexdigest()[:16]


def fmp_api_key() -> str:
    """Return the FMP key from env or the key file. Raises if absent. Never print the result."""
    key = os.environ.get("FMP_API_KEY", "").strip()
    if not key and KEY_FILE.exists():
        key = KEY_FILE.read_text(encoding="utf-8").strip()
    if not key:
        raise RuntimeError(
            "FMP API key not found: set env FMP_API_KEY or save it to %s" % KEY_FILE
        )
    return key
