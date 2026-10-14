"""Typed config and the paths every module shares."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONF_PATH = ROOT / "conf" / "sim.yaml"
REGISTRY_PATH = ROOT / "semantic" / "metrics.yml"
WAREHOUSE_PATH = ROOT / "warehouse" / "warehouse.duckdb"


@dataclass(frozen=True)
class SimConfig:
    seed: int
    n_customers: int
    n_products: int
    n_orders: int
    date_start: str
    date_end: str
    regions: list[str]
    categories: list[str]


def load_config(path: Path = CONF_PATH) -> SimConfig:
    raw = yaml.safe_load(path.read_text())
    return SimConfig(**raw)
