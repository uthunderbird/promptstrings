.PHONY: test lint typecheck build install-hooks all

test:
	uv run pytest -q

lint:
	uv run ruff check .
	uv run ruff format --check .

typecheck:
	uv run mypy src/

build:
	uv build

install-hooks:
	uv run pre-commit install

all: lint typecheck test
