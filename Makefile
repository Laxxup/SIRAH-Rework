UV ?= uv

.PHONY: check test lint format run setup doctor

check: lint test

lint:
	$(UV) run ruff check .
	$(UV) run ruff format --check .

format:
	$(UV) run ruff format .

test:
	$(UV) run pytest

run:
	$(UV) run sirah

setup:
	$(UV) run sirah setup

doctor:
	$(UV) run sirah doctor
