# Receipts — SDD §28. Every target either does the thing or fails loudly.
# Targets whose implementing module does not exist yet print "not built yet"
# and exit 1. None of them ever exits 0 without doing the work.

# Use the local virtualenv when there is one, otherwise whatever is on PATH.
# CI installs into the system interpreter and has no .venv, which is how
# `make data` died with exit 127 for want of .venv/bin/python.
VENV    := $(shell [ -x .venv/bin/python ] && echo .venv/bin || echo "")
PY      := $(if $(VENV),$(VENV)/python,python)
PIP     := $(if $(VENV),$(VENV)/pip,pip)
PYTEST  := $(if $(VENV),$(VENV)/pytest,pytest)
RUFF    := $(if $(VENV),$(VENV)/ruff,ruff)
MYPY    := $(if $(VENV),$(VENV)/mypy,mypy)
SET     ?= dev

.PHONY: setup data test eval eval-holdout lint types up bench freeze-check freeze-questions freeze-gen seed-check freeze-translations double-compute

# --- implemented -------------------------------------------------------------

setup:
	uv venv --python python3.11 .venv
	uv pip install --python $(PY) -e ".[dev]"
	# Tracked hooks, so a fresh clone gets the commit-msg guard without anyone
	# remembering to install it. Twenty-five holdout qids reached commit messages
	# on main, every one written by someone who knew the rule.
	git config core.hooksPath .githooks
	@echo "setup: done. Interpreter: $$($(PY) --version), hooks: $$(git config --get core.hooksPath)"

test:
	$(PYTEST)

lint:
	$(RUFF) check .
	$(RUFF) format --check .

types:
	$(MYPY)

freeze-check:
	$(PY) scripts/freeze.py --check

seed-check:
	@if [ -n "$$KESTREL_SEALED_SEED" ]; then echo "seed present: yes (environment)"; \
	elif [ -f .env ] && grep -q '^KESTREL_SEALED_SEED=' .env; then echo "seed present: yes (.env)"; \
	else echo "seed present: no"; exit 1; fi

# REOPEN=yes re-freezes after a conformance fix, creating the next gen-frozen-N
# tag (ADR-014). Without it a second freeze is refused, which is the default.
freeze-gen:
	$(PY) scripts/freeze_gen.py $(if $(REOPEN),--reopen,)

freeze-questions:
	$(PY) scripts/freeze_questions.py

freeze-translations:
	$(PY) scripts/freeze_translations.py

# The second, independent computation of every reference answer (M3, SDD §6).
# Rewrites tests/fixtures/double.json, which test_reference_double_computation
# compares against the SQL. Takes several minutes: it recomputes every cell of
# every breakdown in pandas rather than sampling.
double-compute:
	$(PY) -m scripts.double_compute

# --- not built yet -----------------------------------------------------------
# Each names the module that will implement it (docs/BUILD_PROMPTS.md).

define NOT_BUILT
@echo "make $(1): not built yet — implemented in module $(2)" >&2; exit 1
endef

data:
	@if [ -z "$$KESTREL_SEALED_SEED" ] && [ -f .env ]; then \
		set -a; . ./.env; set +a; \
	fi; \
	if [ -z "$$KESTREL_SEALED_SEED" ]; then \
		echo "KESTREL_SEALED_SEED is not set and .env has no value for it" >&2; exit 1; \
	fi; \
	echo "seed present: yes"; \
	TIMER=""; \
	if /usr/bin/time -l true >/dev/null 2>&1; then TIMER="/usr/bin/time -l"; \
	elif /usr/bin/time -v true >/dev/null 2>&1; then TIMER="/usr/bin/time -v"; fi; \
	$$TIMER $(PY) -m kestrel_gen --seed 20260910 --scale $${SCALE:-0.55} --out data

eval:
	$(call NOT_BUILT,eval SET=$(SET),M4 — scoring/reports/harness)

eval-holdout:
	$(call NOT_BUILT,eval-holdout,M21 — holdout run)

up:
	$(call NOT_BUILT,up,M20 — deploy/compose)

bench:
	$(call NOT_BUILT,bench,M20 — benchmark)
