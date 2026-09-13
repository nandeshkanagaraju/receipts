"""The asker's choice must reach the plan (M17.1).

The sixth instance of the pattern in `docs/M2_NOTES.md` §11: a value computed
correctly by one component and discarded by the next.

`ClarifyOption` carries a concrete plan patch and an `apply` method, and its own
docstring says why prose would not do -- "an option that was only prose would
have to be re-planned after they answered, which is a second chance to pick
something nobody chose." `apply` was called by one unit test and by nothing in
the product. `POST /api/v1/clarify` re-asked `option_id` as though it were the
question text and marked the ambiguity answered, so the DEFAULT won: both
options of a two-option clarification returned the same metric, the same number,
`VERIFIED`, with a receipt.

That is the failure mode this project exists to prevent -- not an error, a
plausible wrong answer with a receipt vouching for it.

The tests below name the metric each choice must produce. "The two answers
differ" would pass if choice 1 returned choice 2's metric.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from receipts.agent.gate import ClarifyOption
from receipts.domain.types import ClarifyChoice

REPO = Path(__file__).resolve().parents[2]

# The clarification this file turns on. Both readings are real metrics in the
# layer, and they return different numbers -- which is the only reason the
# question is ambiguous in the first place.
QUESTION = "What was our revenue last month?"
ROLE = "rm_tamil_nadu"


@pytest.fixture(scope="module")
def client():
    """The real app in replay mode. No network (D9)."""
    import os

    os.environ.setdefault("RECEIPTS_LLM_MODE", "replay")
    from fastapi.testclient import TestClient

    from receipts.api.app import create_app

    return TestClient(create_app())


def _token(client) -> dict[str, str]:
    token = client.post("/api/v1/auth/demo-login", json={"role": ROLE}).json()["token"]
    return {"authorization": f"Bearer {token}"}


def _clarification(client, headers) -> dict:
    body = client.post(
        "/api/v1/ask?stream=false",
        json={"question": QUESTION, "session_id": "clarify-test"},
        headers=headers,
    ).json()
    assert body["status"] == "CLARIFY", f"precondition: {QUESTION!r} must clarify, got {body}"
    return body["clarification"]


# --------------------------------------------------------------------------- #
# The injection: each choice must produce ITS OWN metric, named.
# --------------------------------------------------------------------------- #
def test_each_clarify_choice_returns_the_metric_it_names(client) -> None:
    headers = _token(client)
    clarification = _clarification(client, headers)
    options = clarification["options"]
    assert len(options) >= 2, options

    seen: list[tuple[str, str, object]] = []
    for option in options:
        wanted = json.loads(option["patch_json"]).get("name")
        if not wanted:
            continue
        answer = client.post(
            "/api/v1/clarify?stream=false",
            json={
                "session_id": "clarify-test",
                "clarification_id": clarification["clarification_id"],
                "option_id": option["option_id"],
                "question": QUESTION,
            },
            headers=headers,
        ).json()
        got = (answer.get("receipt") or {}).get("metric")
        value = answer["table"]["rows"][0][0] if answer.get("table") else None
        print(f"\nchose {wanted!r} -> status={answer.get('status')} metric={got} value={value}")
        seen.append((wanted, got, value))
        # Named, not merely different: "they differ" passes when they are swapped.
        assert got == wanted, f"chose {wanted!r} and the receipt says the metric was {got!r}"

    assert len(seen) >= 2, f"needed two patching options, got {seen}"
    values = [value for _, _, value in seen]
    assert len(set(map(str, values))) == len(values), (
        f"two different metrics returned the same number, so nothing was applied: {seen}"
    )


def test_the_second_choice_is_gmv_captured_and_not_the_default(client) -> None:
    """The exact case that was broken, pinned by name and by number.

    Before M17.1 this returned net_revenue -- the first option -- because the
    route re-asked the question and let the default win.
    """
    headers = _token(client)
    clarification = _clarification(client, headers)
    second = next(
        o
        for o in clarification["options"]
        if json.loads(o["patch_json"]).get("name") == "gmv_captured"
    )
    answer = client.post(
        "/api/v1/clarify?stream=false",
        json={
            "session_id": "clarify-test",
            "clarification_id": clarification["clarification_id"],
            "option_id": second["option_id"],
            "question": QUESTION,
        },
        headers=headers,
    ).json()
    print(f"\nsecond choice -> {answer['receipt']['metric']} = {answer['table']['rows'][0][0]}")
    assert answer["status"] == "VERIFIED"
    assert answer["receipt"]["metric"] == "gmv_captured"


# --------------------------------------------------------------------------- #
# The meta-test: the injection above must FAIL with the fix off.
# --------------------------------------------------------------------------- #
def test_the_old_route_behaviour_lets_the_default_win(client) -> None:
    """With the choice discarded, both options give the same metric.

    This reproduces the pre-M17.1 route exactly -- re-ask the question with the
    ambiguity marked answered and no `chosen` -- and asserts the bug is there.
    If this ever stops reproducing, the test above has stopped proving anything
    and this file needs rewriting rather than deleting.
    """
    from receipts.agent.orchestrator import answer as run_answer
    from receipts.agent.session import Session
    from receipts.api.deps import build_runtime

    state = build_runtime()
    scope = state.scope(ROLE)
    first = run_answer(
        QUESTION,
        Session(session_id="meta", role=ROLE),
        scope,
        state.as_of,
        state.deps,
    )[0]
    assert first.status.value == "CLARIFY"
    key = first.clarification.clarification_id

    # The old route: ambiguity marked answered, choice thrown away.
    result, _ = run_answer(
        QUESTION,
        Session(session_id="meta", role=ROLE, answered_clarifications=(key,)),
        scope,
        state.as_of,
        state.deps,
    )
    offered = [json.loads(o.patch_json).get("name") for o in first.clarification.options]
    print(f"\noptions offered: {offered}")
    print(f"old behaviour returns: {result.receipt.metric if result.receipt else None}")
    assert result.receipt is not None, "precondition: the old path still answers"
    # Exactly one of the offered metrics comes back no matter which was chosen.
    assert result.receipt.metric in offered
    assert offered.count(result.receipt.metric) == 1
    assert result.receipt.metric == "net_revenue", (
        "the meta-test pins the DEFAULT that used to win; if this changed, the "
        "injection above is no longer testing what it claims"
    )


# --------------------------------------------------------------------------- #
# The class guard: no field of a ClarifyChoice may be decoration.
# --------------------------------------------------------------------------- #
def _attribute_reads(path: Path) -> set[str]:
    """Attribute names read in a module. AST, not text: a comment is not a read."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}


def test_every_clarify_choice_field_is_consumed_not_decoration() -> None:
    """Each field must change the identity, or be read by name where it is used.

    The bug this guards: `patch_json` was published on every clarification and
    the server never looked at it again. A field that neither identifies the
    choice nor is read is a field that can drift from what it describes without
    anything failing -- which is how the option a user picked stopped meaning
    anything while the API went on offering it.
    """
    consumers = (
        REPO / "src" / "receipts" / "agent" / "orchestrator.py",
        REPO / "src" / "receipts" / "api" / "app.py",
        REPO / "src" / "receipts" / "agent" / "gate.py",
    )
    read_by_name: set[str] = set()
    for path in consumers:
        read_by_name |= _attribute_reads(path)

    base = ClarifyOption(label="a label", patch={"name": "net_revenue"})
    baseline = base.option_id("k")
    # One mutation per field of the underlying option.
    mutations = {
        "label": ClarifyOption(label="a different label", patch={"name": "net_revenue"}),
        "patch_json": ClarifyOption(label="a label", patch={"name": "gmv_captured"}),
    }

    unconsumed: list[str] = []
    for field in ClarifyChoice.model_fields:
        identifies = field in mutations and mutations[field].option_id("k") != baseline
        named = field in read_by_name
        print(f"  {field:<12} identifies={identifies!s:<5} read_by_name={named}")
        if not (identifies or named):
            unconsumed.append(field)

    assert not unconsumed, (
        f"{unconsumed} are published on every ClarifyChoice and nothing consumes them; "
        "this is the shape of the defect this file exists for"
    )


def test_the_class_guard_fires_when_a_field_is_decoration() -> None:
    """Fault injection for the guard above: an unconsumed field must be caught."""

    class Decorated(ClarifyChoice):
        hint: str = ""

    base = ClarifyOption(label="a label", patch={"name": "net_revenue"})
    read_by_name = _attribute_reads(REPO / "src" / "receipts" / "agent" / "orchestrator.py")
    mutations = {
        "label": ClarifyOption(label="other", patch={"name": "net_revenue"}),
        "patch_json": ClarifyOption(label="a label", patch={"name": "gmv_captured"}),
    }
    unconsumed = [
        field
        for field in Decorated.model_fields
        if not (
            (field in mutations and mutations[field].option_id("k") != base.option_id("k"))
            or field in read_by_name
        )
    ]
    print(f"\ninjected field caught: {unconsumed}")
    assert unconsumed == ["hint"], unconsumed


# --------------------------------------------------------------------------- #
# Identity and refusal.
# --------------------------------------------------------------------------- #
def test_option_ids_are_deterministic_and_distinct() -> None:
    """D3 and D5: the same choice is the same id on every run, in any order."""
    a = ClarifyOption(label="net_revenue: x", patch={"name": "net_revenue"})
    b = ClarifyOption(label="gmv_captured: y", patch={"name": "gmv_captured"})
    print(f"\na={a.option_id('k')} b={b.option_id('k')}")
    assert a.option_id("k") == a.option_id("k")
    assert a.option_id("k") != b.option_id("k")
    # The ambiguity key is part of the identity: the same reading under a
    # different question is a different choice.
    assert a.option_id("k") != a.option_id("other")
    assert len(a.option_id("k")) == 12


def test_an_option_id_that_was_never_offered_asks_again(client) -> None:
    """A client cannot invent a choice, and is not failed for trying.

    The server matches against the options it derived on this run, so an
    unknown id reaches nothing. It asks the question again rather than erroring:
    an id mismatch is not something the asker can act on.
    """
    headers = _token(client)
    clarification = _clarification(client, headers)
    answer = client.post(
        "/api/v1/clarify?stream=false",
        json={
            "session_id": "clarify-test",
            "clarification_id": clarification["clarification_id"],
            "option_id": "000000000000",
            "question": QUESTION,
        },
        headers=headers,
    ).json()
    print(f"\nunknown option_id -> {answer.get('status')}")
    assert answer["status"] == "CLARIFY"
    assert answer["receipt"] is None


def test_a_clarified_plan_still_faces_the_scope_rule(client) -> None:
    """D7: answering a clarification is not a way round rule 1.

    The patched plan goes back through validate AND gate, so scope is re-checked
    against the choice rather than against the plan that was asked about.
    """
    import inspect

    from receipts.agent import orchestrator

    # `answer` is a thin wrapper that stamps usage onto the trace (M20); the
    # pipeline is `_answer`. Both are checked, so neither a renamed wrapper nor
    # a moved pipeline can leave this guard inspecting the wrong function --
    # which is exactly what happened when the wrapper was introduced.
    wrapper = inspect.getsource(orchestrator.answer)
    assert "_answer(" in wrapper, "answer() no longer delegates to the pipeline"

    source = inspect.getsource(orchestrator._answer)
    tree = ast.parse(ast.unparse(ast.parse(source)))
    calls = [
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    ]
    print(f"\n_validate_and_gate called {calls.count('_validate_and_gate')} times in _answer()")
    assert calls.count("_validate_and_gate") == 2, (
        "the clarified plan must be validated and gated again, not spliced in"
    )
