UV ?= uv

.PHONY: check test lint format run setup doctor guard

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

# Rutas intocables (AGENTS.md sección 5). Necesita git.
guard:
	@git rev-parse --git-dir >/dev/null 2>&1 || { echo "guard: no es un repo git; haz git init y un commit base"; exit 1; }
	@changed=$$(git status --porcelain -- firmware config/eyes-calibration.toml models); \
	if [ -n "$$changed" ]; then echo "guard: se tocaron rutas intocables:"; echo "$$changed"; exit 1; fi; \
	echo "guard: ok"
