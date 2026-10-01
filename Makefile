PYTHON ?= python3

.PHONY: install test lint format format-check typecheck validate-data mock-smoke mock-report check

install:
	$(PYTHON) -m pip install -e ".[dev]"

test:
	$(PYTHON) -m pytest

lint:
	$(PYTHON) -m ruff check .

format:
	$(PYTHON) -m ruff format .

format-check:
	$(PYTHON) -m ruff format --check .

typecheck:
	$(PYTHON) -m mypy src

validate-data:
	pie validate-data --dataset data/cases.jsonl

mock-smoke:
	pie run --provider mock --dataset data/smoke_cases.jsonl --condition both --output-dir results/mock-smoke --overwrite

mock-report:
	pie analyze --input-dir results/mock-smoke --output-dir reports/mock-smoke
	pie review --input results/mock-smoke/raw_results.jsonl --output results/mock-smoke/manual_review.csv

check: lint format-check typecheck test
