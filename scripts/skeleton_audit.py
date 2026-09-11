"""scripts/skeleton_audit.py — [IO] the rule-7 filter-swap audit.

Authoring rule 7 (`eval/questions/README.md`): *a filter swap alone is not a
difference.* Two questions that ask the same thing about a different place, a
different window of the same kind, or in a different currency are one question
written twice, and the second buys the evaluation nothing.

    python scripts/skeleton_audit.py            # print colliding groups
    python scripts/skeleton_audit.py --quiet     # exit code only

`scripts/freeze_questions.py` calls `collisions()` as a freeze gate: the
`questions-frozen` tag is refused while any two questions collide.

## What the skeleton keeps, and what it masks

The skeleton masks the *values* of the three things a question may vary without
becoming a new question, and keeps everything else:

| Masked to | Values |
|---|---|
| `<GLOBAL> <COUNTRY> <REGION> <CITY> <SHOWROOM>` | every place name, by **grain** |
| `<DAY> <WEEK> <MONTH> <QUARTER> <YEAR>` … and the comparison forms | every window, by **class** |
| `<CUR>` | every currency |

So Chennai → the UK is a swap and collides; a calendar month → a rolling seven
days is not, because it changes which rows the window selects and which glossary
rule applies (§1.6a). The key also carries population, kind and the
compare/series flags: an ANS and a DENY that read alike are not one question.

## What it cannot do

It compares surface text, so it over-reports where two questions differ in a
word it does not know, and under-reports where they differ only in a word it
does. It is a floor under rule 7, not a substitute for reading the pair.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
QDIR = REPO / "eval" / "questions"
SETS = ("dev", "eval", "holdout")

# Longest match first inside each group; groups are applied in the order below.
CURRENCIES: tuple[tuple[str, str], ...] = (
    ("in us dollars", "<CUR>"),
    ("in singapore dollars", "<CUR>"),
    ("in rupees", "<CUR>"),
    ("in pounds", "<CUR>"),
    ("in dirhams", "<CUR>"),
    ("in ringgit", "<CUR>"),
    ("us dollars", "<CUR>"),
    ("rupees", "<CUR>"),
    ("pounds", "<CUR>"),
    ("dirhams", "<CUR>"),
    ("ringgit", "<CUR>"),
)

WINDOWS: tuple[tuple[str, str], ...] = (
    # comparison windows keep their comparison shape
    ("this month versus the same days last month", "<MTD_VS_MTD>"),
    ("this month compared with last month", "<MTD_VS_MTD>"),
    ("this month versus last month", "<MTD_VS_MTD>"),
    ("this week so far compared with the same days last week", "<WTD_VS_WTD>"),
    ("last month versus the same month last year", "<YOY>"),
    ("versus the same month last year", "<YOY>"),
    ("compared with the same month last year", "<YOY>"),
    ("last week compared with the week before", "<WEEK_VS_WEEK>"),
    ("compared with the week before", "<WEEK_VS_WEEK>"),
    ("over the last 8 weeks compared with the 8 weeks before", "<ROLL8W_VS_ROLL8W>"),
    ("between july and august 2026", "<MONTH_VS_MONTH>"),
    ("from march to august 2026", "<RANGE>"),
    # plain windows
    ("over the last 7 days", "<ROLL7>"),
    ("for the last 7 days", "<ROLL7>"),
    ("in the last 7 days", "<ROLL7>"),
    ("last 7 days", "<ROLL7>"),
    ("over the last 8 weeks", "<ROLL8W>"),
    ("for the last 8 weeks", "<ROLL8W>"),
    ("last 8 weeks", "<ROLL8W>"),
    ("first half of the year", "<HALF>"),
    ("fiscal q1 of fy2026", "<QUARTER>"),
    ("fiscal q3 of fy2026", "<QUARTER>"),
    ("fiscal q1 of fy2027", "<QUARTER>"),
    ("calendar q2 2026", "<QUARTER>"),
    ("last quarter", "<QUARTER>"),
    ("this quarter", "<QUARTER>"),
    ("next quarter", "<QUARTER>"),
    ("q1 this year with q1 last year", "<QUARTER_VS_QUARTER>"),
    ("this year with last year", "<YEAR_VS_YEAR>"),
    ("so far this year", "<YEAR>"),
    ("this year", "<YEAR>"),
    ("last year", "<YEAR>"),
    ("q1", "<QUARTER>"),
    ("q2", "<QUARTER>"),
    ("q3", "<QUARTER>"),
    ("q4", "<QUARTER>"),
    ("the week before", "<WEEK>"),
    ("last week", "<WEEK>"),
    ("this week", "<WEEK>"),
    ("last month", "<MONTH>"),
    ("this month", "<MONTH>"),
    ("next month", "<MONTH>"),
    ("in july", "in <MONTH>"),
    ("in august", "in <MONTH>"),
    ("in june", "in <MONTH>"),
    ("july", "<MONTH>"),
    ("august", "<MONTH>"),
    ("yesterday", "<DAY>"),
    ("today", "<DAY>"),
)

PLACES: tuple[tuple[str, str], ...] = (
    ("across all countries", "<GLOBAL>"),
    ("all countries", "<GLOBAL>"),
    ("every region", "<GLOBAL>"),
    ("tamil nadu", "<REGION>"),
    ("anna nagar", "<SHOWROOM>"),
    ("chennai", "<CITY>"),
    ("coimbatore", "<CITY>"),
    ("madurai", "<CITY>"),
    ("velachery", "<CITY>"),
    ("manchester", "<CITY>"),
    ("dubai", "<CITY>"),
    ("united kingdom", "<COUNTRY>"),
    ("the uk", "<COUNTRY>"),
    ("uk", "<COUNTRY>"),
    ("the uae", "<COUNTRY>"),
    ("uae", "<COUNTRY>"),
    ("india", "<COUNTRY>"),
    ("indian", "<COUNTRY>"),
    ("singapore", "<COUNTRY>"),
    ("malaysia", "<COUNTRY>"),
    ("the us", "<COUNTRY>"),
)

# Words that carry no shape: dropping them keeps "What was our net revenue…" and
# "Net revenue…" the same question, which they are.
FILLER = frozenset(
    (
        "the",
        "our",
        "a",
        "an",
        "we",
        "did",
        "do",
        "does",
        "was",
        "were",
        "is",
        "are",
        "what",
        "show",
        "me",
        "for",
        "in",
        "at",
        "of",
        "and",
        "to",
        "s",
        "please",
        "give",
        "still",
        "much",
        "many",
        "how",
        "over",
        "across",
        "so",
        "far",
        "had",
        "have",
        "has",
        "with",
        "that",
        "it",
        "us",
        "my",
        "their",
    )
)


def skeleton(text: str) -> str:
    """Reduce one English variant to its filter-swap-invariant shape."""
    t = text.casefold()
    t = re.sub(r"[^a-z0-9<>£$ ]+", " ", t)
    for group in (CURRENCIES, WINDOWS, PLACES):
        for token, tag in group:
            t = re.sub(rf"(?<![a-z<]){re.escape(token)}(?![a-z>])", f" {tag} ", t)
    t = t.replace("£", " <CUR> ").replace("$", " <CUR> ")
    return " ".join(w for w in t.split() if w not in FILLER)


def key(row: dict) -> tuple[str, str, str, bool, bool]:
    e = row["expected"]
    return (
        skeleton(row["variants"]["en"]),
        row["population"],
        e["kind"],
        bool(e.get("compare")),
        bool(e.get("series")),
    )


def load_rows(qdir: Path = QDIR) -> list[dict]:
    """Every question in dev, eval and holdout. A missing file is not an error
    here — `freeze_questions.gate_files_present` owns that check."""
    rows: list[dict] = []
    for name in SETS:
        p = qdir / f"{name}.jsonl"
        if not p.exists():
            continue
        rows += [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    return rows


# --------------------------------------------------------------------------- #
# Rule-7 exceptions. A collision is allowed ONLY with a written reason.
# --------------------------------------------------------------------------- #
SKELETON_EXCEPTIONS: dict[frozenset[str], str] = {
    frozenset({"EV-142", "HO-043", "HO-044"}): (
        "deny vs legitimate-zero vs calendar-ambiguous. EV-142 is a DENY: a UK "
        "role asking about Malaysia, refused before any metric resolves. HO-043 "
        "asks for EMI share in the UK, where EMI does not exist, so the correct "
        "answer is a legitimate zero rather than an error or an abstention. "
        "HO-044 asks for India 'last quarter', which is calendar-ambiguous under "
        "a fiscal year starting in April. The three share a surface shape and "
        "test three unrelated behaviours."
    ),
}

# --------------------------------------------------------------------------- #
# GLOSSARY §6.2: terms that must be clarified have no place in an ANS question.
# The scan must not fire on DEFINED metric names that contain such a word --
# "net revenue" is a metric (§2.5); bare "revenue" is not.
# --------------------------------------------------------------------------- #
CLARIFY_TERMS = ("revenue", "best", "top", "worst", "performance", "growth")
DEFINED_PHRASES = ("net revenue", "captured gmv", "gross revenue")
TOPK = re.compile(r"\btop \d+\b|\btop-\d+\b|\bwhich (five|ten|\d+)\b", re.I)


def clarify_hits(qdir: Path = QDIR) -> list[tuple[str, str, str]]:
    """ANS questions using a §6.2 term outside a defined metric name."""
    hits = []
    for row in load_rows(qdir):
        if row["population"] != "ANS":
            continue
        en = row["variants"]["en"]
        masked = en.lower()
        for phrase in DEFINED_PHRASES:
            masked = masked.replace(phrase, " ")
        masked = TOPK.sub(" ", masked)
        for term in CLARIFY_TERMS:
            if re.search(rf"\b{term}\b", masked):
                hits.append((row["qid"], term, en))
    return hits


def allowed_and_failing(
    qdir: Path = QDIR,
) -> tuple[list[tuple], list[tuple]]:
    """Split collisions into those with a written reason and those without."""
    allowed, failing = [], []
    for k, members in collisions(qdir):
        qids = frozenset(r["qid"] for r in members)
        (allowed if qids in SKELETON_EXCEPTIONS else failing).append((k, members))
    return allowed, failing


def collisions(qdir: Path = QDIR) -> list[tuple[tuple, list[dict]]]:
    """Groups of two or more questions sharing a skeleton, sorted by first qid."""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for row in load_rows(qdir):
        groups[key(row)].append(row)
    return sorted(
        ((k, v) for k, v in groups.items() if len(v) > 1),
        key=lambda kv: kv[1][0]["qid"],
    )


def describe(k: tuple, members: list[dict]) -> str:
    qids = ", ".join(r["qid"] for r in members)
    shape = f"{k[1]}/{k[2]}{' compare' if k[3] else ''}{' series' if k[4] else ''}"
    return f"filter-swap collision: {qids} share the skeleton {k[0]!r} [{shape}]"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Rule-7 filter-swap audit")
    ap.add_argument("--quiet", action="store_true", help="exit code only")
    args = ap.parse_args(argv)

    rows = load_rows()
    groups = collisions()
    if not args.quiet:
        distinct = len({key(r) for r in rows})
        print(
            f"{len(rows)} questions, {distinct} distinct skeletons, "
            f"{len(groups)} colliding group(s)"
        )
        for k, members in groups:
            flags = f"{' compare' if k[3] else ''}{' series' if k[4] else ''}"
            print(f"\n  skeleton: {k[0]!r}  [{k[1]}/{k[2]}{flags}]")
            for r in members:
                print(f"    {r['qid']}  {r['variants']['en']}")
    return 1 if groups else 0


if __name__ == "__main__":
    raise SystemExit(main())
