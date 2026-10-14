# text-to-sql-semantic-layer

A metric registry and synonym-retrieval layer that resolves a free-text question into
governed SQL against a warehouse, and refuses rather than guesses when it cannot.

> **Synthetic data notice.** All data in this repository is programmatically generated. It
> contains no proprietary, confidential, or personal data, and no real operational figures.
> This is a reimplementation of analytical methodology on simulated data, built to demonstrate
> technique. Results shown are properties of the simulator, not of any organisation.

---

## Problem

A business glossary spread across people's heads is worse than no glossary. Ask three
analysts what "revenue" means and you get three different joins, two different date
filters, and a number that changes depending on who ran the query. A text-to-SQL layer
built directly on an LLM's guess at column names inherits the same problem and hides it
better: the query runs, returns a plausible number, and nobody checks.

This repo separates the two jobs that get conflated. **Retrieval** maps a question's
vocabulary ("basket size", "AOV", "average order value") onto one canonical metric name.
**Compilation** turns that metric name into SQL using only the table, column and join
paths the registry says are valid. Neither step touches an LLM, on purpose: the registry
is the thing that needs to be right, and a synonym matcher over it is auditable in a way a
model call is not. Swapping the matcher for an embedding search or an LLM re-ranker over
the same registry is additive later, not a rewrite.

---

## Architecture

```
semantic/metrics.yml          the glossary: metrics, dimensions, synonyms, blocked columns
        |
        v
registry.py    loads it, and checks it against the warehouse schema (CI + pre-commit)
        |
        v
retrieve.py    question -> QuerySpec (metric, group_by, filters, window)
        |        refuses on a tie between two equally-good matches
        v
compile.py     QuerySpec -> parameterised SQL, using only known join paths
        |        refuses if a dimension needs a join the registry doesn't define
        v
ask.py         runs it against warehouse.duckdb, returns the dataframe and the SQL
```

A question either produces a number with a SQL string anyone can read and challenge, or
it raises `ResolutionError` / `CompilationError` with a reason. There is no third outcome.

---

## Method

### 1. The registry is checked against the warehouse, not just syntax-valid

`registry.py --check` parses every metric's `expr` and every dimension's `column`,
compares them against `DESCRIBE` on the live warehouse tables, and fails if any of them
reference something that doesn't exist. This runs in pre-commit (scoped to
`semantic/metrics.yml` and `gen.py`) and again in CI. A metric definition that drifts from
a schema migration is a build failure in the commit that caused it, not a dashboard number
that's quietly been wrong for a week.

### 2. Retrieval refuses ties instead of picking one

Each metric and dimension lists its synonyms. A question's tokens are matched against
every candidate's synonym phrases; whichever candidate's tokens are most fully covered
wins. If two metrics tie, `resolve()` raises rather than picking the first one
alphabetically - an silent default there is indistinguishable from a correct match until
someone checks the number.

### 3. Compilation only uses declared join paths

`JOIN_PATHS` is a closed list of two entries: `order_lines -> orders` and
`order_lines -> products`. Grouping by a dimension that would need a join not in that
list raises `CompilationError`. This is the same shape as the blocked-column list: both
exist to make "what the compiler refuses to do" an explicit, readable set rather than
"whatever doesn't happen to throw."

### 4. Filter values are bound, never interpolated

Every `WHERE` clause value - region, category - is a `?` placeholder passed through
`duckdb`'s parameter binding. The SQL text itself is built only from table and column
names that came from the registry. There is no path from question text to the SQL
string.

---

## What this does not attempt

- **No LLM call.** This is the grounding layer an LLM-backed tool sits on top of, not a
  claim that synonym matching alone is what production text-to-SQL should ship with. The
  production version at the job this is modelled on uses an LLM for the parts a fixed
  vocabulary can't cover - compound questions, typos, genuinely novel phrasing - but
  always resolves against this same kind of registry, never free-floating.
- **No multi-table group-by beyond two dimensions worth of joins.** The join graph here
  is two edges. A real warehouse's semantic layer needs a proper join-path solver; this
  repo demonstrates the refuse-on-unknown-join discipline, not the solver.
- **No caching, no query cost estimation, no row-level security beyond the
  blocked-columns list.** All real concerns in production, out of scope for demonstrating
  the registry/retrieval/compile split.

---

## How to run

```bash
make setup   # uv venv + install (Python 3.11+, offline, no credentials)
make demo    # generate -> load -> registry check -> a few example questions
make test    # pytest
```

```bash
uv run python -m semantic_layer.ask "what was revenue by region last 90 days?"
uv run python -m semantic_layer.ask "average order value in apac"
uv run python -m semantic_layer.ask "units sold by category"
```

---

## Repo map

```
conf/sim.yaml                every number in the repo traces here
semantic/metrics.yml         the glossary
src/semantic_layer/
  gen.py                     synthetic customers, products, orders, order lines
  registry.py                load + check the glossary against the warehouse
  retrieve.py                question -> QuerySpec
  compile.py                 QuerySpec -> parameterised SQL
  ask.py                     end to end; the CLI
tests/                       retrieval, compilation, refusal paths, end-to-end
```
