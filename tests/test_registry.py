from __future__ import annotations

from semantic_layer.registry import check


def test_registry_loads_all_metrics_and_dimensions(registry):
    assert set(registry.metrics) >= {"revenue", "cost", "margin", "order_count", "aov"}
    assert set(registry.dimensions) >= {"region", "category", "order_date"}


def test_registry_agrees_with_warehouse_schema(registry, warehouse_path):
    problems = check(registry, warehouse_path=warehouse_path)
    assert problems == []


def test_check_catches_an_unknown_column(registry, warehouse_path):
    from dataclasses import replace

    broken = replace(
        registry,
        metrics={
            **registry.metrics,
            "revenue": replace(registry.metrics["revenue"], expr="SUM(not_a_real_column)"),
        },
    )
    problems = check(broken, warehouse_path=warehouse_path)
    assert any("not_a_real_column" in p for p in problems)


def test_check_catches_an_unknown_qualified_column(registry, warehouse_path):
    """Regression: aov's expr qualifies order_id as order_lines.order_id to
    avoid ambiguity after the join to orders (see compile.py). The checker
    must validate a table.column reference, not just flag it as a mystery
    bare identifier."""
    from dataclasses import replace

    broken = replace(
        registry,
        metrics={
            **registry.metrics,
            "aov": replace(registry.metrics["aov"], expr="SUM(orders.not_a_column)"),
        },
    )
    problems = check(broken, warehouse_path=warehouse_path)
    assert any("not_a_column" in p for p in problems)


def test_check_does_not_flag_a_valid_qualified_reference(registry, warehouse_path):
    # The real aov expr, as shipped, qualifies order_id. It must pass clean.
    assert "order_lines.order_id" in registry.metrics["aov"].expr
    assert check(registry, warehouse_path=warehouse_path) == []
