"""A failing holdout scan says how many, never which.

The holdout scans in `tests/unit/test_question_consistency.py` read the holdout
and report counts. Today they say nothing more, and that holds by reading the
source — nothing enforces it. The enforcement matters precisely because of who
sees the failure: these scans fail for the isolated session and for nobody else,
and that session is the only one allowed to look. A qid or a question sentence in
an assertion message would put holdout content into a transcript, a CI log and a
report, on the one path where the failure is least likely to be noticed as a
leak.

So: run both scans against a synthetic holdout that violates both rules, capture
stdout *and* the AssertionError text, and assert that neither carries a qid, a
question sentence, or a place term.

Same shape as `test_sealed_values_never_printed.py`, and for the same reason: a
test may read sealed or holdout material, and may never say what it read.
"""

from __future__ import annotations

import io
import re
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tests" / "unit"))
import test_question_consistency as scans  # noqa: E402

# Deliberately loud: if any of this reaches the output, the test has found a leak.
PLANTED_QID = "HO-999"
PLANTED_SENTENCE = "Weekly duplicate captures in Bengaluru for the last 8 weeks."
PLANTED_PLACE = "bengaluru"


def violating_corpus() -> list[dict]:
    """A full-sized corpus that breaks both rules at once."""
    corpus = []
    for i in range(scans.holdout_floor() + 5):
        corpus.append(
            {
                "qid": PLANTED_QID if i == 0 else f"HO-{i:03d}",
                "population": "ANS",
                "role": "store_ops_uk",  # a UK role...
                "variants": {"en": PLANTED_SENTENCE},  # ...asking about India
                # scalar + compare: the same self-contradiction as EV-115.
                "expected": {"kind": "scalar", "compare": True},
            }
        )
    return corpus


def run_scan(scan, monkeypatch) -> tuple[str, str]:
    """Return (stdout, assertion text) for a scan that must fail."""
    monkeypatch.setattr(scans, "holdout_corpus", violating_corpus)
    buffer = io.StringIO()
    with redirect_stdout(buffer), pytest.raises(AssertionError) as caught:
        scan()
    return buffer.getvalue(), str(caught.value)


@pytest.mark.parametrize("scan", scans.HOLDOUT_SCANS, ids=lambda f: f.__name__)
def test_a_failing_holdout_scan_names_nothing(scan, monkeypatch) -> None:
    out, message = run_scan(scan, monkeypatch)
    blob = f"{out}\n{message}"

    # Precondition: the scan really did fail, or this proves nothing.
    assert message.strip(), f"{scan.__name__} failed with an empty message"

    qids = re.findall(r"\b(?:DV|EV|HO)-\d{3}\b", blob)
    assert not qids, f"{scan.__name__} leaked qid(s): {sorted(set(qids))}"
    assert PLANTED_SENTENCE not in blob, f"{scan.__name__} leaked a question sentence"
    assert "duplicate captures" not in blob.casefold(), f"{scan.__name__} leaked part of a question"

    lowered = blob.casefold()
    leaked_places = {p for p in scans.PLACE_TERMS if p in lowered}
    assert not leaked_places, f"{scan.__name__} leaked place term(s): {sorted(leaked_places)}"

    print(f"\n{scan.__name__}: failed in {len(message)} chars, named nothing")


@pytest.mark.parametrize("scan", scans.HOLDOUT_SCANS, ids=lambda f: f.__name__)
def test_the_failure_still_says_how_many(scan, monkeypatch) -> None:
    """Silent is not the same as useless: a count must survive the redaction."""
    out, message = run_scan(scan, monkeypatch)
    assert re.search(r"\d", out + message), (
        f"{scan.__name__} reported neither a qid nor a count, which leaves the "
        "isolated session nothing to act on"
    )


def test_meta_the_probe_would_catch_a_leak(monkeypatch) -> None:
    """Guard off: a scan that *does* name a row is caught by the same checks.

    Without this the tests above pass for a scan that emits nothing at all, and
    a silent guard is indistinguishable from a working one.
    """
    monkeypatch.setattr(scans, "holdout_corpus", violating_corpus)

    def leaky_scan() -> None:
        rows = scans.holdout_corpus()
        offenders = [r["qid"] for r in rows if scans.out_of_scope(r)]
        print(f"out of scope: {offenders[:3]}")
        raise AssertionError(f"{offenders[0]} asks outside its scope: {rows[0]['variants']['en']}")

    out, message = run_scan(leaky_scan, monkeypatch)
    blob = f"{out}\n{message}"
    assert re.findall(r"\b(?:DV|EV|HO)-\d{3}\b", blob), "the probe found no qid in a leaky scan"
    assert PLANTED_SENTENCE in blob, "the probe found no question text in a leaky scan"
    lowered = blob.casefold()
    assert any(p in lowered for p in scans.PLACE_TERMS), "the probe found no place term"
    print(f"\nmeta: a leaky scan is caught on all three checks ({len(blob)} chars)")
