from __future__ import annotations

import pytest

from semantic_layer.compile import CompilationError, compile_query
from semantic_layer.retrieve import QuerySpec


def test_simple_metric_no_join(registry):
    compiled = compile_query(QuerySpec(metric="order_count"), registry)
    assert "JOIN" not in compiled.sql
    assert "orders" in compiled.sql


def test_group_by_adds_join_when_needed(registry):
    compiled = compile_query(QuerySpec(metric="units_sold", group_by=["category"]), registry)
    assert "JOIN products" in compiled.sql
    assert "GROUP BY products.category" in compiled.sql


def test_filter_binds_a_parameter_not_a_literal(registry):
    compiled = compile_query(QuerySpec(metric="revenue", filters={"region": "APAC"}), registry)
    assert "?" in compiled.sql
    assert "APAC" not in compiled.sql  # value is bound, never interpolated
    assert compiled.params == ["APAC"]


def test_unknown_filter_dimension_refuses(registry):
    with pytest.raises(CompilationError):
        compile_query(QuerySpec(metric="revenue", filters={"not_a_dimension": "x"}), registry)


def test_blocked_column_refuses_even_as_group_by(registry):
    from dataclasses import replace

    # Point a dimension at a column the registry has blocked, and confirm
    # compile_query refuses to emit SQL for it rather than quietly dropping
    # the group-by.
    blocked_dim = replace(
        registry.dimensions.get("region") or next(iter(registry.dimensions.values())),
        name="signup_date",
        table="customers",
        column="signup_date",
    )
    rigged = replace(
        registry,
        dimensions={**registry.dimensions, "signup_date": blocked_dim},
        blocked_columns=registry.blocked_columns | {"customers.signup_date"},
    )
    with pytest.raises(CompilationError):
        compile_query(QuerySpec(metric="revenue", group_by=["signup_date"]), rigged)


def test_window_adds_date_filter(registry):
    compiled = compile_query(QuerySpec(metric="revenue", window_days=30), registry)
    assert "INTERVAL '30 days'" in compiled.sql
