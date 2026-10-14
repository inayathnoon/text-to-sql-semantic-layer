"""End to end: a question in, a dataframe and the SQL that produced it out.

This is the whole point of the repo in one function. Everything upstream
(registry, retrieve, compile) exists so that `ask()` either answers from a
definition someone can point to, or refuses with a reason - never a number
with no accountable source.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import duckdb
import pandas as pd

from semantic_layer.compile import CompiledQuery, compile_query
from semantic_layer.config import WAREHOUSE_PATH
from semantic_layer.registry import Registry, load_registry
from semantic_layer.retrieve import QuerySpec, resolve


@dataclass(frozen=True)
class AskResult:
    question: str
    spec: QuerySpec
    sql: str
    frame: pd.DataFrame


def ask(
    question: str,
    registry: Registry | None = None,
    warehouse_path: Path = WAREHOUSE_PATH,
) -> AskResult:
    registry = registry or load_registry()
    spec = resolve(question, registry)
    compiled: CompiledQuery = compile_query(spec, registry)

    con = duckdb.connect(str(warehouse_path), read_only=True)
    try:
        frame = con.execute(compiled.sql, compiled.params).fetchdf()
    finally:
        con.close()

    return AskResult(question=question, spec=spec, sql=compiled.sql, frame=frame)


def main() -> None:
    import sys

    if len(sys.argv) < 2:
        print('usage: python -m semantic_layer.ask "what was revenue by region last 90 days?"')
        raise SystemExit(2)
    question = " ".join(sys.argv[1:])
    result = ask(question)
    print(f"# {question}\n")
    print(result.sql)
    print()
    print(result.frame.to_string(index=False))


if __name__ == "__main__":
    main()
