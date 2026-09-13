"""Aliases for the values the data holds, and where each one came from.

SDD §9.1 rule 3 asks that filter values match "with case-insensitive and
trilingual-synonym matching". Until now only `country` had aliases and only in
English, which cost 18 of the 62 dev over-abstentions: the planner passes a place
name through in the script the question was asked in -- `चेन्नई`, `சென்னை`,
`தமிழ்நாடு` -- and the value index holds `Chennai` and `Tamil Nadu`.

There are two sources here and they are kept apart on purpose, because one is
derived and the other is written down:

**MECHANICAL** (`mechanical_synonyms`) is computed from the value index itself.
The data stores enum values as snake_case tokens, so `pay_later` implies "pay
later" and "paylater" the way a plural implies its singular. Nothing is invented:
every alias is a transformation of a string the data already holds, and if a new
payment method appears the aliases appear with it.

**CURATED** (`semantic/value_synonyms.yaml`) is the trilingual layer, and it is
written by hand because nothing in the warehouse knows that Chennai is சென்னை --
there is no localised name column, and the glossary defines metrics rather than
naming places. Its provenance rule is the part that matters:

  Every canonical value in that file must exist in the data's value index, and
  the file must cover EVERY value of the dimensions it covers, not the ones that
  happen to fail. `test_curated_synonyms_cover_every_value` enforces both. A file
  that listed Chennai and Tamil Nadu and stopped would be tuning against the eval
  set wearing a data file's clothes.

Neither source may be built from `eval/questions`. `test_no_synonym_came_from_the_questions`
asserts that the curated file contains no string that appears in a question
variant and nowhere in the data.
"""

from __future__ import annotations

import unicodedata
from pathlib import Path
from typing import Any

import yaml

CURATED = Path(__file__).resolve().parent.parent.parent.parent / "semantic" / "value_synonyms.yaml"


def fold_value(value: str) -> str:
    """Casefold, collapse whitespace, and normalise to NFC.

    NFC matters for the Indic scripts: `சென்னை` typed with a precomposed vowel
    sign and the same word typed with a combining one are different strings and
    the same word. The language layer already learned this in M8.
    """
    return " ".join(unicodedata.normalize("NFC", value).casefold().split())


def mechanical_synonyms(values: tuple[str, ...]) -> dict[str, str]:
    """Aliases implied by the shape of the values themselves.

    `pay_later` -> "pay later", "paylater". `in_store` -> "in store", "instore".
    Nothing here is a translation or a judgement; it is the same token with its
    separators spelled differently, which is the difference between a synonym and
    a guess.
    """
    out: dict[str, str] = {}
    for value in values:
        if "_" not in value and "-" not in value:
            continue
        spaced = value.replace("_", " ").replace("-", " ")
        for alias in (spaced, spaced.replace(" ", "")):
            key = fold_value(alias)
            if key and key != fold_value(value):
                out.setdefault(key, value)
    return out


def load_curated(path: Path = CURATED) -> dict[str, dict[str, str]]:
    """The trilingual file, as `{dimension: {alias_folded: canonical}}`.

    Absent file is not an error: the layer loads without it and every value still
    resolves by exact match. A malformed one is, because a synonym file that half
    parses resolves half the names and refuses the rest for no visible reason.
    """
    if not path.exists():
        return {}
    raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError(f"{path.name}: expected a mapping of dimension -> values")
    out: dict[str, dict[str, str]] = {}
    for dimension, entries in raw.items():
        if not isinstance(entries, dict):
            raise ValueError(f"{path.name}: {dimension!r} must map canonical values to aliases")
        table: dict[str, str] = {}
        for canonical, aliases in entries.items():
            if isinstance(aliases, str):
                aliases = [aliases]
            if not isinstance(aliases, list):
                raise ValueError(f"{path.name}: aliases for {canonical!r} must be a list")
            for alias in aliases:
                table[fold_value(str(alias))] = str(canonical)
        out[str(dimension)] = table
    return out


def synonyms_for(
    dimension: str,
    values: tuple[str, ...],
    declared: dict[str, str],
    curated: dict[str, dict[str, str]],
) -> dict[str, str]:
    """Everything that resolves for one dimension, in precedence order.

    Mechanical first, then the dimension YAML's own `value_synonyms`, then the
    curated trilingual file -- later sources win, so a hand-written alias can
    correct a derived one and never the reverse.
    """
    out = mechanical_synonyms(values)
    out.update({fold_value(k): v for k, v in declared.items()})
    out.update(curated.get(dimension, {}))
    return out
