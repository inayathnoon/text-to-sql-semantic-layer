from __future__ import annotations

import pytest

from semantic_layer.config import load_config
from semantic_layer.gen import generate, load
from semantic_layer.registry import load_registry


@pytest.fixture(scope="session")
def warehouse_path(tmp_path_factory):
    path = tmp_path_factory.mktemp("warehouse") / "warehouse.duckdb"
    cfg = load_config()
    tables = generate(cfg)
    load(tables, path=path)
    return path


@pytest.fixture(scope="session")
def registry():
    return load_registry()
