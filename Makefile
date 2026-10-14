.PHONY: setup demo test lint

setup:
	uv venv --python 3.11
	uv sync --frozen --extra dev

demo:
	uv run python -m semantic_layer.gen
	uv run python -m semantic_layer.registry --check
	uv run python -m semantic_layer.ask "what was revenue by region last 90 days?"
	uv run python -m semantic_layer.ask "average order value in apac"
	uv run python -m semantic_layer.ask "units sold by category"

test:
	uv run pytest -q

lint:
	uv run ruff check src tests
	uv run ruff format --check src tests
	uv run mypy src
