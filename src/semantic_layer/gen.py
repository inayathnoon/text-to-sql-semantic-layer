"""Synthetic sales warehouse: customers, products, orders, order lines.

Five tables, one obvious grain each. Nothing here claims to model real
customer behaviour - it only needs to be internally consistent enough that
the metrics in semantic/metrics.yml have something true to compute against.
"""

from __future__ import annotations

import duckdb
import numpy as np
import pandas as pd

from semantic_layer.config import WAREHOUSE_PATH, SimConfig, load_config

REGION_WEIGHT = {"EMEA": 0.4, "APAC": 0.35, "AMER": 0.25}
CATEGORY_PRICE_RANGE = {
    "electronics": (40, 600),
    "home": (15, 250),
    "apparel": (10, 120),
    "grocery": (3, 40),
    "beauty": (5, 80),
}


def _customers(cfg: SimConfig, rng: np.random.Generator) -> pd.DataFrame:
    regions = list(cfg.regions)
    weights = np.array([REGION_WEIGHT.get(r, 1 / len(regions)) for r in regions])
    weights = weights / weights.sum()
    return pd.DataFrame(
        {
            "customer_id": np.arange(1, cfg.n_customers + 1),
            "region": rng.choice(regions, size=cfg.n_customers, p=weights),
            "signup_date": pd.to_datetime(cfg.date_start)
            - pd.to_timedelta(rng.integers(0, 900, size=cfg.n_customers), unit="D"),
        }
    )


def _products(cfg: SimConfig, rng: np.random.Generator) -> pd.DataFrame:
    categories = rng.choice(list(cfg.categories), size=cfg.n_products)
    prices = np.array([rng.uniform(*CATEGORY_PRICE_RANGE[c]) for c in categories]).round(2)
    cost_ratio = rng.uniform(0.45, 0.75, size=cfg.n_products)
    return pd.DataFrame(
        {
            "product_id": np.arange(1, cfg.n_products + 1),
            "category": categories,
            "unit_price": prices,
            "unit_cost": (prices * cost_ratio).round(2),
        }
    )


def _orders_and_lines(
    cfg: SimConfig,
    rng: np.random.Generator,
    customers: pd.DataFrame,
    products: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    dates = pd.date_range(cfg.date_start, cfg.date_end, freq="D")
    # A mild weekly seasonality and a slow upward trend, so "this month vs
    # last" and "trend over time" questions have something to find.
    day_idx = np.arange(len(dates))
    trend = 1.0 + 0.0006 * day_idx
    dow_weight = np.where(pd.Index(dates).dayofweek >= 5, 1.35, 1.0)
    daily_weight = trend * dow_weight
    daily_weight = daily_weight / daily_weight.sum()

    order_dates = rng.choice(dates, size=cfg.n_orders, p=daily_weight)
    order_customers = rng.choice(customers["customer_id"], size=cfg.n_orders)

    orders = pd.DataFrame(
        {
            "order_id": np.arange(1, cfg.n_orders + 1),
            "customer_id": order_customers,
            "order_date": order_dates,
        }
    ).merge(customers[["customer_id", "region"]], on="customer_id", how="left")

    # 1-4 lines per order, Poisson-ish via truncated geometric.
    n_lines = rng.integers(1, 5, size=cfg.n_orders)
    line_order_id = np.repeat(orders["order_id"].to_numpy(), n_lines)
    total_lines = len(line_order_id)

    line_products = rng.choice(products["product_id"], size=total_lines)
    quantities = rng.integers(1, 6, size=total_lines)

    lines = pd.DataFrame(
        {
            "order_line_id": np.arange(1, total_lines + 1),
            "order_id": line_order_id,
            "product_id": line_products,
            "quantity": quantities,
        }
    ).merge(products[["product_id", "unit_price", "unit_cost"]], on="product_id", how="left")
    lines["gross_revenue"] = (lines["quantity"] * lines["unit_price"]).round(2)
    lines["gross_cost"] = (lines["quantity"] * lines["unit_cost"]).round(2)
    lines = lines.drop(columns=["unit_price", "unit_cost"])

    return orders, lines


def generate(cfg: SimConfig | None = None) -> dict[str, pd.DataFrame]:
    cfg = cfg or load_config()
    rng = np.random.default_rng(cfg.seed)

    customers = _customers(cfg, rng)
    products = _products(cfg, rng)
    orders, lines = _orders_and_lines(cfg, rng, customers, products)

    return {
        "customers": customers,
        "products": products,
        "orders": orders,
        "order_lines": lines,
    }


def load(tables: dict[str, pd.DataFrame], path=WAREHOUSE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    con = duckdb.connect(str(path))
    try:
        for name, df in tables.items():
            con.register(f"_{name}", df)
            con.execute(f"CREATE TABLE {name} AS SELECT * FROM _{name}")
    finally:
        con.close()


def main() -> None:
    cfg = load_config()
    tables = generate(cfg)
    load(tables)
    for name, df in tables.items():
        print(f"{name:<14} {len(df):>8,} rows")


if __name__ == "__main__":
    main()
