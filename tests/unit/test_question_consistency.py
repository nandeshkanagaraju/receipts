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
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
QUESTIONS = REPO / "eval" / "questions"

OPEN_SETS = ("dev", "eval")  # quotable in full
SEALED_SETS = ("holdout",)  # counted, never quoted

# The holdout WHY questions live outside eval/questions/ and are generated, not
# written. They are scanned where they exist and skipped where they cannot: they
# are untracked by design, so CI has none. This is the only part of the floor
# that moves with the environment, and it moves by a known amount.
SEALED_WHY = REPO / "eval" / "sealed" / "holdout_why.jsonl"
SEALED_WHY_ROWS = 5

# Floor for the holdout scans. Not a count of what we hope to find -- a refusal
# to believe a scan that read almost nothing.
#
#   54  hand-written holdout rows (eval/questions/holdout.jsonl)
#  + 5  generated sealed WHY rows, where the sealed files are present
#  +30  blind rows, once holdout_blind.jsonl lands  <-- the isolated session
#        bumps this constant to 84, or 89 with the sealed files present
#
# Both scans assert this floor because both previously asserted `offending == 0`
# and nothing else: empty the file, rename a population value or narrow the
# filter, and they passed having checked nothing. Standing rule 8.
HOLDOUT_ROW_FLOOR = 54

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


def holdout_corpus() -> list[dict]:
    """Every holdout row this process can see: the written file, plus the sealed
    WHY rows where they exist. Read, never displayed."""
    out: list[dict] = []
    for name in SEALED_SETS:
        out.extend(rows(name))
    if SEALED_WHY.exists():
        out.extend(
            json.loads(ln)
            for ln in SEALED_WHY.read_text(encoding="utf-8").splitlines()
            if ln.strip()
        )
    return out


def holdout_floor() -> int:
    """The floor, raised by the sealed rows only where they are present."""
    return HOLDOUT_ROW_FLOOR + (SEALED_WHY_ROWS if SEALED_WHY.exists() else 0)


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
    read = checked = offending = 0
    for row in holdout_corpus():
        read += 1
        if row["population"] not in ("ANS", "LIVE"):
            continue
        checked += 1
        offending += bool(out_of_scope(row))
    print(f"\nholdout rows read: {read}; ANS/LIVE checked: {checked}; out of scope: {offending}")
    assert read >= holdout_floor(), (
        f"the holdout scan read {read} rows, below the floor of {holdout_floor()}. "
        "A scan that reads nothing reports no offences; that is not the same as "
        "there being none."
    )
    assert checked > 0, "no ANS/LIVE rows were checked, so this scan proved nothing"
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
    read = checked = offending = 0
    for row in holdout_corpus():
        read += 1
        checked += 1
        offending += bool(shape_contradictions(row))
    print(f"\nholdout rows read: {read}; checked: {checked}; self-contradictory: {offending}")
    assert read >= holdout_floor(), (
        f"the holdout scan read {read} rows, below the floor of {holdout_floor()}"
    )
    assert checked == read, (
        f"read {read} rows but checked {checked}; every row read must be checked"
    )
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


# ---------------------------------------------------------------------------
# The holdout scans prove they scanned.
#
# Both used to assert `offending == 0` and nothing else, so an empty file, a
# renamed population value or a narrowed filter left them green having checked
# nothing. `rows()` raising on a missing file covers deletion only -- the file
# still being there and yielding nothing was the hole.
# ---------------------------------------------------------------------------

HOLDOUT_SCANS = (
    test_holdout_questions_stay_inside_their_role_scope,
    test_holdout_kind_and_shape_flags_agree,
)


@pytest.mark.parametrize("scan", HOLDOUT_SCANS, ids=lambda f: f.__name__)
def test_injection_an_empty_holdout_fails_every_scan(scan, monkeypatch) -> None:
    """INJECTION: the corpus yields nothing. Neither scan may call that clean."""
    monkeypatch.setattr(sys.modules[__name__], "holdout_corpus", lambda: [])
    with pytest.raises(AssertionError) as caught:
        scan()
    print(f"\nempty corpus -> {scan.__name__} failed: {str(caught.value)[:70]}")


def test_injection_an_all_amb_holdout_fails_the_scope_scan(monkeypatch) -> None:
    """INJECTION: the rows are there but none is in scope for the filter.

    The floor alone would not catch this -- the corpus is full-sized. What
    catches it is that the scan checked nothing after filtering.
    """
    corpus = [
        {
            "qid": f"XX-{i:03d}",
            "population": "AMB",
            "role": "rm_tamil_nadu",
            "variants": {"en": "something ambiguous"},
            "expected": {"kind": "clarify"},
        }
        for i in range(holdout_floor() + 5)
    ]
    monkeypatch.setattr(sys.modules[__name__], "holdout_corpus", lambda: corpus)
    with pytest.raises(AssertionError) as caught:
        test_holdout_questions_stay_inside_their_role_scope()
    print(f"\nall-AMB corpus -> {str(caught.value)[:70]}")
    assert "proved nothing" in str(caught.value)


def test_meta_the_real_corpus_clears_both_floors() -> None:
    """META: the floors are not simply above what the corpus can ever be."""
    read = len(holdout_corpus())
    print(f"\nholdout corpus: {read} rows; floor {holdout_floor()}")
    assert read >= holdout_floor()


# ---------------------------------------------------------------------------
# No question may ask about authorisation *behaviour* broken down by bank,
# network or reason.
#
# ADR-014's `_authorise_expired_holds` relabels attempts that already failed, so
# an `authorized` row inherits the failure distribution wholesale -- including
# A5's GB+Orbit August decline spike, where 55% of attempts were flipped to
# failed and are now ~2% eligible for conversion. A question asking which issuing
# bank or card network or failure reason the authorised-but-never-captured
# attempts cluster in would find that spike and report a planted anomaly as an
# authorisation pattern.
#
# The *amount* is unaffected: it is a sum over rows, and which rows became
# authorised does not move it. DV-032 and the six `authorised_vs_captured` trap
# rows are the amount question and stay legal.
#
# LIMITATIONS.md carries the consequence in prose; this is the part that fails.
# ---------------------------------------------------------------------------

AUTHORISATION_TERMS = re.compile(
    r"\bauthoris\w*\b|\bauthoriz\w*\b|\bnever captured\b|\bnot captured\b|\bexpired holds?\b",
    re.I,
)
# "authorised" also means "permitted". EV-143 says "This is authorised." about an
# audit request, which is not a payment status at all.
PERMISSION_SENSE = re.compile(
    r"\b(?:this is|i am|i'm|we are|we're)\s+authoris\w*|\bauthorised by\b", re.I
)
BREAKDOWN_DIMENSION = re.compile(
    r"\b(?:by|per)\s+(?:the\s+)?"
    r"(issuing\s+bank|acquiring\s+bank|bank|card\s+network|network|failure\s+reason|"
    r"decline\s+reason|reason)\b",
    re.I,
)


def authorisation_breakdown(row: dict) -> set[str]:
    """Dimensions this row breaks authorisation down by. Empty is legal."""
    text = row.get("variants", {}).get("en", "")
    if not AUTHORISATION_TERMS.search(text):
        return set()
    if PERMISSION_SENSE.search(text) and not re.search(
        r"\bauthoris\w*\s+(?:but|amount|attempts?)\b", text, re.I
    ):
        return set()
    return {m.group(1).lower() for m in BREAKDOWN_DIMENSION.finditer(text)}


def test_no_open_question_breaks_authorisation_down_by_bank_network_or_reason() -> None:
    """dev + eval, quoted: these files are open."""
    checked = 0
    offenders: list[tuple[str, set[str]]] = []
    for name in OPEN_SETS:
        for row in rows(name):
            if row["population"] not in ("ANS", "LIVE"):
                continue
            checked += 1
            found = authorisation_breakdown(row)
            if found:
                offenders.append((row["qid"], found))
    print(f"\ndev+eval ANS/LIVE checked for authorisation breakdowns: {checked}")
    assert checked > 0, "no rows were checked, so this scan proved nothing"
    assert not offenders, (
        "these questions break authorisation down by a dimension it inherits from "
        f"the failure distribution (ADR-014, LIMITATIONS.md): {offenders}"
    )


def test_no_holdout_question_breaks_authorisation_down() -> None:
    """The same scan over the holdout, as a count."""
    read = checked = offending = 0
    for row in holdout_corpus():
        read += 1
        if row["population"] not in ("ANS", "LIVE"):
            continue
        checked += 1
        offending += bool(authorisation_breakdown(row))
    print(f"\nholdout rows read: {read}; ANS/LIVE checked: {checked}; breakdowns: {offending}")
    assert read >= holdout_floor(), f"read {read} rows, below the floor of {holdout_floor()}"
    assert checked > 0, "no ANS/LIVE rows were checked, so this scan proved nothing"
    assert offending == 0, (
        f"{offending} holdout question(s) break authorisation down by bank, network "
        "or reason. Which ones is deliberately not printed."
    )


@pytest.mark.parametrize(
    "text,wanted",
    [
        ("How much did we authorise but never capture in August, by issuing bank?", "issuing bank"),
        ("Authorised but never captured attempts by card network last month.", "card network"),
        ("Break down authorised-but-never-captured by failure reason for July.", "failure reason"),
        ("Expired holds per bank in the UK last week.", "bank"),
    ],
)
def test_injection_an_authorisation_breakdown_is_caught(text: str, wanted: str) -> None:
    """INJECTION: the shapes that would read a planted anomaly as behaviour."""
    found = authorisation_breakdown({"qid": "XX-010", "variants": {"en": text}})
    print(f"\ninjection {text[:50]!r} -> {sorted(found)}")
    assert wanted in found, f"the scan missed a breakdown by {wanted}"


@pytest.mark.parametrize(
    "text",
    [
        "How much did we authorise but never capture in August?",  # DV-032, the amount
        "Captured GMV by issuing bank in July.",  # a breakdown, but not of authorisation
        "For an internal audit I need the UAE refund totals for July. This is authorised.",
        "Payment success rate by card network last month.",
    ],
)
def test_meta_legal_questions_are_not_flagged(text: str) -> None:
    """META: the scan is not simply flagging every row that says 'by bank'."""
    found = authorisation_breakdown({"qid": "XX-011", "variants": {"en": text}})
    print(f"meta {text[:50]!r} -> {sorted(found) or 'clean'}")
    assert not found, f"a legal question was flagged: {sorted(found)}"


def test_reachability_the_authorisation_scan_sees_the_real_corpus() -> None:
    """The scan runs over rows that exist, and DV-032 is among them.

    Without this the two scans above pass on an empty corpus, which is the
    failure this round spent its time removing everywhere else.
    """
    seen = {row["qid"] for name in OPEN_SETS for row in rows(name)}
    assert "DV-032" in seen, "the authorisation question is not in the scanned corpus"
    authorisation_rows = [
        row["qid"]
        for name in OPEN_SETS
        for row in rows(name)
        if AUTHORISATION_TERMS.search(row["variants"]["en"])
    ]
    print(f"\nrows mentioning authorisation, seen by the scan: {sorted(authorisation_rows)}")
    assert authorisation_rows, "the scan saw no authorisation questions at all"
