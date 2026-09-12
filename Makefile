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
	# --python .venv/bin/python, not $(PY). Before the venv exists $(PY) falls
	# back to the bare name `python`, and uv looks for an interpreter by that
	# name on PATH -- which a fresh machine need not have. The path is what was
	# just created one line above, so name it.
	uv pip install --python .venv/bin/python -e ".[dev]"
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

# SET defaults to dev. The holdout has its own target and its own confirmation,
# so reaching it takes two deliberate acts rather than one forgotten flag (D17).
eval:
	$(PY) -m receipts.evalkit.harness --system $${SYSTEM:-oracle} --set $${SET:-dev}

eval-holdout:
	@if [ "$$CONFIRM_HOLDOUT" != "yes" ]; then \
		echo "the holdout runs once (D17). CONFIRM_HOLDOUT=yes if that is what you mean." >&2; \
		exit 1; \
	fi
	CONFIRM_HOLDOUT=yes $(PY) -m receipts.evalkit.harness --system $${SYSTEM:-oracle} --set holdout

up:
	$(call NOT_BUILT,up,M20 — deploy/compose)

bench:
	$(call NOT_BUILT,bench,M20 — benchmark)

fault-table:             ## Print the F1-F12 fault-injection status table (SDD §12.5).
	$(PY) scripts/fault_table.py

canary-sweep:            ## F12: sweep every scoped dev trial for a planted canary (T7).
	$(PY) scripts/canary_sweep.py

semantic-lint:           ## Lint the semantic layer (SDD §7.3) and list the metrics.
	$(PY) -m receipts.semantic.lint --list

# --- Baseline B0 (SDD §25.4). The only targets that spend money. ----------- #
# A repo-local scratch path, not $(TMPDIR): TMPDIR is set on macOS and empty on
# most Linux CI images, where the copy would have landed in the working tree.
BASELINE_TMP := .make/baseline_first.json
# OPENAI_API_KEY must be in the environment (ADR-018). It is never echoed, never
# written to a file, and never passed on a command line.

baseline-smoke:          ## 3 live calls, no report written. Run this first.
	@test -n "$$OPENAI_API_KEY" || { echo "OPENAI_API_KEY is not set" >&2; exit 1; }
	RECEIPTS_LLM_MODE=record $(PY) -m receipts.evalkit.harness \
	  --system baseline --set dev --limit 3

baseline-record:         ## ~180 live calls, ~$$14. Writes recordings and the report.
	@test -n "$$OPENAI_API_KEY" || { echo "OPENAI_API_KEY is not set" >&2; exit 1; }
	RECEIPTS_LLM_MODE=record $(PY) -m receipts.evalkit.harness --system baseline --set dev

baseline-verify:         ## Replay twice and prove the two reports are byte-identical (D16).
	@mkdir -p .make
	@RECEIPTS_LLM_MODE=replay $(PY) -m receipts.evalkit.harness --system baseline --set dev \
	  > /dev/null
	@cp eval/results/dev/baseline/report.json $(BASELINE_TMP)
	@RECEIPTS_LLM_MODE=replay $(PY) -m receipts.evalkit.harness --system baseline --set dev \
	  > /dev/null
	@cmp -s $(BASELINE_TMP) eval/results/dev/baseline/report.json \
	  && echo "two replays are byte-identical" \
	  || { echo "two replays of the same recordings differ (D16)" >&2; \
	       set -o pipefail; \
	       diff $(BASELINE_TMP) eval/results/dev/baseline/report.json | head -20; \
	       rm -f $(BASELINE_TMP); exit 1; }
	@rm -f $(BASELINE_TMP)
