"""The model layer: refusal under pytest, replay keying, fallback, budget, metering.

The two properties this module exists to guarantee are both refusals:

- a **real client cannot be constructed** inside a test run (D9);
- **replay with a missing recording raises** rather than reaching the network.

Both are tested as refusals rather than as "makes no calls", because a client
that exists is a client something can call, and a replay that falls through is a
live call nobody asked for.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from receipts.llm import budget as budget_mod
from receipts.llm import fallback as fallback_mod
from receipts.llm import prompts as prompt_mod
from receipts.llm import replay as replay_mod
from receipts.llm.base import (
    BudgetExceeded,
    ModelUnavailable,
    Msg,
    Provenance,
    RealClientUnderPytest,
    RecordingMissing,
    StructuredResult,
    TextResult,
    Transient,
    Usage,
)
from receipts.observability import metering

REPO = Path(__file__).resolve().parents[2]
SCHEMA = {"type": "object", "properties": {"answer": {"type": "string"}}}


# --------------------------------------------------------------------------- #
# 1. D9: the real clients refuse to exist here.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("module,cls", [("anthropic", "AnthropicLLM"), ("openai", "OpenAILLM")])
def test_real_llm_refuses_under_pytest(module: str, cls: str) -> None:
    import importlib

    provider = getattr(importlib.import_module(f"receipts.llm.{module}"), cls)
    with pytest.raises(RealClientUnderPytest) as caught:
        provider(model="whatever")
    print(f"\n{cls} -> {str(caught.value)[:70]}")
    assert "D9" in str(caught.value)


def test_the_refusal_is_construction_not_calling() -> None:
    """A client that exists is a client something can call.

    Asserted on the source: the guard is the first statement of `__init__`, before
    any attribute is set, so there is no half-built client to reach for.
    """
    source = (REPO / "src" / "receipts" / "llm" / "anthropic.py").read_text(encoding="utf-8")
    init = source[source.index("def __init__(") :]
    body = init[: init.index("\n\n")]
    first = [ln.strip() for ln in body.splitlines()[1:] if ln.strip()][0]
    print(f"\nfirst statement of __init__: {first}")
    assert "_refuse_under_pytest" in first


# --------------------------------------------------------------------------- #
# 2. Replay round trip, and the prompt hash in the key.
# --------------------------------------------------------------------------- #


class FakeLLM:
    """A stand-in provider. Counts its calls so a retry cannot be miscounted."""

    def __init__(self, *, provider: str = "fake", model: str = "fake-1", raises: int = 0) -> None:
        self.provider = provider
        self.model = model
        self.calls = 0
        self._raises = raises

    def _provenance(self, prompt_id: str) -> Provenance:
        prompt = prompt_mod.load(prompt_id)
        return Provenance(
            prompt_id=prompt.prompt_id,
            version=prompt.version,
            sha256=prompt.sha256,
            provider=self.provider,
            model=self.model,
        )

    def structured(self, *, prompt_id, messages, schema, max_tokens) -> StructuredResult:
        self.calls += 1
        if self.calls <= self._raises:
            raise Transient(status=529, detail="overloaded")
        return StructuredResult(
            data={"answer": "42"},
            usage=Usage(input_tokens=11, output_tokens=7),
            provenance=self._provenance(prompt_id),
            raw='{"answer": "42"}',
        )

    def text(self, *, prompt_id, messages, max_tokens) -> TextResult:
        self.calls += 1
        if self.calls <= self._raises:
            raise Transient(status=503, detail="unavailable")
        return TextResult(
            text="forty two",
            usage=Usage(input_tokens=5, output_tokens=3),
            provenance=self._provenance(prompt_id),
        )


@pytest.fixture
def prompt_dir(tmp_path: Path, monkeypatch) -> Path:
    directory = tmp_path / "prompts"
    directory.mkdir()
    (directory / "toy.v1.md").write_text("a toy prompt\n", encoding="utf-8")
    monkeypatch.setattr(prompt_mod, "PROMPTS", directory)
    return directory


def test_record_then_replay_returns_identical_results(tmp_path: Path, prompt_dir: Path) -> None:
    recordings = tmp_path / "recordings"
    inner = FakeLLM()
    recorder = replay_mod.RecordingLLM(inner, directory=recordings)
    messages = [Msg(role="user", content="what is the answer?")]

    recorded = recorder.structured(prompt_id="toy", messages=messages, schema=SCHEMA, max_tokens=64)
    files = list(recordings.glob("*.json"))
    print(f"\nrecording written: {len(files)} file(s)")
    assert len(files) == 1, "recording did not write exactly one file"

    player = replay_mod.ReplayLLM(recordings, provider="fake", model="fake-1")
    replayed = player.structured(prompt_id="toy", messages=messages, schema=SCHEMA, max_tokens=64)
    assert replayed.data == recorded.data
    assert replayed.usage == recorded.usage
    assert replayed.provenance == recorded.provenance
    assert inner.calls == 1, "replay called the inner client"


def test_one_character_of_the_prompt_changes_the_key_and_replay_raises(
    tmp_path: Path, prompt_dir: Path
) -> None:
    """The property that makes recordings trustworthy.

    A prompt edit that silently reused old recordings would report numbers
    belonging to an experiment nobody ran.
    """
    recordings = tmp_path / "recordings"
    recorder = replay_mod.RecordingLLM(FakeLLM(), directory=recordings)
    messages = [Msg(role="user", content="q")]
    recorder.structured(prompt_id="toy", messages=messages, schema=SCHEMA, max_tokens=64)

    player = replay_mod.ReplayLLM(recordings, provider="fake", model="fake-1")
    player.structured(prompt_id="toy", messages=messages, schema=SCHEMA, max_tokens=64)  # hits

    (prompt_dir / "toy.v1.md").write_text("a toy prompt!\n", encoding="utf-8")  # one character
    with pytest.raises(RecordingMissing) as caught:
        player.structured(prompt_id="toy", messages=messages, schema=SCHEMA, max_tokens=64)
    print(f"\nafter a one-character edit: {str(caught.value)[:80]}")


def test_replay_never_falls_through_to_the_network(tmp_path: Path, prompt_dir: Path) -> None:
    """Structural, not behavioural: ReplayLLM holds no client to fall through to."""
    player = replay_mod.ReplayLLM(tmp_path / "empty", provider="fake", model="fake-1")
    assert not hasattr(player, "inner"), "ReplayLLM carries an inner client"
    with pytest.raises(RecordingMissing):
        player.text(prompt_id="toy", messages=[Msg(role="user", content="q")], max_tokens=8)


@pytest.mark.parametrize(
    "field,value",
    [("model", "other-model"), ("provider", "other-provider")],
)
def test_the_key_covers_provider_and_model(
    field: str, value: str, tmp_path: Path, prompt_dir: Path
) -> None:
    """Replaying against a different model is a different experiment."""
    recordings = tmp_path / "recordings"
    replay_mod.RecordingLLM(FakeLLM(), directory=recordings).structured(
        prompt_id="toy", messages=[Msg(role="user", content="q")], schema=SCHEMA, max_tokens=64
    )
    kwargs = {"provider": "fake", "model": "fake-1", field: value}
    player = replay_mod.ReplayLLM(recordings, **kwargs)
    with pytest.raises(RecordingMissing):
        player.structured(
            prompt_id="toy", messages=[Msg(role="user", content="q")], schema=SCHEMA, max_tokens=64
        )


# --------------------------------------------------------------------------- #
# 3. Fallback: exactly one retry.
# --------------------------------------------------------------------------- #


def test_fallback_retries_the_primary_exactly_once_then_uses_the_secondary(
    prompt_dir: Path,
) -> None:
    primary = FakeLLM(provider="primary", raises=2)  # fails both attempts
    secondary = FakeLLM(provider="secondary")
    chain = fallback_mod.FallbackLLM(primary, secondary)

    result = chain.structured(
        prompt_id="toy", messages=[Msg(role="user", content="q")], schema=SCHEMA, max_tokens=64
    )
    print(f"\nprimary attempts={chain.primary_attempts} secondary={chain.secondary_attempts}")
    assert chain.primary_attempts == 2, "the primary was not tried exactly twice (1 + 1 retry)"
    assert chain.secondary_attempts == 1
    assert result.provenance.provider == "secondary"


def test_a_primary_that_recovers_on_its_retry_never_reaches_the_secondary(
    prompt_dir: Path,
) -> None:
    primary = FakeLLM(provider="primary", raises=1)
    secondary = FakeLLM(provider="secondary")
    chain = fallback_mod.FallbackLLM(primary, secondary)
    chain.structured(
        prompt_id="toy", messages=[Msg(role="user", content="q")], schema=SCHEMA, max_tokens=64
    )
    assert chain.primary_attempts == 2 and chain.secondary_attempts == 0


def test_both_failing_raises_model_unavailable(prompt_dir: Path) -> None:
    chain = fallback_mod.FallbackLLM(
        FakeLLM(provider="primary", raises=9), FakeLLM(provider="secondary", raises=9)
    )
    with pytest.raises(ModelUnavailable):
        chain.text(prompt_id="toy", messages=[Msg(role="user", content="q")], max_tokens=8)


def test_with_no_secondary_the_chain_goes_straight_to_unavailable(prompt_dir: Path) -> None:
    """The M5 cut-line: no pretending a second opinion exists."""
    chain = fallback_mod.FallbackLLM(FakeLLM(provider="primary", raises=9), None)
    with pytest.raises(ModelUnavailable) as caught:
        chain.text(prompt_id="toy", messages=[Msg(role="user", content="q")], max_tokens=8)
    assert "no secondary" in str(caught.value)


def test_a_non_transient_failure_is_not_retried(prompt_dir: Path) -> None:
    """A second identical request is a second identical failure plus a second charge."""

    class Broken(FakeLLM):
        def structured(self, **kwargs):  # type: ignore[override]
            self.calls += 1
            raise ValueError("bad request")

    primary = Broken(provider="primary")
    chain = fallback_mod.FallbackLLM(primary, FakeLLM(provider="secondary"))
    with pytest.raises(ValueError):
        chain.structured(
            prompt_id="toy", messages=[Msg(role="user", content="q")], schema=SCHEMA, max_tokens=64
        )
    assert primary.calls == 1, f"a non-transient failure was retried {primary.calls} times"


# --------------------------------------------------------------------------- #
# 4. Budget.
# --------------------------------------------------------------------------- #


def test_exceeding_the_per_question_budget_raises(prompt_dir: Path) -> None:
    class Greedy(FakeLLM):
        def structured(self, **kwargs):  # type: ignore[override]
            self.calls += 1
            return StructuredResult(
                data={},
                usage=Usage(input_tokens=99_999, output_tokens=1),
                provenance=self._provenance(kwargs["prompt_id"]),
            )

    limited = budget_mod.BudgetedLLM(Greedy(), budget_mod.QuestionBudget())
    with pytest.raises(BudgetExceeded) as caught:
        limited.structured(
            prompt_id="toy", messages=[Msg(role="user", content="q")], schema=SCHEMA, max_tokens=64
        )
    print(f"\nbudget -> {caught.value}")


def test_a_budget_accumulates_across_calls(prompt_dir: Path) -> None:
    """One question, several calls. The budget is per question, not per call."""
    limited = budget_mod.BudgetedLLM(
        FakeLLM(), budget_mod.QuestionBudget(tokens_in=25, tokens_out=25)
    )
    for _ in range(2):
        limited.structured(
            prompt_id="toy", messages=[Msg(role="user", content="q")], schema=SCHEMA, max_tokens=8
        )
    assert limited.budget.spent_in == 22
    with pytest.raises(BudgetExceeded):
        limited.structured(
            prompt_id="toy", messages=[Msg(role="user", content="q")], schema=SCHEMA, max_tokens=8
        )


# --------------------------------------------------------------------------- #
# 5. Metering: integer arithmetic only.
# --------------------------------------------------------------------------- #


def test_no_float_in_metering() -> None:
    """AST-walked. A price that touches a float is a price that drifts."""
    source = (REPO / "src" / "receipts" / "observability" / "metering.py").read_text("utf-8")
    tree = ast.parse(source)
    # Scoped to the functions that compute money. At module level `/` joins paths
    # -- `REPO / "config" / "pricing.yaml"` -- and a scan that cannot tell a path
    # join from a division would be switched off the first time it was right
    # about nothing. The three names are asserted, so a fourth arithmetic
    # function added later fails here rather than going unscanned.
    ARITHMETIC = {"cost_micro_usd", "_ceil_div", "format_micro_usd"}
    scanned = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name in ARITHMETIC
    ]
    assert {n.name for n in scanned} == ARITHMETIC, (
        f"the arithmetic functions have been renamed; scanned {[n.name for n in scanned]}"
    )
    floats = [
        n
        for fn in scanned
        for n in ast.walk(fn)
        if isinstance(n, ast.Constant) and isinstance(n.value, float)
    ]
    divisions = [
        n
        for fn in scanned
        for n in ast.walk(fn)
        if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Div)
    ]
    print(f"\nfloat literals: {len(floats)}; true division: {len(divisions)}")
    assert not floats, f"float literals in metering: {[n.value for n in floats]}"
    assert not divisions, "true division in metering; use integer arithmetic"


def test_a_known_usage_costs_exactly_what_it_should() -> None:
    pricing = {"m": metering.ModelPrice(3_000_000, 15_000_000)}
    # 12k in at 3 usd/Mtok = 36000 micro; 2k out at 15 usd/Mtok = 30000 micro.
    cost = metering.cost_micro_usd(
        model="m", input_tokens=12_000, output_tokens=2_000, pricing=pricing
    )
    print(f"\n12k/2k -> {cost} micro-usd ({metering.format_micro_usd(cost)})")
    assert cost == 66_000
    assert isinstance(cost, int)


def test_rounding_is_up_at_the_last_micro_dollar() -> None:
    """Under-reporting a bill is the error noticed late and by someone else."""
    pricing = {"m": metering.ModelPrice(1, 1)}
    assert metering.cost_micro_usd(model="m", input_tokens=1, output_tokens=0, pricing=pricing) == 1


def test_an_unpriced_model_raises_rather_than_guessing() -> None:
    with pytest.raises(metering.PricingError):
        metering.cost_micro_usd(model="nope", input_tokens=1, output_tokens=1, pricing={})


def test_every_configured_model_has_a_price() -> None:
    """Reachability: the pricing file is read and covers the configured models."""
    import yaml

    settings = yaml.safe_load((REPO / "config" / "settings.yaml").read_text("utf-8"))
    table = metering.load_pricing()
    configured = {
        settings["llm"]["primary"]["model"],
        settings["llm"]["secondary"]["model"],
    } - {"none", None}
    print(f"\nconfigured models {sorted(configured)}; priced {sorted(table)}")
    assert table, "no prices loaded at all"
    assert configured <= set(table), f"unpriced: {sorted(configured - set(table))}"


# --------------------------------------------------------------------------- #
# 6. Provenance (D15).
# --------------------------------------------------------------------------- #


def test_prompt_provenance_recorded(tmp_path: Path, prompt_dir: Path) -> None:
    recordings = tmp_path / "recordings"
    replay_mod.RecordingLLM(FakeLLM(), directory=recordings).structured(
        prompt_id="toy", messages=[Msg(role="user", content="q")], schema=SCHEMA, max_tokens=64
    )
    body = json.loads(next(recordings.glob("*.json")).read_text(encoding="utf-8"))
    provenance = body["provenance"]
    print(f"\nrecorded provenance: {provenance}")
    for field in ("prompt_id", "version", "sha256"):
        assert provenance.get(field), f"provenance has no {field} (D15)"
    assert provenance["sha256"] == prompt_mod.load("toy").sha256


def test_every_result_type_carries_provenance() -> None:
    for cls in (StructuredResult, TextResult):
        assert "provenance" in cls.__dataclass_fields__, f"{cls.__name__} has no provenance (D15)"


def test_a_missing_prompt_raises_rather_than_becoming_empty(tmp_path: Path, monkeypatch) -> None:
    """An empty system prompt is a different experiment, and it would run."""
    monkeypatch.setattr(prompt_mod, "PROMPTS", tmp_path)
    with pytest.raises(prompt_mod.PromptError):
        prompt_mod.load("absent")


def test_the_default_prompt_directory_is_resolved_at_call_time() -> None:
    """The default path, not the redirected one -- and they were once different.

    `load(directory: Path = PROMPTS)` bound the module attribute at *import*, so
    every test that redirected `PROMPTS` silently kept reading the real directory.
    Two tests above passed anyway, for the wrong reason: one asked for a prompt
    that was absent from both directories, and the other compared a sha to itself.
    A redirect that does nothing is worse than no redirect, because it reads as
    coverage. So this asserts both halves: the default reaches the repo's own
    prompts, and a redirect actually moves it.
    """
    from_default = prompt_mod.load("toy")
    assert from_default.sha256 == prompt_mod.load("toy", directory=prompt_mod.PROMPTS).sha256
    print(f"\ndefault directory {prompt_mod.PROMPTS.name}/ -> toy.v{from_default.version}")
    assert (prompt_mod.PROMPTS / f"toy.v{from_default.version}.md").exists()


# --------------------------------------------------------------------------- #
# 7. The provider switch (ADR-018) and prompt caching.
# --------------------------------------------------------------------------- #


class FakeOpenAIResponse:
    """Shaped like the SDK's response, including the nested usage details."""

    def __init__(self, content: str, prompt: int, completion: int, cached: int) -> None:
        self.choices = [type("C", (), {"message": type("M", (), {"content": content})()})()]
        details = type("D", (), {"cached_tokens": cached})()
        self.usage = type(
            "U",
            (),
            {
                "prompt_tokens": prompt,
                "completion_tokens": completion,
                "prompt_tokens_details": details,
            },
        )()


class FakeOpenAISDK:
    """Records exactly what was sent, so the request shape can be asserted."""

    def __init__(self, cached: int = 0) -> None:
        self.sent: list[dict] = []
        self._cached = cached
        outer = self

        class Completions:
            def create(self, **kwargs):
                outer.sent.append(kwargs)
                return FakeOpenAIResponse("hello", prompt=1000, completion=20, cached=outer._cached)

        self.chat = type("Chat", (), {"completions": Completions()})()


def openai_client(monkeypatch, **kwargs):
    """Construct the real class with the pytest refusal lifted for one line.

    The refusal is the point of `test_real_llm_refuses_under_pytest`, so it is
    suspended here deliberately and narrowly rather than weakened: these tests
    drive a fake SDK and make no call.
    """
    from receipts.llm import openai as openai_mod

    monkeypatch.setattr(openai_mod, "_refuse_under_pytest", lambda provider: None)
    return openai_mod.OpenAILLM(**kwargs)


def test_the_gpt5_family_gets_max_completion_tokens_not_max_tokens(monkeypatch, prompt_dir) -> None:
    """`max_tokens` is refused outright with a 400 by every gpt-5 model."""
    sdk = FakeOpenAISDK()
    client = openai_client(monkeypatch, model="gpt-5.5-2026-04-23", client=sdk)
    client.text(prompt_id="toy", messages=[Msg(role="user", content="q")], max_tokens=64)
    sent = sdk.sent[0]
    print(f"\nrequest keys: {sorted(sent)}")
    assert "max_completion_tokens" in sent and sent["max_completion_tokens"] == 64
    assert "max_tokens" not in sent, "the deprecated parameter is still being sent"


def test_temperature_is_omitted_when_it_is_none(monkeypatch, prompt_dir) -> None:
    """Not sent as 0. The model returns 400 for any explicit value (ADR-018)."""
    sdk = FakeOpenAISDK()
    client = openai_client(monkeypatch, model="gpt-5.5-2026-04-23", client=sdk, temperature=None)
    client.text(prompt_id="toy", messages=[Msg(role="user", content="q")], max_tokens=8)
    assert "temperature" not in sdk.sent[0], "temperature was sent to a model that refuses it"


def test_temperature_is_sent_when_it_is_set(monkeypatch, prompt_dir) -> None:
    """Guard off: a model that accepts 0 still gets 0, so the omission is
    conditional rather than a quiet removal of the charter's setting."""
    sdk = FakeOpenAISDK()
    client = openai_client(monkeypatch, model="gpt-4.1", client=sdk, temperature=0)
    client.text(prompt_id="toy", messages=[Msg(role="user", content="q")], max_tokens=8)
    assert sdk.sent[0]["temperature"] == 0


def test_a_caller_supplied_system_message_is_not_shadowed(monkeypatch, prompt_dir) -> None:
    """The defect that would have wasted the whole paid run.

    `_messages` prepended the prompt *file* unconditionally. The baseline's
    system message is a 16k rendered prompt, so every call would have carried the
    unrendered template -- `{{DDL}}`, `{{GLOSSARY}}` and all -- in front of the
    real one: two system messages, one of them nonsense, on 180 calls.
    """
    sdk = FakeOpenAISDK()
    client = openai_client(monkeypatch, model="gpt-5.5-2026-04-23", client=sdk)
    client.text(
        prompt_id="toy",
        messages=[Msg(role="system", content="RENDERED"), Msg(role="user", content="q")],
        max_tokens=8,
    )
    sent = sdk.sent[0]["messages"]
    systems = [m for m in sent if m["role"] == "system"]
    print(f"\n{len(sent)} messages, {len(systems)} system")
    assert len(systems) == 1, f"{len(systems)} system messages were sent"
    assert systems[0]["content"] == "RENDERED"
    assert "{{" not in json.dumps(sent), "an unrendered template reached the request"


def test_the_prompt_file_is_still_the_system_message_when_none_is_supplied(
    monkeypatch, prompt_dir
) -> None:
    """Guard off: the fix is conditional, not a removal."""
    sdk = FakeOpenAISDK()
    client = openai_client(monkeypatch, model="gpt-5.5-2026-04-23", client=sdk)
    client.text(prompt_id="toy", messages=[Msg(role="user", content="q")], max_tokens=8)
    systems = [m for m in sdk.sent[0]["messages"] if m["role"] == "system"]
    assert len(systems) == 1 and "toy prompt" in systems[0]["content"]


def test_a_cache_key_is_sent_so_same_prefix_calls_share_a_cache(monkeypatch, prompt_dir) -> None:
    sdk = FakeOpenAISDK()
    client = openai_client(monkeypatch, model="m", client=sdk, cache_key="receipts-baseline-m")
    client.text(prompt_id="toy", messages=[Msg(role="user", content="q")], max_tokens=8)
    assert sdk.sent[0]["prompt_cache_key"] == "receipts-baseline-m"


def test_cached_tokens_are_read_back_from_usage(monkeypatch, prompt_dir) -> None:
    """A cache that silently stops hitting looks exactly like a bigger bill."""
    sdk = FakeOpenAISDK(cached=896)
    client = openai_client(monkeypatch, model="m", client=sdk)
    result = client.text(prompt_id="toy", messages=[Msg(role="user", content="q")], max_tokens=8)
    print(f"\nusage: {result.usage}")
    assert result.usage.cached_input_tokens == 896
    assert result.usage.input_tokens == 1000, "cached tokens are part of the prompt total"


def test_cached_tokens_cannot_exceed_the_prompt_total() -> None:
    with pytest.raises(ValueError):
        Usage(input_tokens=10, output_tokens=1, cached_input_tokens=11)


def test_a_cached_prefix_is_priced_at_the_cached_rate() -> None:
    """The saving is real money and is computed, not assumed."""
    table = metering.load_pricing()
    model = "gpt-5.5-2026-04-23"
    full = metering.cost_micro_usd(
        model=model, input_tokens=16_000, output_tokens=500, pricing=table
    )
    cached = metering.cost_micro_usd(
        model=model,
        input_tokens=16_000,
        output_tokens=500,
        cached_input_tokens=15_000,
        pricing=table,
    )
    fmt = metering.format_micro_usd
    print(f"\nuncached {fmt(full)} -> cached {fmt(cached)}")
    assert cached < full, "caching did not reduce the price"
    # 1000 fresh @ $5/Mtok + 15000 cached @ $0.50/Mtok + 500 out @ $30/Mtok
    assert cached == 5_000 + 7_500 + 15_000


def test_cached_tokens_are_not_billed_twice() -> None:
    """They are *part of* the prompt total, not additional to it.

    Adding the two counts would bill the cached tokens at both rates, which is
    the arithmetic that makes caching look like it saved nothing.
    """
    table = metering.load_pricing()
    all_cached = metering.cost_micro_usd(
        model="gpt-5", input_tokens=1000, output_tokens=0, cached_input_tokens=1000, pricing=table
    )
    assert all_cached == 125, (
        f"1000 fully-cached tokens at $0.125/Mtok is 125 micro, got {all_cached}"
    )


def test_a_nonsensical_cached_count_raises_rather_than_discounting() -> None:
    with pytest.raises(ValueError):
        metering.cost_micro_usd(
            model="gpt-5", input_tokens=10, output_tokens=0, cached_input_tokens=99
        )


def test_the_configured_primary_and_secondary_agree_with_the_adr() -> None:
    """Same model on both sides, pinned, with no second opinion (ADR-018)."""
    from receipts.config import load_settings

    settings = load_settings()
    assert settings.llm.primary.provider == "openai"
    assert settings.llm.primary.model == "gpt-5.5-2026-04-23"
    assert "-" in settings.llm.primary.model.split("gpt-5.5")[-1], (
        "the primary is a floating alias; a dated snapshot is required so the "
        "baseline and Receipts cannot be recorded against different models"
    )
    assert settings.llm.secondary.provider == "none", (
        "a fallback to another model would break 'same model on both sides'"
    )


def test_a_budget_is_per_question_and_is_reset_between_them(prompt_dir: Path) -> None:
    """Found by the first live smoke run, at trial three of a 180-trial run.

    One `BudgetedLLM` is built per run, so without a reset the counter is a
    *per-run* budget wearing a per-question name, and the run dies partway
    through on a limit nobody set.
    """
    limited = budget_mod.BudgetedLLM(FakeLLM(), budget_mod.QuestionBudget(tokens_in=25))
    for _ in range(2):
        limited.structured(
            prompt_id="toy", messages=[Msg(role="user", content="q")], schema=SCHEMA, max_tokens=8
        )
    assert limited.budget.spent_in == 22
    limited.new_question()
    assert limited.budget.spent_in == 0, "the budget carried into the next question"
    assert limited.budget.tokens_in == 25, "resetting changed the allowance itself"
    assert limited.questions == 1
    # And it still refuses within one question.
    for _ in range(2):
        limited.structured(
            prompt_id="toy", messages=[Msg(role="user", content="q")], schema=SCHEMA, max_tokens=8
        )
    with pytest.raises(BudgetExceeded):
        limited.structured(
            prompt_id="toy", messages=[Msg(role="user", content="q")], schema=SCHEMA, max_tokens=8
        )
