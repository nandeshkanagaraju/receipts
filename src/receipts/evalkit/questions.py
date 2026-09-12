"""receipts.evalkit.questions — [IO] load question files and expand them to trials.

A *question* is a row. A *trial* is a question in one language under one role
(SDD §8), and trials are what gets scored: the same question asked in Tamil and
in English are two measurements, and pooling them would hide exactly the
asymmetry the language columns exist to show.

Only variants that are actually present expand. A row whose `ta-Latn` is
`pending` contributes no Tanglish trial rather than an empty one — an empty
trial would be scored, and scored as something.

The holdout set is three files: the hand-written rows, the blind rows, and the
generated sealed WHY rows. `load` takes them together, because every consumer
wants the holdout *set* rather than one of its authorships.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .types import POPULATIONS, Population, Trial

REPO = Path(__file__).resolve().parents[3]
QUESTIONS = REPO / "eval" / "questions"
SEALED_WHY = REPO / "eval" / "sealed" / "holdout_why.jsonl"

# Which files make up each set. The holdout is the only one with more than one
# author, and the sealed file is absent wherever it should be (CI, any clone).
SET_FILES: dict[str, tuple[Path, ...]] = {
    "dev": (QUESTIONS / "dev.jsonl",),
    "eval": (QUESTIONS / "eval.jsonl",),
    "holdout": (QUESTIONS / "holdout.jsonl", QUESTIONS / "holdout_blind.jsonl", SEALED_WHY),
}

LANGUAGES: tuple[str, ...] = ("en", "ta", "hi", "ta-Latn")


class QuestionError(ValueError):
    """A question file that cannot be trusted to measure anything."""


def _rows(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def load(set_name: str, *, required: bool = True) -> list[dict[str, Any]]:
    """Every row of a set, from every file that makes it up.

    A missing *optional* file is silently empty -- the sealed WHY questions are
    untracked and absent everywhere but one machine. A missing required file
    raises: a set that loaded nothing would score 0 of 0 and report success.
    """
    if set_name not in SET_FILES:
        raise QuestionError(f"unknown set {set_name!r}; known: {sorted(SET_FILES)}")
    rows: list[dict[str, Any]] = []
    for path in SET_FILES[set_name]:
        if not path.exists():
            if required and path.parent == QUESTIONS:
                raise QuestionError(f"{path} is missing; {set_name} cannot be scored")
            continue
        rows.extend(_rows(path))
    if required and not rows:
        raise QuestionError(f"{set_name} loaded no questions at all")
    return rows


def validate(rows: list[dict[str, Any]], set_name: str) -> None:
    """Everything the scorer relies on, checked once rather than per trial."""
    seen: set[str] = set()
    for row in rows:
        qid = row.get("qid")
        if not qid:
            raise QuestionError(f"{set_name}: a row has no qid")
        if qid in seen:
            raise QuestionError(f"{set_name}: duplicate qid {qid}")
        seen.add(qid)
        population = row.get("population")
        if population not in POPULATIONS:
            raise QuestionError(f"{qid}: unknown population {population!r}")
        if not row.get("role"):
            raise QuestionError(f"{qid}: no role, so scope cannot be scored")
        variants = row.get("variants") or {}
        if not (variants.get("en") or "").strip():
            raise QuestionError(f"{qid}: no English variant")
        for language in variants:
            if language not in LANGUAGES:
                raise QuestionError(f"{qid}: unknown language {language!r}")


def expand(rows: list[dict[str, Any]], set_name: str) -> list[Trial]:
    """One trial per (question, present variant, role).

    Sorted by an explicit key (D4) so two runs produce the same order and the
    report can be compared byte for byte (D16).
    """
    trials: list[Trial] = []
    for row in rows:
        population: Population = row["population"]
        for language in LANGUAGES:
            text = (row.get("variants", {}).get(language) or "").strip()
            if not text:
                continue
            trials.append(
                Trial(
                    qid=row["qid"],
                    set_name=set_name,
                    population=population,
                    language=language,
                    role=row["role"],
                    text=text,
                )
            )
    return sorted(trials, key=lambda t: (t.qid, t.language, t.role))


def trials(set_name: str, *, required: bool = True) -> list[Trial]:
    rows = load(set_name, required=required)
    validate(rows, set_name)
    return expand(rows, set_name)


def by_qid(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {row["qid"]: row for row in rows}
