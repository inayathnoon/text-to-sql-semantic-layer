"""The one test that exercises the whole chain: a question in, a correct
number out, checked against a plain aggregate computed independently."""

from __future__ import annotations

import duckdb

from semantic_layer.ask import ask


def test_revenue_by_region_matches_a_plain_aggregate(registry, warehouse_path):
    result = ask("revenue by region", registry=registry, warehouse_path=warehouse_path)
    assert set(result.frame["region"]) == {"EMEA", "APAC", "AMER"}

    con = duckdb.connect(str(warehouse_path), read_only=True)
    try:
        expected = con.execute(
            """
            SELECT orders.region, SUM(order_lines.gross_revenue) AS revenue
            FROM order_lines JOIN orders ON order_lines.order_id = orders.order_id
            GROUP BY orders.region
            """
        ).fetchdf()
    finally:
        con.close()

    got = result.frame.set_index("region")["revenue"].sort_index()
    want = expected.set_index("region")["revenue"].sort_index()
    assert (got - want).abs().max() < 0.01


def test_aov_matches_a_plain_aggregate(registry, warehouse_path):
    result = ask("average order value", registry=registry, warehouse_path=warehouse_path)

    con = duckdb.connect(str(warehouse_path), read_only=True)
    try:
        expected = con.execute(
            "SELECT SUM(gross_revenue) / COUNT(DISTINCT order_id) FROM order_lines"
        ).fetchone()[0]
    finally:
        con.close()

    assert abs(result.frame.iloc[0, 0] - expected) < 0.01


def test_sql_is_reproducible_for_the_same_question(registry, warehouse_path):
    first = ask("revenue by region last 90 days", registry=registry, warehouse_path=warehouse_path)
    second = ask("revenue by region last 90 days", registry=registry, warehouse_path=warehouse_path)
    assert first.sql == second.sql
    assert first.frame.equals(second.frame)
