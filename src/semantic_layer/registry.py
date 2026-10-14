"""Loads semantic/metrics.yml and checks it against the warehouse schema.

The check is the point of this module, not a side effect of it. A metric
whose `table`/`expr` or a dimension's `table`/`column` names something the
warehouse doesn't have is a defect caught here - in the commit that
introduced it, via the pre-commit hook, and again in CI - rather than a
query that runs, returns a number, and is simply wrong.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

import duckdb
import yaml

from semantic_layer.config import REGISTRY_PATH, WAREHOUSE_PATH

_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_QUALIFIED = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\b")


@dataclass(frozen=True)
class Metric:
    name: str
    synonyms: list[str]
    table: str
    expr: str
    description: str
    format: str


@dataclass(frozen=True)
class Dimension:
    name: str
    synonyms: list[str]
    table: str
    column: str
    join: str | None
    temporal: bool = False


@dataclass(frozen=True)
class Registry:
    metrics: dict[str, Metric]
    dimensions: dict[str, Dimension]
    blocked_columns: set[str]

    def resolve_metric(self, name: str) -> Metric:
        return self.metrics[name]

    def resolve_dimension(self, name: str) -> Dimension:
        return self.dimensions[name]


def load_registry(path: Path = REGISTRY_PATH) -> Registry:
    raw = yaml.safe_load(path.read_text())
    metrics = {
        name: Metric(
            name=name,
            synonyms=spec.get("synonyms", []),
            table=spec["table"],
            expr=spec["expr"],
            description=spec.get("description", ""),
            format=spec.get("format", "number"),
        )
        for name, spec in raw.get("metrics", {}).items()
    }
    dimensions = {
        name: Dimension(
            name=name,
            synonyms=spec.get("synonyms", []),
            table=spec["table"],
            column=spec["column"],
            join=spec.get("join"),
            temporal=spec.get("temporal", False),
        )
        for name, spec in raw.get("dimensions", {}).items()
    }
    blocked = set(raw.get("blocked_columns", []))
    return Registry(metrics=metrics, dimensions=dimensions, blocked_columns=blocked)


def _columns_referenced(expr: str) -> set[tuple[str | None, str]]:
    """Best-effort: every identifier in an expression that isn't a known SQL
    keyword or function name, as (table_or_none, column) pairs - a bare
    `gross_revenue` is (None, 'gross_revenue'), a qualified
    `orders.region` is ('orders', 'region'). Good enough to catch a typo'd
    column or an ambiguous bare reference after a join; not a SQL parser."""
    keywords = {
        "SUM",
        "COUNT",
        "DISTINCT",
        "NULLIF",
        "AVG",
        "MIN",
        "MAX",
        "CASE",
        "WHEN",
        "THEN",
        "ELSE",
        "END",
        "AND",
        "OR",
        "NOT",
        "NULL",
    }
    qualified_spans: list[tuple[int, int]] = []
    result: set[tuple[str | None, str]] = set()
    for m in _QUALIFIED.finditer(expr):
        qualified_spans.append(m.span())
        result.add((m.group(1), m.group(2)))

    for m in _IDENT.finditer(expr):
        tok = m.group(0)
        if tok.upper() in keywords or tok.isdigit():
            continue
        if any(start <= m.start() < end for start, end in qualified_spans):
            continue  # part of a table.column pair already captured above
        result.add((None, tok))
    return result


def check(registry: Registry, warehouse_path: Path = WAREHOUSE_PATH) -> list[str]:
    """Returns a list of problems; empty means the registry agrees with the
    warehouse. Does not raise, so callers can report everything at once."""
    problems: list[str] = []
    if not warehouse_path.exists():
        return [f"warehouse not found at {warehouse_path}; run `make demo` first"]

    con = duckdb.connect(str(warehouse_path), read_only=True)
    try:
        tables = {r[0] for r in con.execute("SHOW TABLES").fetchall()}
        schema: dict[str, set[str]] = {}
        for t in tables:
            cols = con.execute(f"DESCRIBE {t}").fetchall()
            schema[t] = {c[0] for c in cols}
    finally:
        con.close()

    for m in registry.metrics.values():
        if m.table not in schema:
            problems.append(f"metric '{m.name}': table '{m.table}' not in warehouse")
            continue
        for table, column in _columns_referenced(m.expr):
            target_table = table or m.table
            if target_table not in schema:
                problems.append(
                    f"metric '{m.name}': expr references unknown table '{target_table}'"
                )
            elif column not in schema[target_table]:
                problems.append(
                    f"metric '{m.name}': expr references unknown column '{target_table}.{column}'"
                )

    for d in registry.dimensions.values():
        if d.table not in schema:
            problems.append(f"dimension '{d.name}': table '{d.table}' not in warehouse")
            continue
        if d.column not in schema[d.table]:
            problems.append(f"dimension '{d.name}': column '{d.column}' not in table '{d.table}'")

    for blocked in registry.blocked_columns:
        table, _, column = blocked.partition(".")
        if table in schema and column not in schema[table]:
            problems.append(
                f"blocked_columns entry '{blocked}' names a column that no longer exists"
            )

    return problems


def main() -> int:
    if "--check" not in sys.argv:
        print("usage: python -m semantic_layer.registry --check")
        return 2
    registry = load_registry()
    problems = check(registry)
    if problems:
        print(f"{len(problems)} problem(s):")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(
        f"registry agrees with the warehouse: {len(registry.metrics)} metrics, "
        f"{len(registry.dimensions)} dimensions"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
