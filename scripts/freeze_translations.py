"""scripts/freeze_translations.py — [IO] gate and freeze the question translations.

    python scripts/freeze_translations.py --check       # run the gates only
    python scripts/freeze_translations.py --report      # per-set counts, no text
    python scripts/freeze_translations.py --backfill    # record missing source hashes
    python scripts/freeze_translations.py               # gates, then manifest + tag

Two freezes, on two clocks, because the work runs on two clocks:

| Tag | Covers | Moves when |
|---|---|---|
| `questions-frozen` | English wording, structure, roles, traps,
  expected answers, GLOSSARY.md, M2_NOTES.md | never again |
| `translations-frozen` | `variants.ta`, `variants.hi`,
  `variants.ta-Latn`, `translation_provenance` | once a human has read the Tamil |

Splitting them is not a convenience. A single freeze forces one of two bad
outcomes: freeze early and every Tamil correction reopens the evaluation, or
freeze late and the English is still editable while the system is being built.
Split, the evaluation is fixed the moment the questions are, and the
translations can still be corrected — but only the translations, because the
questions tag pins everything else and would fail if English moved.

**The gate.** `translations-frozen` is refused while any `eval` or `holdout`
question's Tamil variant is `pending` or `machine_unverified`. T6 (SDD §29) is
reported for human-checked variants, so a machine draft nobody has read is not
something to freeze — it is something to review. `dev` is exempt: it is the set
you run while building, not a set anything is reported from.

**The staleness guard.** Every translation records the SHA-256 of the English it
was made from, in `translation_source_hash` on its own row, one entry per
language. A translation is *stale* when that hash is not the hash of the
English now on the row: the question was reworded after the translation was
written, so the Tamil and the Hindi are answering the question as it used to be.
This is not hypothetical — three eval WHY questions were reworded in
`769ade5` and their translations had to be thrown away, which is only visible
because someone happened to look. The gate refuses the tag while any gated set
holds a stale translation, a translation with no recorded source hash, or an
empty `ta` or `hi`.

`--backfill` records hashes that are **missing** and refuses to touch one that
disagrees with the English. Overwriting is what a re-translation does, not what
a bookkeeping pass does; a backfill that silently re-stamped stale rows would be
a button that deletes the guard.

`--report` prints per-set counts of empty and stale translations — counts only,
never question text, so it can scan the holdout without disclosing it. The
same numbers are printed by `tests/unit/test_translation_freshness.py` on every
run of the suite.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import freeze_questions as fq  # noqa: E402

REPO = fq.REPO
QDIR = fq.QDIR
MANIFEST = fq.MANIFEST
TAG = "translations-frozen"

# Sets whose translations are reported on, and therefore gated.
GATED_SETS = ("eval", "holdout")
# Provenance values that mean a person has been involved (SDD §29).
CHECKED = ("human", "machine_verified")

# The row-level field holding one English hash per language.
SOURCE_HASH = "translation_source_hash"
# Languages every gated question must actually carry. `ta-Latn` is not here: it
# is hand-written by the author after the Tamil settles, so `pending` is its
# honest state, not a hole. It is still hashed once it carries text.
REQUIRED_LANGS = ("ta", "hi")


def translation_projection(row: dict) -> dict:
    """One question reduced to its qid and its translated fields."""
    return {
        "qid": row["qid"],
        "variants": {k: row["variants"].get(k, "") for k in fq.TRANSLATED_LANGS},
        "translation_provenance": row.get("translation_provenance", {}),
        SOURCE_HASH: row.get(SOURCE_HASH, {}),
    }


def english_of(row: dict) -> str:
    return row["variants"]["en"]


def source_hash(row: dict) -> str:
    """SHA-256 of the English this row's translations must have been made from."""
    return fq.sha256_text(english_of(row))


def text_of(row: dict, lang: str) -> str:
    return row["variants"].get(lang, "") or ""


def translated_langs(row: dict) -> tuple[str, ...]:
    """The languages this row actually carries text for."""
    return tuple(lang for lang in fq.TRANSLATED_LANGS if text_of(row, lang).strip())


def empty_langs(row: dict, langs: tuple[str, ...] = REQUIRED_LANGS) -> tuple[str, ...]:
    return tuple(lang for lang in langs if not text_of(row, lang).strip())


def hash_state(row: dict) -> dict[str, str]:
    """Per language that carries text: 'fresh', 'stale', or 'unhashed'.

    Three states, not two. A translation with no recorded hash is not fresh —
    nothing says which English it was made from — but it is not evidence of a
    reworded question either, and calling it stale would hide the rows that
    genuinely went out of date behind the rows nobody has hashed yet.
    """
    recorded = row.get(SOURCE_HASH) or {}
    current = source_hash(row)
    out = {}
    for lang in translated_langs(row):
        was = recorded.get(lang)
        out[lang] = "unhashed" if not was else ("fresh" if was == current else "stale")
    return out


def translation_digests(qdir: Path = QDIR) -> dict[str, str]:
    return {
        f"eval/questions/{p.name}": fq.sha256_text(
            fq.canonical(fq.rows_of(p), translation_projection)
        )
        for p in sorted(qdir.glob("*.jsonl"))
    }


def gate_provenance(qdir: Path = QDIR, gated: tuple[str, ...] = GATED_SETS) -> list[str]:
    """Every gated set's Tamil variant is human or machine_verified.

    `gated` is a parameter so a meta-test can empty it and show the same corpus
    would otherwise have been tagged.
    """
    problems: list[str] = []
    for name in gated:
        p = qdir / f"{name}.jsonl"
        if not p.exists():
            problems.append(f"{name}.jsonl is missing")
            continue
        unchecked: dict[str, list[str]] = {}
        for row in fq.rows_of(p):
            prov = row.get("translation_provenance", {}).get("ta", "pending")
            if prov not in CHECKED:
                unchecked.setdefault(prov, []).append(row["qid"])
        for prov, qids in sorted(unchecked.items()):
            problems.append(
                f"{name}.jsonl: {len(qids)} Tamil variant(s) are {prov!r}, "
                f"which is not one of {list(CHECKED)} — e.g. {', '.join(sorted(qids)[:5])}"
            )
    return sorted(problems)


def gate_text_present(qdir: Path = QDIR, gated: tuple[str, ...] = GATED_SETS) -> list[str]:
    """A variant marked as checked must actually carry text."""
    problems = []
    for name in gated:
        p = qdir / f"{name}.jsonl"
        if not p.exists():
            continue
        for row in fq.rows_of(p):
            for lang in fq.TRANSLATED_LANGS:
                prov = row.get("translation_provenance", {}).get(lang, "pending")
                if prov in CHECKED and not row["variants"].get(lang, "").strip():
                    problems.append(f"{row['qid']}: {lang} is {prov!r} but empty")
    return sorted(problems)


def gate_no_empty_translations(
    qdir: Path = QDIR,
    gated: tuple[str, ...] = GATED_SETS,
    langs: tuple[str, ...] = REQUIRED_LANGS,
) -> list[str]:
    """No gated question may be missing its Tamil or its Hindi.

    Separate from `gate_text_present`, which only catches an empty variant that
    someone has labelled as checked. This one does not consult the label: an
    empty translation in a reported set is a hole in the evaluation whatever the
    provenance says about it, and `pending` is exactly the label a hole wears.
    """
    problems = []
    for name in gated:
        p = qdir / f"{name}.jsonl"
        if not p.exists():
            continue
        for row in fq.rows_of(p):
            missing = empty_langs(row, langs)
            if missing:
                problems.append(f"{name}.jsonl: {row['qid']} has no {' or '.join(missing)}")
    return sorted(problems)


def gate_source_hashes(
    qdir: Path = QDIR,
    gated: tuple[str, ...] = GATED_SETS,
    enabled: bool = True,
) -> list[str]:
    """No gated translation may be stale or unhashed.

    `enabled` is a parameter so a meta-test can turn the guard off and show the
    same corpus would otherwise have been tagged.
    """
    if not enabled:
        return []
    problems = []
    for name in gated:
        p = qdir / f"{name}.jsonl"
        if not p.exists():
            continue
        for row in fq.rows_of(p):
            states = hash_state(row)
            stale = sorted(lang for lang, s in states.items() if s == "stale")
            unhashed = sorted(lang for lang, s in states.items() if s == "unhashed")
            if stale:
                problems.append(
                    f"{name}.jsonl: {row['qid']} {', '.join(stale)} translated from "
                    f"a different English — the question was reworded, retranslate it"
                )
            if unhashed:
                problems.append(
                    f"{name}.jsonl: {row['qid']} {', '.join(unhashed)} has no recorded "
                    f"source hash — run --backfill, or retranslate if it is out of date"
                )
    return sorted(problems)


def all_gates(qdir: Path = QDIR, gated: tuple[str, ...] = GATED_SETS) -> list[str]:
    return (
        gate_provenance(qdir, gated)
        + gate_text_present(qdir, gated)
        + gate_no_empty_translations(qdir, gated)
        + gate_source_hashes(qdir, gated)
    )


# --------------------------------------------------------------------------- #
# Counts, for every set including the holdout
# --------------------------------------------------------------------------- #
def set_counts(path: Path) -> dict[str, int]:
    """Counts only. This function must never return question text.

    It is the one thing that reads the holdout on an ordinary test run, so what
    it returns is what leaks. Ints, and nothing else.
    """
    counts = {"questions": 0}
    for lang in REQUIRED_LANGS:
        counts[f"{lang}_empty"] = 0
        counts[f"{lang}_stale"] = 0
        counts[f"{lang}_unhashed"] = 0
    for row in fq.rows_of(path):
        counts["questions"] += 1
        for lang in empty_langs(row):
            counts[f"{lang}_empty"] += 1
        for lang, state in hash_state(row).items():
            if lang in REQUIRED_LANGS and state in ("stale", "unhashed"):
                counts[f"{lang}_{state}"] += 1
    return counts


def translation_counts(qdir: Path = QDIR, sets: tuple[str, ...] = fq.SETS) -> dict[str, dict]:
    return {name: set_counts(qdir / f"{name}.jsonl") for name in sets if (qdir / f"{name}.jsonl").exists()}


def format_counts(counts: dict[str, dict]) -> str:
    head = f"{'set':10} {'questions':>9} " + " ".join(
        f"{lang + ' ' + k:>12}" for lang in REQUIRED_LANGS for k in ("empty", "stale", "unhashed")
    )
    lines = [head]
    for name, c in counts.items():
        cells = " ".join(
            f"{c[f'{lang}_{k}']:>12}"
            for lang in REQUIRED_LANGS
            for k in ("empty", "stale", "unhashed")
        )
        lines.append(f"{name:10} {c['questions']:>9} {cells}")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Backfill
# --------------------------------------------------------------------------- #
def backfill_file(path: Path, overwrite: bool = False) -> dict[str, int]:
    """Record the English hash for every translation that has text but no hash.

    Returns counts, and rewrites the file only if something changed. A hash that
    is present and disagrees is left exactly as it is: that row is the finding,
    and quietly re-stamping it would erase the only evidence that the question
    moved after it was translated.
    """
    rows = fq.rows_of(path)
    added = kept_stale = 0
    for row in rows:
        current = source_hash(row)
        recorded = dict(row.get(SOURCE_HASH) or {})
        for lang in translated_langs(row):
            if recorded.get(lang) == current:
                continue
            if lang in recorded and not overwrite:
                kept_stale += 1
                continue
            recorded[lang] = current
            added += 1
        # Drop hashes for languages that no longer carry text, so an emptied
        # variant cannot keep a hash that claims it was translated.
        recorded = {k: v for k, v in recorded.items() if k in translated_langs(row)}
        if recorded:
            row[SOURCE_HASH] = dict(sorted(recorded.items()))
        else:
            row.pop(SOURCE_HASH, None)
    write_rows(path, rows)
    return {"added": added, "left_stale": kept_stale, "questions": len(rows)}


def write_rows(path: Path, rows: list[dict]) -> None:
    """Rewrite a question file, one compact JSON object per line, key order kept.

    `translation_source_hash` is placed directly after `translation_provenance`
    so the two translation-side fields read together.
    """
    out = []
    for row in rows:
        ordered = {}
        for key, value in row.items():
            if key == SOURCE_HASH:
                continue
            ordered[key] = value
            if key == "translation_provenance" and SOURCE_HASH in row:
                ordered[SOURCE_HASH] = row[SOURCE_HASH]
        if SOURCE_HASH in row and SOURCE_HASH not in ordered:
            ordered[SOURCE_HASH] = row[SOURCE_HASH]
        out.append(json.dumps(ordered, ensure_ascii=False))
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def write_manifest(path: Path = MANIFEST, qdir: Path = QDIR) -> dict[str, str]:
    payload: dict = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    digests = translation_digests(qdir)
    payload["translations"] = digests
    payload["translations_projection"] = (
        "Translated fields only: variants.ta, variants.hi, variants.ta-Latn and "
        "translation_provenance. The English wording and structure are covered "
        "by questions-frozen."
    )
    payload.setdefault("algorithm", "sha256")
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return digests


def check_translations(path: Path = MANIFEST, qdir: Path = QDIR) -> list[str]:
    payload = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    recorded = payload.get("translations")
    if not recorded:
        return []
    actual = translation_digests(qdir)
    problems = []
    for rel in sorted(set(recorded) | set(actual)):
        want, got = recorded.get(rel), actual.get(rel)
        if want is None:
            problems.append(f"{rel}: present on disk but not in the manifest")
        elif got is None:
            problems.append(f"{rel}: in the manifest but missing on disk")
        elif want != got:
            problems.append(f"{rel}: translations changed after {TAG}")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="run the gates without freezing")
    ap.add_argument(
        "--report",
        action="store_true",
        help="per-set counts of empty and stale translations; prints no question text",
    )
    ap.add_argument(
        "--backfill",
        action="store_true",
        help="record missing source hashes; never overwrites one that disagrees",
    )
    args = ap.parse_args(argv)

    if args.report:
        print(format_counts(translation_counts()))
        return 0

    if args.backfill:
        total = {"added": 0, "left_stale": 0}
        for name in fq.SETS:
            p = QDIR / f"{name}.jsonl"
            if not p.exists():
                continue
            result = backfill_file(p)
            total["added"] += result["added"]
            total["left_stale"] += result["left_stale"]
            print(
                f"{name}.jsonl: {result['questions']} questions, "
                f"{result['added']} hash(es) recorded, {result['left_stale']} left stale"
            )
        if total["left_stale"]:
            print(
                f"\n{total['left_stale']} translation(s) disagree with the English on "
                f"their row and were NOT re-stamped. Retranslate them, then run "
                f"--backfill again.",
                file=sys.stderr,
            )
        return 0

    if not fq.tag_exists(fq.TAG):
        print(
            f"{fq.TAG} does not exist yet. Translations are frozen after the "
            f"questions they translate, never before.",
            file=sys.stderr,
        )
        return 1

    print(format_counts(translation_counts()))

    problems = all_gates()
    if problems:
        print(f"\nREFUSING to create the {TAG} tag. {len(problems)} problem(s):", file=sys.stderr)
        for p in problems:
            print(f"  {p}", file=sys.stderr)
        return 1

    if args.check:
        print("all translation gates pass; --check made no changes")
        return 0

    if fq.tag_exists(TAG):
        print(f"\n{TAG} already exists; refusing to move it", file=sys.stderr)
        return 1

    digests = write_manifest()
    print(f"recorded in {MANIFEST.relative_to(REPO)}:")
    for rel, d in digests.items():
        print(f"  {rel}  {d}")
    subprocess.run(
        ["git", "tag", "-a", TAG, "-m", "Question translations frozen"], cwd=REPO, check=True
    )
    out = subprocess.run(
        ["git", "rev-parse", TAG + "^{}"], cwd=REPO, capture_output=True, text=True, check=True
    )
    print(f"\ntagged {TAG} at {out.stdout.strip()[:7]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
