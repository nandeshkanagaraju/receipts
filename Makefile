# Receipts — SDD §28. Every target either does the thing or fails loudly.
# Targets whose implementing module does not exist yet print "not built yet"
# and exit 1. None of them ever exits 0 without doing the work.

PY      := .venv/bin/python
PIP     := .venv/bin/pip
PYTEST  := .venv/bin/pytest
RUFF    := .venv/bin/ruff
MYPY    := .venv/bin/mypy
SET     ?= dev

.PHONY: setup data test eval eval-holdout lint types up bench freeze-check freeze-questions

# --- implemented -------------------------------------------------------------

setup:
	uv venv --python python3.11 .venv
	uv pip install --python $(PY) -e ".[dev]"
	@echo "setup: done. Interpreter: $$($(PY) --version)"

test:
	$(PYTEST)

lint:
	$(RUFF) check .
	$(RUFF) format --check .

types:
	$(MYPY)

freeze-check:
	$(PY) scripts/freeze.py --check

freeze-questions:
	$(PY) scripts/freeze_questions.py

# --- not built yet -----------------------------------------------------------
# Each names the module that will implement it (docs/BUILD_PROMPTS.md).

define NOT_BUILT
@echo "make $(1): not built yet — implemented in module $(2)" >&2; exit 1
endef

data:
	$(call NOT_BUILT,data,M2 — synthetic world generator)

eval:
	$(call NOT_BUILT,eval SET=$(SET),M4 — scoring/reports/harness)

eval-holdout:
	$(call NOT_BUILT,eval-holdout,M21 — holdout run)

up:
	$(call NOT_BUILT,up,M20 — deploy/compose)

bench:
	$(call NOT_BUILT,bench,M20 — benchmark)
