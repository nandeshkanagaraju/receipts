"""A question row must not contradict itself, and must stay inside its role's scope.

Two checks, both added after M3 found one offender of each kind by hand while
writing reference SQL. Finding them by hand is not a control; this file is.

**Scope (ruling 2).** `eval/questions/README.md` authoring rule 5 and D7 together
say that scope comes from the auth context and that a manager asking outside
their own scope must be **denied**. So an ANS or LIVE question naming a place
outside its role's scope is mis-populated: it is a DENY question wearing an ANS
label, and scoring it as ANS marks a correctly-scoped system wrong for refusing.
EV-057 was exactly this — `store_ops_uk` asking about India — and is now
`global_finance`.

**Self-consistency (ruling 3).** `expected.kind` and the shape flags are two
statements about the same thing and must agree. EV-115 declared `kind: scalar`
alongside `top_k: 10` for a question reading "net revenue **by acquiring bank**",
which is not a scalar quantity. A scorer dispatching on `kind` would have
compared one number against ten rows.

**The holdout is checked and never quoted.** Both scans run over
`holdout.jsonl` too — a rule that stops at the set it is easy to look at is not
a rule — but they print **counts only**: no qid, no question text, no place name.
The file is read by this process and never reaches a transcript, which is the
same posture `evalkit.scoring` has toward `eval/sealed/`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
QUESTIONS = REPO / "eval" / "questions"

OPEN_SETS = ("dev", "eval")  # quotable in full
SEALED_SETS = ("holdout",)  # counted, never quoted

# Which places each role may be asked about. `global_finance` has no ceiling.
# Terms are matched as whole words against the English variant, case-folded.
ROLE_SCOPE: dict[str, set[str]] = {
    "rm_tamil_nadu": {
        "tamil nadu",
        "chennai",
        "coimbatore",
        "madurai",
        "trichy",
        "salem",
        "velachery",
        "tambaram",
        "perambur",
        "nungambakkam",
        "ambattur",
        "porur",
    },
    "store_ops_uk": {
        "uk",
        "united kingdom",
        "britain",
        "london",
        "birmingham",
        "manchester",
        "liverpool",
        "leicester",
        "midlands",
        "north west",
        "pounds",
        "sterling",
    },
}

# Every place term a question might name, and the role scopes it belongs to.
# A term absent from a role's set is outside that role's scope.
PLACE_TERMS: set[str] = (
    ROLE_SCOPE["rm_tamil_nadu"]
    | ROLE_SCOPE["store_ops_uk"]
    | {
        "india",
        "indian",
        "singapore",
        "malaysia",
        "uae",
        "dubai",
        "abu dhabi",
        "emirates",
        "us",
        "usa",
        "united states",
        "america",
        "delhi",
        "mumbai",
        "bangalore",
        "bengaluru",
        "hyderabad",
        "kolkata",
        "gujarat",
        "karnataka",
        "maharashtra",
        "telangana",
        "west bengal",
        "penang",
        "kuala lumpur",
        "california",
        "new york",
        "texas",
        "rupees",
        "dirhams",
        "ringgit",
        "singapore dollars",
    }
)

# Currency words name a country as surely as a city does: "in rupees" from a UK
# role is the same leak as "in India". Mapped to the scope that may use them.
CURRENCY_SCOPE = {
    "rupees": "rm_tamil_nadu",
    "pounds": "store_ops_uk",
    "sterling": "store_ops_uk",
}


def rows(name: str) -> list[dict]:
    path = QUESTIONS / f"{name}.jsonl"
    if not path.exists():
        raise AssertionError(f"missing question file {path} — this scan proves nothing without it")
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def places_named(text: str) -> set[str]:
    """Place terms appearing as whole words in the English variant."""
    lowered = text.casefold()
    return {t for t in PLACE_TERMS if re.search(rf"(?<![\w-]){re.escape(t)}(?![\w-])", lowered)}


def out_of_scope(row: dict) -> set[str]:
    """Places this row names that its role may not be asked about.

    `global_finance` sees everything, so it can never offend. Only ANS and LIVE
    are checked: a DENY question naming somewhere out of scope is the point of
    the question, and an AMB or UNA one is not answered from data at all.
    """
    if row["population"] not in ("ANS", "LIVE"):
        return set()
    allowed = ROLE_SCOPE.get(row["role"])
    if allowed is None:
        return set()
    named = places_named(row["variants"]["en"])
    offending = named - allowed
    # A currency word only offends if it belongs to a *different* role's scope.
    return {t for t in offending if t not in CURRENCY_SCOPE or CURRENCY_SCOPE[t] != row["role"]}


# --------------------------------------------------------------------------- #
# Ruling 2 — scope
# --------------------------------------------------------------------------- #
def test_answerable_questions_stay_inside_their_role_scope() -> None:
    """dev and eval, quoted in full because nothing here is sealed."""
    offenders: list[str] = []
    checked = 0
    for name in OPEN_SETS:
        for row in rows(name):
            if row["population"] not in ("ANS", "LIVE"):
                continue
            checked += 1
            bad = out_of_scope(row)
            if bad:
                offenders.append(
                    f"{row['qid']} ({row['role']}) names {sorted(bad)}: {row['variants']['en']}"
                )
    print(f"\n{checked} ANS/LIVE questions in dev+eval checked against their role's scope")
    for o in offenders:
        print(f"  OUT OF SCOPE {o}")
    assert not offenders, (
        f"{len(offenders)} ANS/LIVE question(s) ask outside the asker's scope. Under D7 and "
        "eval/questions/README.md rule 5 these are DENY questions, and scoring them as ANS "
        "marks a correctly-scoped system wrong for refusing:\n  " + "\n  ".join(offenders)
    )


def test_holdout_questions_stay_inside_their_role_scope() -> None:
    """The same scan over the holdout, reported as a COUNT and nothing else.

    No qid, no question, no place name. The file is read by this process and
    never displayed — the posture `evalkit.scoring` has toward `eval/sealed/`.
    """
    checked = offending = 0
    for name in SEALED_SETS:
        for row in rows(name):
            if row["population"] not in ("ANS", "LIVE"):
                continue
            checked += 1
            offending += bool(out_of_scope(row))
    print(f"\nholdout ANS/LIVE checked: {checked}; out of scope: {offending}")
    assert offending == 0, (
        f"{offending} holdout ANS/LIVE question(s) ask outside the asker's scope. "
        "Which ones is deliberately not printed; run the scan in the isolated session "
        "(docs/ISOLATED_REFERENCE_RUN.md) to see them."
    )


def test_injection_an_out_of_scope_question_is_caught() -> None:
    """INJECTION: EV-057 as it was — a UK role asking about India."""
    row = {
        "qid": "XX-001",
        "population": "ANS",
        "role": "store_ops_uk",
        "variants": {"en": "Weekly duplicate captures in India for the last 8 weeks."},
    }
    found = out_of_scope(row)
    print(f"\ninjection (store_ops_uk asking about India) -> {sorted(found)}")
    assert "india" in found, "the scan missed a plainly out-of-scope question"


def test_injection_a_currency_word_counts_as_a_place() -> None:
    """INJECTION: "in rupees" from a UK role names India without saying India."""
    row = {
        "qid": "XX-002",
        "population": "ANS",
        "role": "store_ops_uk",
        "variants": {"en": "What did we take last month, in rupees?"},
    }
    print(f"\ninjection (store_ops_uk asking in rupees) -> {sorted(out_of_scope(row))}")
    assert "rupees" in out_of_scope(row)


def test_meta_the_same_question_from_global_finance_is_fine() -> None:
    """META: the refusal comes from the ROLE, not from the words.

    Without this the scan could be rejecting the sentence rather than the
    mismatch, and EV-057's fix — changing the role, not the question — would not
    be verified by anything.
    """
    row = {
        "qid": "XX-001",
        "population": "ANS",
        "role": "global_finance",
        "variants": {"en": "Weekly duplicate captures in India for the last 8 weeks."},
    }
    print(f"\nmeta (global_finance, same sentence) -> {sorted(out_of_scope(row))}")
    assert not out_of_scope(row), "global_finance was refused a question it may ask"


def test_meta_a_deny_question_may_name_anywhere() -> None:
    """META: DENY questions are out of scope on purpose; that is the population."""
    row = {
        "qid": "XX-003",
        "population": "DENY",
        "role": "rm_tamil_nadu",
        "variants": {"en": "How much did we take in Dubai last month?"},
    }
    assert not out_of_scope(row), "a DENY question was flagged for being out of scope"
    print("\nmeta: a DENY question naming Dubai is not an offender")


def test_ev_057_is_answerable_by_its_role_now() -> None:
    """The specific fix, asserted against the file rather than assumed."""
    row = next(r for r in rows("eval") if r["qid"] == "EV-057")
    print(f"\nEV-057 role={row['role']} population={row['population']}")
    assert row["role"] == "global_finance"
    assert row["population"] == "ANS"
    assert not out_of_scope(row)


# --------------------------------------------------------------------------- #
# Ruling 3 — a row must not contradict itself
# --------------------------------------------------------------------------- #
def shape_contradictions(row: dict) -> list[str]:
    """Ways `expected.kind` and the shape flags can disagree (ADR-009)."""
    e = row["expected"]
    kind = e.get("kind")
    problems: list[str] = []
    if kind == "scalar":
        for flag in ("top_k", "series", "compare"):
            if e.get(flag):
                problems.append(f"kind=scalar with {flag}={e[flag]!r}")
    if e.get("series") and "top_k" in e:
        problems.append(f"series with top_k={e['top_k']!r}")
    return problems


def test_kind_and_shape_flags_agree() -> None:
    """dev and eval. `series` carries no top_k: matching a series by RANK would
    pass a result whose days were right but misordered, which for a series is the
    entire answer (ADR-009)."""
    offenders: list[str] = []
    checked = 0
    for name in OPEN_SETS:
        for row in rows(name):
            checked += 1
            for problem in shape_contradictions(row):
                offenders.append(f"{row['qid']}: {problem}")
    print(f"\n{checked} questions in dev+eval checked for kind/shape agreement")
    for o in offenders:
        print(f"  CONTRADICTION {o}")
    assert not offenders, "rows that contradict themselves:\n  " + "\n  ".join(offenders)


def test_holdout_kind_and_shape_flags_agree() -> None:
    """The same check over the holdout, as a count."""
    checked = offending = 0
    for name in SEALED_SETS:
        for row in rows(name):
            checked += 1
            offending += bool(shape_contradictions(row))
    print(f"\nholdout questions checked: {checked}; self-contradictory: {offending}")
    assert offending == 0, f"{offending} holdout row(s) contradict themselves (qids not printed)"


@pytest.mark.parametrize(
    "expected,wanted",
    [
        ({"kind": "scalar", "top_k": 10}, "top_k"),
        ({"kind": "scalar", "series": True}, "series"),
        ({"kind": "scalar", "compare": True}, "compare"),
        ({"kind": "table", "series": True, "top_k": 5}, "series with top_k"),
    ],
)
def test_injection_self_contradictory_rows_are_caught(expected: dict, wanted: str) -> None:
    """INJECTION: the four ways a row can disagree with itself, EV-115 first."""
    problems = shape_contradictions({"qid": "XX-004", "expected": expected})
    print(f"\ninjection {expected} -> {problems}")
    assert any(wanted in p for p in problems), f"{expected} was not caught"


def test_meta_a_consistent_row_passes() -> None:
    """META: the scan is not simply refusing every row it sees."""
    for expected in (
        {"kind": "scalar"},
        {"kind": "table", "top_k": 10},
        {"kind": "table", "series": True},
        {"kind": "scalar", "compare": False},
    ):
        assert not shape_contradictions({"qid": "XX-005", "expected": expected}), expected
    print("\nmeta: consistent rows pass the identical scan")


def test_ev_115_declares_a_table_now() -> None:
    row = next(r for r in rows("eval") if r["qid"] == "EV-115")
    print(f"\nEV-115 kind={row['expected']['kind']} top_k={row['expected'].get('top_k')}")
    assert row["expected"]["kind"] == "table"
    assert row["expected"]["top_k"] == 10
    assert not shape_contradictions(row)
