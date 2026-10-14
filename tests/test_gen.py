from __future__ import annotations

from semantic_layer.config import load_config
from semantic_layer.gen import generate


def test_generate_is_deterministic_under_the_configured_seed():
    cfg = load_config()
    first = generate(cfg)
    second = generate(cfg)
    for name in first:
        assert first[name].equals(second[name]), f"{name} differs across runs with the same seed"


def test_row_counts_match_config():
    cfg = load_config()
    tables = generate(cfg)
    assert len(tables["customers"]) == cfg.n_customers
    assert len(tables["products"]) == cfg.n_products
    assert len(tables["orders"]) == cfg.n_orders


def test_order_lines_reference_real_orders_and_products():
    cfg = load_config()
    tables = generate(cfg)
    order_ids = set(tables["orders"]["order_id"])
    product_ids = set(tables["products"]["product_id"])
    assert set(tables["order_lines"]["order_id"]) <= order_ids
    assert set(tables["order_lines"]["product_id"]) <= product_ids


def test_dates_within_configured_window():
    import pandas as pd

    cfg = load_config()
    tables = generate(cfg)
    dates = tables["orders"]["order_date"]
    assert dates.min() >= pd.Timestamp(cfg.date_start)
    assert dates.max() <= pd.Timestamp(cfg.date_end)
