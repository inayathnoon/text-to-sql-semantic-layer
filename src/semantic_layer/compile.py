"""Compiles a QuerySpec into SQL against the registry's governed tables and
join paths. Never string-formats a value into the SQL text: every filter
value is bound as a parameter, so a metric name typo is a KeyError at
compile time and a filter value can never become a SQL injection.
"""

from __future__ import annotations

from dataclasses import dataclass

from semantic_layer.registry import Registry
from semantic_layer.retrieve import QuerySpec

# The only join this layer knows how to make. A metric or dimension that
# needs a join path not listed here is refused by compile(), rather than
# the compiler guessing at a join condition.
JOIN_PATHS: dict[tuple[str, str], str] = {
    ("order_lines", "orders"): "order_lines.order_id = orders.order_id",
    ("order_lines", "products"): "order_lines.product_id = products.product_id",
}


class CompilationError(Exception):
    """A question the registry says is not answerable. Refusing is the
    feature: this compiler will not emit SQL it cannot justify from the
    registry."""


@dataclass(frozen=True)
class CompiledQuery:
    sql: str
    params: list
    spec: QuerySpec


def _join_clause(base_table: str, needed_table: str) -> str:
    if needed_table == base_table:
        return ""
    key = (
        (base_table, needed_table)
        if (base_table, needed_table) in JOIN_PATHS
        else (needed_table, base_table)
    )
    if key not in JOIN_PATHS:
        raise CompilationError(f"no known join path between '{base_table}' and '{needed_table}'")
    return f"JOIN {needed_table} ON {JOIN_PATHS[key]}"


def compile_query(spec: QuerySpec, registry: Registry) -> CompiledQuery:
    metric = registry.resolve_metric(spec.metric)
    base_table = metric.table

    joins: list[str] = []
    select_cols: list[str] = []
    group_cols: list[str] = []

    for dim_name in spec.group_by:
        dim = registry.resolve_dimension(dim_name)
        qualified = f"{dim.table}.{dim.column}"
        if f"{dim.table}.{dim.column}" in registry.blocked_columns:
            raise CompilationError(f"'{qualified}' is a blocked column; refusing")
        clause = _join_clause(base_table, dim.table)
        if clause and clause not in joins:
            joins.append(clause)
        select_cols.append(f"{qualified} AS {dim_name}")
        group_cols.append(qualified)

    where_clauses: list[str] = []
    params: list = []
    for filter_name, value in spec.filters.items():
        maybe_dim = registry.dimensions.get(filter_name)
        if maybe_dim is None:
            raise CompilationError(f"no dimension named '{filter_name}' to filter on")
        dim = maybe_dim
        qualified = f"{dim.table}.{dim.column}"
        clause = _join_clause(base_table, dim.table)
        if clause and clause not in joins:
            joins.append(clause)
        where_clauses.append(f"{qualified} = ?")
        params.append(value)

    if spec.window_days is not None:
        date_dim = registry.dimensions.get("order_date")
        if date_dim is None:
            raise CompilationError(
                "question implies a time window but no temporal dimension exists"
            )
        qualified = f"{date_dim.table}.{date_dim.column}"
        clause = _join_clause(base_table, date_dim.table)
        if clause and clause not in joins:
            joins.append(clause)
        window = int(spec.window_days)
        where_clauses.append(
            f"{qualified} >= (SELECT MAX({qualified}) FROM {date_dim.table}) "
            f"- INTERVAL '{window} days'"
        )

    select_cols.append(f"{metric.expr} AS {metric.name}")

    sql_parts = [f"SELECT {', '.join(select_cols)}", f"FROM {base_table}"]
    sql_parts.extend(joins)
    if where_clauses:
        sql_parts.append("WHERE " + " AND ".join(where_clauses))
    if group_cols:
        sql_parts.append("GROUP BY " + ", ".join(group_cols))
        sql_parts.append("ORDER BY " + metric.name + " DESC")

    return CompiledQuery(sql="\n".join(sql_parts), params=params, spec=spec)
