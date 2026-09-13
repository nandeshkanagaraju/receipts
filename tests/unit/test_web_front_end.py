"""The front end, guarded from the Python side (M17, SDD §22).

Playwright covers the journeys; these cover the things that drift silently
between the spec, the API and the bundle -- and that no browser test would
notice because the page would still render.

Every assertion here reads the artefact. None of them repeats a number from a
document.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
WEB = REPO / "web"
SDD = REPO / "docs" / "SDD.md"


def _sdd_tokens() -> dict[str, str]:
    """SDD §22's design-token table, parsed out of the spec itself."""
    text = SDD.read_text(encoding="utf-8")
    section = text[text.index("## 22. Front end") :]
    section = section[: section.index("**Quality floor:**")]
    rows = re.findall(r"^\|\s*(\w[\w ]*?)\s*\|\s*`(#[0-9A-Fa-f]{6})`\s*\|", section, re.MULTILINE)
    return {name.strip().lower(): value.upper() for name, value in rows}


def test_the_tailwind_palette_is_exactly_the_sdd_tokens() -> None:
    """A colour in the config that §22 does not define is a colour nobody chose.

    The point of naming the tokens in the spec is that a component cannot reach
    for a shade that was never agreed. That only holds while the two agree.
    """
    tokens = _sdd_tokens()
    assert tokens, "precondition: §22's token table was not found in the SDD"

    config = (WEB / "tailwind.config.js").read_text(encoding="utf-8")
    block = config[config.index("colors: {") : config.index("fontFamily")]
    configured = {
        name: value.upper() for name, value in re.findall(r'(\w+):\s*"(#[0-9A-Fa-f]{6})"', block)
    }
    print(f"\nSDD §22 tokens: {tokens}")
    print(f"tailwind colors: {configured}")
    assert configured == tokens, "the palette and SDD §22 have drifted apart"


def test_the_type_stack_is_the_one_the_sdd_names() -> None:
    """Plex Sans for the interface, Plex Mono for the receipt, Noto fallbacks."""
    config = (WEB / "tailwind.config.js").read_text(encoding="utf-8")
    for family in ("IBM Plex Sans", "IBM Plex Mono", "Noto Sans Tamil", "Noto Sans Devanagari"):
        assert family in config, f"§22 names {family} and the config does not"


def test_mono_is_used_only_inside_the_receipt() -> None:
    """§22 permits Plex Mono in ONE place, and the restraint is the design.

    The receipt reads as a different kind of object because it is set
    differently. A second mono block anywhere else spends that signal.
    """
    allowed = {"ReceiptCard.tsx", "ReceiptDrawer.tsx"}
    offenders = [
        path.name
        for path in (WEB / "src").rglob("*.tsx")
        if "font-mono" in path.read_text(encoding="utf-8") and path.name not in allowed
    ]
    print(f"\nfont-mono appears in: {sorted(set(offenders) | allowed)}")
    assert offenders == [], f"Plex Mono outside the receipt: {offenders}"


def test_every_example_question_is_one_the_demo_can_actually_answer() -> None:
    """The replay key hashes the question text (ADR-005, SDD §16).

    An example that is not in the recorded dev set returns 503, so the demo
    would fail on its own suggestions. This is why `examples.ts` is generated.
    """
    source = (WEB / "src" / "examples.ts").read_text(encoding="utf-8")
    payload = json.loads(source[source.index("{") : source.rindex("}") + 1])

    recorded: set[str] = set()
    questions = (REPO / "eval" / "questions" / "dev.jsonl").read_text(encoding="utf-8")
    for line in questions.splitlines():
        recorded.update(json.loads(line)["variants"].values())

    missing = [
        question
        for role in payload.values()
        for questions in role.values()
        for question in questions
        if question not in recorded
    ]
    total = sum(len(q) for role in payload.values() for q in role.values())
    print(f"\n{total} example questions, all drawn from the recorded dev set")
    assert missing == [], f"examples the demo cannot answer: {missing}"


def test_every_role_has_examples_in_every_offered_language() -> None:
    """A role switch that empties the empty state is a dead end."""
    source = (WEB / "src" / "examples.ts").read_text(encoding="utf-8")
    payload = json.loads(source[source.index("{") : source.rindex("}") + 1])
    roles = json.loads(
        json.dumps(  # the roles the UI offers, read from the component
            re.findall(
                r'"(\w+)"',
                (WEB / "src" / "api" / "types.ts")
                .read_text(encoding="utf-8")
                .split("export const ROLES = [")[1]
                .split("]")[0],
            )
        )
    )
    assert roles, "precondition: ROLES was not found"
    for role in roles:
        for language in ("en", "ta", "hi"):
            assert payload.get(role, {}).get(language), f"{role}/{language} has no examples"


def test_the_generated_examples_match_the_generator() -> None:
    """`examples.ts` is generated. A hand-edit must fail, not drift."""
    from scripts.gen_web_examples import build

    on_disk = (WEB / "src" / "examples.ts").read_text(encoding="utf-8")
    assert on_disk == build(), (
        "web/src/examples.ts has been hand-edited; run `python -m scripts.gen_web_examples` instead"
    )


def test_the_stages_the_ui_renders_are_the_stages_the_api_publishes() -> None:
    """The step trace names stages. It must name the ones that arrive."""
    from receipts.api.sse import STAGES

    source = (WEB / "src" / "api" / "types.ts").read_text(encoding="utf-8")
    listed = re.findall(r'"(\w+)"', source.split("export const STAGES = [")[1].split("]")[0])
    print(f"\nAPI stages: {list(STAGES)}\nUI stages:  {listed}")
    assert listed == list(STAGES)


def test_the_ui_knows_every_role_the_api_serves() -> None:
    import yaml

    declared = sorted(
        yaml.safe_load((REPO / "config" / "roles.yaml").read_text(encoding="utf-8"))["roles"]
    )
    source = (WEB / "src" / "api" / "types.ts").read_text(encoding="utf-8")
    listed = sorted(re.findall(r'"(\w+)"', source.split("export const ROLES = [")[1].split("]")[0]))
    print(f"\nroles.yaml: {declared}\nUI:         {listed}")
    assert listed == declared


def test_every_typed_error_code_has_copy_in_the_ui() -> None:
    """ "No error says only that something went wrong" (PDD §9).

    A code with no entry falls back to the API's own sentence, which is written
    for a developer. Every code the API can emit gets copy that says what to do.
    """
    from receipts.api.errors import CODES

    source = (WEB / "src" / "i18n.ts").read_text(encoding="utf-8")
    block = source.split("errors: {")[1].split("},")[0]
    covered = set(re.findall(r"(\w+):", block))
    missing = sorted(set(CODES) - covered - {"INTERNAL"})
    print(f"\nAPI codes: {sorted(CODES)}\nUI copy for: {sorted(covered)}")
    assert missing == [], f"error codes with no UI copy: {missing}"


def test_ask_why_is_rendered_disabled_and_names_the_cut() -> None:
    """The one documented SDD §22 deviation (LIMITATIONS.md).

    §22 requires the control; M18 is cut and `/why` returns 404. It is shown
    disabled with the reason on it. If the why-agent is ever built, this test
    fails and forces the decision to be revisited rather than forgotten.
    """
    source = (WEB / "src" / "components" / "AnswerCanvas.tsx").read_text(encoding="utf-8")
    assert 'data-testid="ask-why"' in source, "§22 requires the control to exist"
    assert "disabled" in source.split('data-testid="ask-why"')[0].rsplit("<button", 1)[1]
    assert "askWhyCut" in source, "the cut must be named on the control"

    limitations = (REPO / "LIMITATIONS.md").read_text(encoding="utf-8")
    assert "Ask why" in limitations, "an undocumented deviation from a frozen spec"


def test_the_why_route_still_refuses(monkeypatch: pytest.MonkeyPatch) -> None:
    """The reason the control is disabled, asserted against the API.

    Paired with the test above: one says the UI disables it, this says the API
    would refuse. A guard that asserts the milestone rather than the invariant
    goes quiet when the milestone passes (M2_NOTES §5), so this asserts the
    route's behaviour, and when M18 lands BOTH fail together.
    """
    monkeypatch.setenv("RECEIPTS_LLM_MODE", "replay")
    from fastapi.testclient import TestClient

    from receipts.api.app import create_app

    client = TestClient(create_app())
    token = client.post("/api/v1/auth/demo-login", json={"role": "admin"}).json()["token"]
    response = client.post(
        "/api/v1/why",
        json={"receipt_id": "0" * 16},
        headers={"authorization": f"Bearer {token}"},
    )
    print(f"\nPOST /why -> {response.status_code} {response.json()}")
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_the_built_spa_is_served_at_root_and_does_not_shadow_the_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One deployable (§22). A StaticFiles mount at "/" swallows what follows it."""
    monkeypatch.setenv("RECEIPTS_LLM_MODE", "replay")
    from fastapi.testclient import TestClient

    from receipts.api.app import create_app

    if not (WEB / "dist" / "index.html").is_file():
        pytest.fail("web/dist is missing; run `make web` (a missing artifact FAILS, never skips)")

    client = TestClient(create_app())
    page = client.get("/")
    print(f"\nGET / -> {page.status_code} {page.headers['content-type']}")
    assert page.status_code == 200
    assert 'id="root"' in page.text

    # Every API surface still reachable underneath the mount.
    assert client.get("/healthz").status_code == 200
    assert client.get("/api/v1/openapi.json").status_code == 200
    assert client.post("/api/v1/auth/demo-login", json={"role": "admin"}).status_code == 200


def test_no_component_exists_that_the_sdd_table_does_not_name() -> None:
    """ "If a component isn't in the SDD table, don't build it" (BUILD_PROMPTS)."""
    named = {
        "Header",
        "ChatPane",
        "StepTrace",
        "AnswerCanvas",
        "StatusBadge",
        "ChartView",
        "ClarifyChoices",
        "ReceiptCard",
        "ReceiptDrawer",
        "CatalogDrawer",
        "CatalogModeBanner",
        # Not in the table: the shell both drawers share. Named here rather than
        # excluded quietly -- it is a de-duplication of two components that ARE
        # in the table, and it renders nothing of its own.
        "Drawer",
    }
    built = {path.stem for path in (WEB / "src" / "components").glob("*.tsx")}
    print(f"\ncomponents built: {sorted(built)}")
    assert built <= named, f"components the SDD §22 table does not name: {sorted(built - named)}"


def test_the_front_end_reads_no_field_the_api_does_not_send() -> None:
    """Receipt fields the card renders must exist on the domain model.

    The card is written against a Receipt that was printed from a running
    system; this keeps it that way. A renamed field would otherwise show as a
    blank row rather than as a failure.
    """
    from receipts.domain.types import Receipt

    source = (WEB / "src" / "api" / "types.ts").read_text(encoding="utf-8")
    block = source.split("export interface Receipt {")[1].split("}")[0]
    declared = set(re.findall(r"^\s*(\w+):", block, re.MULTILINE))
    actual = set(Receipt.model_fields)
    print(f"\nUI Receipt fields: {sorted(declared)}")
    assert declared == actual, (
        f"only in the UI: {sorted(declared - actual)}; only in the API: {sorted(actual - declared)}"
    )


def test_the_clarify_body_the_ui_sends_is_the_one_the_route_accepts() -> None:
    """M17.1, from the client side.

    The route's body gained `question` and kept `option_id`. A client that
    stopped sending one of them would fall back to a CLARIFY loop that looks
    like a UI bug, so the two are pinned together.
    """
    from receipts.api.app import ClarifyBody

    source = (WEB / "src" / "api" / "client.ts").read_text(encoding="utf-8")
    body = source.split('stream(\n    "/clarify"')[1].split("handlers")[0]
    sent = set(re.findall(r"^\s*(\w+):", body, re.MULTILINE))
    required = set(ClarifyBody.model_fields)
    print(f"\nClarifyBody requires: {sorted(required)}\nthe client sends:     {sorted(sent)}")
    assert required <= sent, f"the client never sends {sorted(required - sent)}"


def test_the_app_never_hard_codes_a_colour_outside_the_tokens() -> None:
    """A hex literal in a component is a colour that skipped §22.

    Recharts takes colours as props rather than classes, so the chart is allowed
    the token values themselves -- and they are checked against §22, not merely
    permitted.
    """
    tokens = set(_sdd_tokens().values())
    offenders: dict[str, list[str]] = {}
    for path in (WEB / "src").rglob("*.tsx"):
        found = [
            value.upper()
            for value in re.findall(r"#[0-9A-Fa-f]{6}", path.read_text(encoding="utf-8"))
            if value.upper() not in tokens
        ]
        if found:
            offenders[path.name] = found
    print(f"\nhex literals outside §22: {offenders}")
    assert offenders == {}, offenders


def test_the_e2e_suite_covers_every_journey_build_prompts_names() -> None:
    """J1, J3, J4, J5, J7, J10. Walked as an AST over the spec file's titles,
    so a journey that is renamed out of existence fails rather than disappears."""
    source = (WEB / "e2e" / "journeys.spec.ts").read_text(encoding="utf-8")
    titles = re.findall(r'test\(\s*"([^"]+)"', source)
    covered = {match for title in titles for match in re.findall(r"^J\d+", title)}
    print(f"\njourneys covered: {sorted(covered)}")
    assert covered == {"J1", "J3", "J4", "J5", "J7", "J10"}, sorted(covered)


def test_the_reduced_motion_preference_is_honoured_globally() -> None:
    """§22 quality floor. Honoured once, globally, so a component added later
    cannot forget it."""
    css = (WEB / "src" / "index.css").read_text(encoding="utf-8")
    assert "@media (prefers-reduced-motion" in css, "the preference is not honoured at all"
    block = css.split("@media (prefers-reduced-motion")[1]
    assert "*," in block, "the rule must apply to everything, not to one component"


def test_focus_is_never_removed() -> None:
    """The commonest way visible focus is lost is a reset that hides the ring."""
    offenders = [
        path.name
        for path in (WEB / "src").rglob("*.*")
        if path.suffix in {".tsx", ".css"}
        and re.search(r"outline:\s*none|outline-none", path.read_text(encoding="utf-8"))
    ]
    print(f"\nfiles removing focus outline: {offenders}")
    assert offenders == []
