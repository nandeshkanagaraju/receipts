"""Language detection and normalisation: script ranges, code-mixing, digits.

No model call anywhere (SDD §9 stage 1). The hard case is not Tamil or
Devanagari script -- a codepoint range settles those -- it is romanised Tamil and
Hindi, which share an alphabet with English.

The test that earns its place is `test_no_lexicon_entry_is_an_english_word`. The
Hindi lexicon contained `the`, the plural of `tha`, and while it did, every
English question containing "the" was detected as Hinglish: two of sixty dev
English variants went that way. A lexicon entry that is also an English word does
not degrade the detector, it inverts it, and no amount of threshold tuning fixes
it.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import pytest

from receipts.language import read
from receipts.language.detect import (
    DECISION_THRESHOLD,
    LEXICON_WEIGHT,
    LanguageError,
    scripts_in,
)
from receipts.language.detect import detect as detect_with
from receipts.language.lexicon import LexiconError, load, read_one
from receipts.language.normalize import (
    DEVANAGARI_DIGITS,
    TAMIL_DIGITS,
    TAMIL_NUMERAL_SIGNS,
    normalize_text,
)

REPO = Path(__file__).resolve().parents[2]
LEXICONS = load()


def detect(text: str):
    """The pure detector with the loaded lexicon, so tests read as prose."""
    return detect_with(text, LEXICONS)


def load_lexicon(language: str) -> frozenset[str]:
    return LEXICONS.of(language)


QUESTIONS = REPO / "eval" / "questions"
TOKEN = re.compile(r"[A-Za-z][A-Za-z']*")
THRESHOLD = 0.95


def variants(set_name: str) -> list[tuple[str, str, str]]:
    out: list[tuple[str, str, str]] = []
    for line in (QUESTIONS / f"{set_name}.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        for lang, text in (row.get("variants") or {}).items():
            if text and text.strip():
                out.append((row["qid"], lang, text))
    return out


# --------------------------------------------------------------------------- #
# The corpus (M8 TEST 1). The matrix is printed, per VERIFY.
# --------------------------------------------------------------------------- #


def confusion(rows: list[tuple[str, str, str]], title: str) -> dict[str, Counter]:
    table: dict[str, Counter] = defaultdict(Counter)
    misses: list[str] = []
    for qid, labelled, text in rows:
        got = detect(text).lang
        table[labelled][got] += 1
        if got != labelled:
            misses.append(f"{qid} labelled {labelled} detected {got}: {text[:56]}")
    predicted = sorted({p for counts in table.values() for p in counts})
    print(f"\n{title}")
    print(" " * 12 + "".join(f"{p:>10}" for p in predicted) + f"{'n':>7}{'acc':>9}")
    for labelled in sorted(table):
        counts = table[labelled]
        n = sum(counts.values())
        right = counts.get(labelled, 0)
        cells = "".join(f"{counts.get(p, 0):>10}" for p in predicted)
        print(f"  {labelled:<10}{cells}{n:>7}{right / n:>9.1%}")
    for line in misses[:10]:
        print(f"    miss: {line}")
    return table


def test_dev_variants_are_detected_as_their_labelled_language() -> None:
    """Dev carries en, ta and hi on all 60. It carries no ta-Latn at all."""
    table = confusion(variants("dev"), "DEV confusion matrix")
    for labelled, counts in sorted(table.items()):
        n = sum(counts.values())
        accuracy = counts.get(labelled, 0) / n
        assert accuracy >= THRESHOLD, (
            f"{labelled}: {accuracy:.1%} over {n} variants, below {THRESHOLD:.0%}. "
            f"Detected instead: {dict(counts)}"
        )


def test_dev_carries_no_ta_latn_yet() -> None:
    """Stated as a fact, not assumed.

    All 60 ta-Latn variants in dev are empty with provenance `pending`. The human
    Tanglish lives in eval. A test that silently skipped an absent language would
    let the corpus quietly lose one.
    """
    rows = [
        json.loads(line)
        for line in (QUESTIONS / "dev.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    filled = [r for r in rows if (r.get("variants") or {}).get("ta-Latn", "").strip()]
    pending = [
        r for r in rows if (r.get("translation_provenance") or {}).get("ta-Latn") == "pending"
    ]
    print(f"\ndev ta-Latn: {len(filled)} filled, {len(pending)} pending, of {len(rows)}")
    assert not filled, "dev now has ta-Latn text; fold it into the dev matrix"
    assert len(pending) == len(rows)


def test_the_human_tanglish_variants_are_detected() -> None:
    """The 40 `provenance: human` ta-Latn rows in eval -- real code-mixed text."""
    rows = [r for r in variants("eval") if r[1] == "ta-Latn"]
    assert len(rows) == 40, f"{len(rows)} human ta-Latn variants, expected 40"
    table = confusion(rows, "EVAL ta-Latn (human-written)")
    counts = table["ta-Latn"]
    accuracy = counts.get("ta-Latn", 0) / sum(counts.values())
    assert accuracy >= THRESHOLD, f"ta-Latn {accuracy:.1%}, below {THRESHOLD:.0%}"


def test_no_english_variant_is_detected_as_anything_else() -> None:
    """210 English questions across dev and eval.

    The false-positive direction, tested on its own, because it is the one that
    costs most: English is the default and the majority, so a wrong Tamil reading
    misroutes a question that would otherwise have been fine.
    """
    english = [r for f in ("dev", "eval") for r in variants(f) if r[1] == "en"]
    wrong = [
        (qid, detect(text).lang, text) for qid, _, text in english if detect(text).lang != "en"
    ]
    print(f"\n{len(english)} English variants, {len(wrong)} misdetected")
    for qid, got, text in wrong[:6]:
        print(f"  {qid} -> {got}: {text[:60]}")
    assert not wrong, f"{len(wrong)} English questions detected as another language"


# --------------------------------------------------------------------------- #
# The lexicon guarantee the threshold rests on.
# --------------------------------------------------------------------------- #

ENGLISH_STOPLIST = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "been",
        "but",
        "by",
        "can",
        "did",
        "do",
        "does",
        "for",
        "from",
        "had",
        "has",
        "have",
        "he",
        "her",
        "his",
        "how",
        "i",
        "if",
        "in",
        "into",
        "is",
        "it",
        "its",
        "me",
        "my",
        "no",
        "not",
        "of",
        "on",
        "or",
        "our",
        "out",
        "she",
        "so",
        "than",
        "that",
        "the",
        "their",
        "them",
        "then",
        "there",
        "these",
        "they",
        "this",
        "to",
        "up",
        "us",
        "was",
        "we",
        "were",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "will",
        "with",
        "you",
        "your",
    ]
)


def test_no_lexicon_entry_is_an_english_word() -> None:
    """The guarantee that makes one lexicon hit conclusive.

    Checked two ways: against a stoplist, and against every distinct English
    token in the corpus's own English variants -- which is the empirical half and
    the half that caught the real bug. `the` was in the Hindi lexicon.
    """
    corpus_english: set[str] = set()
    for set_name in ("dev", "eval"):
        for _qid, lang, text in variants(set_name):
            if lang == "en":
                corpus_english.update(word.casefold() for word in TOKEN.findall(text))
    print(f"\n{len(corpus_english)} distinct English tokens in the corpus")

    offenders: list[str] = []
    for language in ("ta", "hi"):
        lexicon = load_lexicon(language)
        for source, words in (("stoplist", ENGLISH_STOPLIST), ("corpus", corpus_english)):
            collisions = sorted(lexicon & words)
            if collisions:
                offenders.append(f"{language}.txt vs {source}: {collisions}")
    for line in offenders:
        print(f"  {line}")
    assert not offenders, (
        "a lexicon entry is also an English word. This does not degrade the detector, "
        f"it inverts it: {offenders}"
    )


def test_one_lexicon_hit_is_enough_to_decide() -> None:
    """The threshold and the guarantee have to agree, and this is where they do."""
    assert DECISION_THRESHOLD <= LEXICON_WEIGHT, (
        "one lexicon hit no longer decides, but the lexicon still guarantees that "
        "its entries are not English words; the two settings disagree"
    )
    assert detect("last week namma refund rate evlo?").lang == "ta-Latn"


def test_the_lexicons_hold_function_words_not_business_nouns() -> None:
    """Code-mixed text keeps its nouns in English; the grammar is what marks it.

    A lexicon of business nouns would match nothing, because nobody writes them
    in Tamil. Asserted by checking the metric vocabulary is absent.
    """
    business = {"order", "orders", "refund", "payment", "gmv", "revenue", "showroom", "bank"}
    for language in ("ta", "hi"):
        assert not (load_lexicon(language) & business), f"{language}.txt holds business nouns"


# --------------------------------------------------------------------------- #
# Script ranges and mixing (M8 TEST 2).
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Chennai UPI வெற்றி விகிதம்", "ta"),
        ("Chennai UPI सफलता दर", "hi"),
        ("நேற்று Chennai-la orders", "ta"),
        ("What was our UPI success rate in Chennai yesterday?", "en"),
        ("July-la country-wise captured GMV evlo, US dollars-la?", "ta-Latn"),
        ("kal Chennai mein kitne orders hue?", "hi-Latn"),
    ],
)
def test_mixed_script_takes_the_indic_language(text: str, expected: str) -> None:
    """A person writing their own script has chosen their language.

    The English words in "Chennai UPI வெற்றி விகிதம்" are the borrowing, not the
    other way round -- and the Latin characters outnumber the Tamil ones, so a
    majority rule would get this exactly backwards.
    """
    detection = detect(text)
    print(f"\n{detection.lang:<8} conf={detection.confidence:<7} {text[:44]}")
    assert detection.lang == expected


def test_scripts_seen_reports_what_was_actually_there() -> None:
    detection = detect("Chennai UPI வெற்றி விகிதம்")
    assert "Tamil" in detection.scripts_seen and "Latin" in detection.scripts_seen


def test_confidence_is_never_certain() -> None:
    """This is a heuristic and says so. A 1.0 would invite treating it as a fact."""
    for text in ("July-la evlo?", "kal kitne orders hue?"):
        assert detect(text).confidence <= 0.95


@pytest.mark.parametrize("text", ["orders \u0bae", "orders \u0bbe"])
def test_a_single_tamil_character_is_enough(text: str) -> None:
    """A letter, and a bare vowel sign.

    The second case failed while `scripts_in` filtered on `isalpha()`: U+0BBE is
    a spacing combining mark, so Python calls it not-a-letter and the counter saw
    pure Latin. Both are Tamil script.
    """
    assert detect(text).lang == "ta"


# --------------------------------------------------------------------------- #
# Normalisation (M8 TEST 3 and 4).
# --------------------------------------------------------------------------- #


def test_indic_digits_normalise_to_ascii() -> None:
    assert normalize_text("௧௨") == "12"
    assert normalize_text("१२") == "12"
    assert normalize_text("last ௭ days") == "last 7 days"
    assert normalize_text("कल १२ orders") == "कल 12 orders"


def test_every_digit_in_both_scripts_maps() -> None:
    """All ten, both scripts, in order. A partial map is worse than none."""
    assert normalize_text(TAMIL_DIGITS) == "0123456789"
    assert normalize_text(DEVANAGARI_DIGITS) == "0123456789"


def test_tamil_numeral_signs_are_left_alone() -> None:
    """௰ ௱ ௲ are ten, hundred, thousand -- not positional digits.

    Mapping them to an ASCII character would turn a numeral sign into a plausible
    wrong number, which is worse than leaving a character the planner will simply
    not understand.
    """
    assert normalize_text(TAMIL_NUMERAL_SIGNS) == TAMIL_NUMERAL_SIGNS


def test_whitespace_collapses_and_nfc_is_applied() -> None:
    assert normalize_text("  a   b  ") == "a b"
    decomposed = "நெ"  # ந + ெ
    assert normalize_text(decomposed) == "நெ"
    assert normalize_text("é") == "é", "NFC was not applied"


def test_the_original_is_kept_alongside() -> None:
    """The receipt has to quote what the person actually typed."""
    question = read("  நேற்று   ௧௨ orders ")
    assert question.text == "நேற்று 12 orders"
    assert question.original == "  நேற்று   ௧௨ orders "
    assert question.changed is True
    assert question.lang == "ta"


def test_detection_runs_on_the_original_not_the_normalised_form() -> None:
    """Which scripts were present is a fact about what was typed."""
    question = read("௧௨ orders")
    assert question.detection.scripts_seen, "scripts were counted after normalisation"


@pytest.mark.parametrize("bad", ["", "   ", "\t\n", " "])
def test_empty_or_whitespace_is_a_typed_error_not_english(bad: str) -> None:
    """An empty question routed as English reaches the planner and comes back
    as a confident answer to nothing."""
    with pytest.raises(LanguageError):
        detect(bad)
    with pytest.raises(LanguageError):
        read(bad)


def test_scripts_in_ignores_punctuation_and_digits() -> None:
    assert scripts_in("123 !?") == {"Tamil": 0, "Devanagari": 0, "Latin": 0, "Other": 0}


def test_no_model_call_is_possible_from_this_package() -> None:
    """SDD §9 stage 1: no model. Asserted on the imports, not on behaviour."""
    import ast

    package = REPO / "src" / "receipts" / "language"
    offenders = []
    for path in sorted(package.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            for name in names:
                if any(
                    word in name for word in ("llm", "openai", "anthropic", "httpx", "requests")
                ):
                    offenders.append(f"{path.name}:{node.lineno} imports {name}")
    print(f"\nlanguage/: {len(offenders)} model-shaped imports")
    assert not offenders, offenders


# --------------------------------------------------------------------------- #
# Purity: the lexicon is data, and the modules that use it do no I/O.
# --------------------------------------------------------------------------- #


def test_the_pure_modules_hold_no_file_access() -> None:
    """SDD §3 marks detect and normalize [P]; SDD §9 gives stage 1 a file.

    Both cannot hold in one module, and purity won: the lexicon is loaded by
    `language/lexicon.py` [IO] and passed in as data. Asserted on the source so
    the split cannot quietly be undone by a lazy import -- which would pass the
    charter's syntactic scan while doing exactly what it forbids.
    """
    import ast

    for name in ("detect.py", "normalize.py"):
        source = (REPO / "src" / "receipts" / "language" / name).read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in {
                "read_text",
                "read_bytes",
                "open",
                "glob",
            }:
                raise AssertionError(f"{name}:{node.lineno} touches the filesystem")
            if isinstance(node, ast.ImportFrom) and node.module == "lexicon":
                raise AssertionError(f"{name}:{node.lineno} imports the I/O module")
    print("\ndetect.py and normalize.py: no filesystem access, no lexicon import")


def test_a_missing_lexicon_file_raises_rather_than_matching_nothing(tmp_path: Path) -> None:
    """An empty lexicon silently turns every code-mixed question English.

    That failure looks like a detector that has stopped working rather than a
    file that has gone missing, which is why it is an error and not a default.
    """
    with pytest.raises(LexiconError):
        read_one("ta", tmp_path)
    (tmp_path / "ta.txt").write_text("# only a comment\n", encoding="utf-8")
    with pytest.raises(LexiconError):
        read_one("ta", tmp_path)
