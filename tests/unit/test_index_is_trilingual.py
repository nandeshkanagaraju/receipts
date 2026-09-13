"""No index-building step may work in one language and not the others.

Three milestones in a row shipped a facility built for English that nobody had
extended: M8's tokeniser split Devanagari and Tamil combining marks, M14's
glossary-default matcher split matras with `[\\w-]+`, and M15's retriever noise
list was eleven English words. Every time the English path worked, nothing raised
an error, and the cost showed up only as a language gap in the eval — Hindi at
25.0% against Tamil's 41.7%, traced back to `में` and `कितने` being indexed as
metric terms for a finance-gated metric.

The pattern is the thing worth testing, not the three instances. These tests ask
of each step: does it treat the three scripts alike?
"""

from __future__ import annotations

import pytest

from receipts.agent.retrieve import LOW_SIGNAL, retrieve, tokenize
from receipts.semantic import loader

SCRIPTS = {
    "en": "How much did we capture in the UK last week?",
    "hi": "पिछले हफ़्ते UK में हमने कितना पैसा वसूल किया?",
    "ta": "கடந்த வாரம் UK-யில் எவ்வளவு பணம் வசூலித்தோம்?",
}

# Devanagari and Tamil Unicode blocks.
DEVANAGARI = range(0x0900, 0x0980)
TAMIL = range(0x0B80, 0x0C00)


@pytest.fixture(scope="module")
def catalog():
    return loader.load()


def _script_of(word: str) -> str:
    for char in word:
        if ord(char) in DEVANAGARI:
            return "hi"
        if ord(char) in TAMIL:
            return "ta"
    return "en"


def test_the_noise_list_covers_all_three_scripts() -> None:
    """The M15 defect, stated as a property rather than as its symptom."""
    by_script: dict[str, int] = {"en": 0, "hi": 0, "ta": 0}
    for word in LOW_SIGNAL:
        by_script[_script_of(word)] += 1
    print(f"\nLOW_SIGNAL by script: {by_script}")
    for script, count in by_script.items():
        assert count >= 8, (
            f"{script} has {count} noise words against "
            f"{max(by_script.values())} for the best-covered script; "
            "a single-language noise list is how Hindi lost two questions"
        )


def test_the_noise_list_holds_no_interrogatives() -> None:
    """The composition rule, in both directions.

    Too narrow admits false matches -- `में` indexed as a metric term. Too wide
    erases true ones: `gmv_captured`'s Hindi phrase is "कितना पैसा वसूल", so a
    list that swallowed `कितना` emptied that question's slice. Interrogatives
    carry signal in this domain and stay.
    """
    interrogatives = {
        "how",
        "many",
        "much",
        "what",
        "which",
        "कितना",
        "कितने",
        "कितनी",
        "क्या",
        "एत्तனை",
        "எத்தனை",
        "எவ்வளவு",
        "என்ன",
    }
    caught = sorted(LOW_SIGNAL & interrogatives)
    assert not caught, f"interrogatives carry signal here and were stripped: {caught}"


def test_tokenising_keeps_whole_words_in_every_script() -> None:
    """M8's bug, which would have been caught here."""
    for lang, text in SCRIPTS.items():
        tokens = tokenize(text)
        assert tokens, f"{lang} tokenised to nothing"
        # No token may be a bare combining mark or a one-character fragment of a
        # word: that is what splitting on matras produces.
        debris = [t for t in tokens if len(t) == 1 and _script_of(t) != "en"]
        assert not debris, f"{lang} produced syllable debris: {debris}"


def test_every_language_retrieves_a_non_empty_slice_for_the_same_question(catalog) -> None:
    """The same question in three languages must reach the layer in all three."""
    results = {}
    for lang, text in SCRIPTS.items():
        slice_ = retrieve(text, catalog, k=8)
        results[lang] = tuple(m.name for m in slice_.metrics)
        assert slice_.metrics, f"{lang} retrieved nothing for a question en answers"
    print(f"\ntop metric per language: { {k: v[0] for k, v in results.items()} }")
    # They need not agree on ordering, but the intended metric must be reachable
    # in all three -- "how much did we capture" is gmv_captured.
    for lang, names in results.items():
        assert "gmv_captured" in names, f"{lang} cannot reach gmv_captured: {names[:4]}"


def test_no_metric_phrase_is_indexed_as_pure_noise(catalog) -> None:
    """A metric whose phrase survives tokenisation as nothing matches everything.

    `settlement_lag_days` carried the Hindi phrase "निपटान में कितने दिन". Had
    every word in it been noise, it would have matched every Hindi question
    equally -- the opposite error to the one that actually happened, and the
    reason the composition rule above is two-sided.
    """
    empty: list[str] = []
    for metric in catalog.metrics:
        for lang, phrases in (metric.default_for or {}).items():
            for phrase in phrases:
                if not tokenize(phrase):
                    empty.append(f"{metric.name}[{lang}]: {phrase!r}")
    assert not empty, "metric phrases that tokenise to nothing:\n" + "\n".join(empty)


def test_a_gated_metric_does_not_win_on_function_words(catalog) -> None:
    """The measured regression, pinned.

    Two Hindi questions with nothing to do with settlement scored 4.08 against
    `settlement_lag_days` -- higher than either other language managed on the
    right metric -- because `में` and `कितने` came from its Hindi phrase. The gate
    then DENIED, naming a capability the question never asked about.
    """
    every = tuple(sorted({m.required_capability for m in catalog.metrics if m.required_capability}))
    for text in (
        "पिछले महीने UK में हमें कितने अलग-अलग जारीकर्ता बैंक दिखे?",
        "पिछले हफ़्ते UK में कितने कार्ड प्रयास विफल हुए?",
    ):
        top = retrieve(text, catalog, k=3, capabilities=every).scored
        assert top, "precondition: this question retrieves nothing at all"
        winner = catalog.metric(top[0].name)
        print(f"\n{text[:40]}... -> {top[0].name} ({top[0].score:.2f})")
        assert not winner.required_capability, (
            f"a capability-gated metric ({winner.name}) is the top match for a "
            "question that never asked for it; rule 1 will DENY on a function word"
        )
