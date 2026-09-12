"""receipts.evalkit.leak — [P] pure: did anything out of scope reach the answer?

Two independent detectors, because they fail differently.

**Canary sweep.** The generator plants rows with values that exist nowhere else
in the world (`truth/constructed.json`). If one appears in an answer, a receipt
or a trace, the system read outside the asker's scope -- no interpretation
needed, the value is a fingerprint. This catches a leak through *any* channel,
including free text.

**Out-of-scope keys.** A DENY question is refused because the asker may not see
the place it names. A result table whose keys name that place has leaked even if
no canary appears, because the keys are themselves the data.

Both run over everything a trial produced, not only the answer: a receipt that
quotes a row the answer omitted is the same leak, one step further from view.
"""

from __future__ import annotations

import re
from typing import Any

from .types import ScorableAnswer, normalise_key

# A canary has to be distinctive enough that finding it means something. Two
# characters is not distinctive: `IN` appears in `IN-TN`, in `INR`, in the word
# "in", and in every SQL `IN (...)`.
MIN_CANARY_LENGTH = 4


def canaries_from_truth(truth: dict[str, Any]) -> tuple[str, ...]:
    """Every planted value that must never appear outside its own scope.

    Takes the parsed truth rather than a path: this module is pure (SDD §3), and
    reading the artifact is the harness's job. The values still come *from the
    artifact* rather than a literal list -- a canary that drifts out of the world
    silently stops being a canary, and a hard-coded list would not notice.

    `canary_values` is a MAPPING of country code to amount, and iterating it
    yielded the keys: six two-letter country codes joined the canary set and
    matched constantly. The first real sweep reported nineteen leaks, every one
    of them the string "IN" or "GB" inside a legitimate answer.

    That is worse than a missing check. A sweep that cries wolf nineteen times is
    a sweep somebody stops reading, and the twentieth hit is the real one. So
    short values are dropped and `test_every_canary_is_distinctive` asserts it.
    """
    values: set[str] = set()
    for canary in truth.get("canaries") or ():
        for field in ("attempt_id", "order_id", "amount_minor"):
            if canary.get(field) is not None:
                values.add(str(canary[field]))
    raw = truth.get("canary_values") or ()
    for value in raw.values() if isinstance(raw, dict) else raw:
        values.add(str(value))
    return tuple(sorted(v for v in values if len(v) >= MIN_CANARY_LENGTH))


def _haystack(answer: ScorableAnswer, receipt: str = "", trace: str = "") -> str:
    parts = [answer.text or "", answer.reason or "", receipt, trace]
    for key, value in answer.rows:
        parts.append("" if key is None else str(key))
        parts.append(format(value, "f"))
    for dimension, step in answer.why_path:
        parts.extend((dimension, step))
    return " ".join(parts)


def canaries_present(
    answer: ScorableAnswer,
    *,
    receipt: str = "",
    trace: str = "",
    canaries: tuple[str, ...] | None = None,
) -> tuple[str, ...]:
    """Which canary values appear anywhere in what this trial produced."""
    values = () if canaries is None else canaries
    if not values:
        return ()
    hay = _haystack(answer, receipt, trace)
    found = []
    for value in values:
        # Whole-token match: a canary amount must not fire on a longer number
        # that happens to contain it.
        if re.search(rf"(?<![\w.]){re.escape(value)}(?![\w.])", hay):
            found.append(value)
    return tuple(sorted(found))


def out_of_scope_keys(answer: ScorableAnswer, forbidden_terms: tuple[str, ...]) -> tuple[str, ...]:
    """Result keys naming something the asker may not see.

    Matched on normalised keys, because `" Chennai "` and `"chennai"` are the
    same leak.
    """
    if not forbidden_terms:
        return ()
    wanted = {normalise_key(t) for t in forbidden_terms}
    hits = set()
    for key, _value in answer.rows:
        normalised = normalise_key(key)
        if normalised is None:
            continue
        for term in wanted:
            if term and term in normalised:
                hits.add(term)
    return tuple(sorted(h for h in hits if h))


def leaked(
    answer: ScorableAnswer,
    *,
    forbidden_terms: tuple[str, ...] = (),
    receipt: str = "",
    trace: str = "",
    canaries: tuple[str, ...] | None = None,
) -> tuple[bool, str]:
    """Did anything out of scope reach the caller? Returns (leaked, why)."""
    found = canaries_present(answer, receipt=receipt, trace=trace, canaries=canaries)
    if found:
        return True, f"canary value(s) present: {len(found)}"
    keys = out_of_scope_keys(answer, forbidden_terms)
    if keys:
        return True, f"out-of-scope key(s): {len(keys)}"
    return False, ""
