"""scripts/freeze_translations.py — [IO] gate and freeze the question translations.

    python scripts/freeze_translations.py --check   # run the gates only
    python scripts/freeze_translations.py           # gates, then manifest + tag

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


def translation_projection(row: dict) -> dict:
    """One question reduced to its qid and its translated fields."""
    return {
        "qid": row["qid"],
        "variants": {k: row["variants"].get(k, "") for k in fq.TRANSLATED_LANGS},
        "translation_provenance": row.get("translation_provenance", {}),
    }


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


def all_gates(qdir: Path = QDIR, gated: tuple[str, ...] = GATED_SETS) -> list[str]:
    return gate_provenance(qdir, gated) + gate_text_present(qdir, gated)


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
    args = ap.parse_args(argv)

    if not fq.tag_exists(fq.TAG):
        print(
            f"{fq.TAG} does not exist yet. Translations are frozen after the "
            f"questions they translate, never before.",
            file=sys.stderr,
        )
        return 1

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
