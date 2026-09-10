"""Rule-7 skeleton audit — authoring scaffolding, deleted at `questions-frozen`.

Authoring rule 7: a filter swap alone is not a difference. Two questions that
ask the same thing about a different place, a different window of the same kind,
or in a different currency are one question, not two.

So the skeleton masks the *values* of place, window and currency while keeping
everything that makes a question a different question:

  * place  -> its grain  (<GLOBAL> <COUNTRY> <REGION> <CITY> <SHOWROOM>)
  * window -> its class  (<DAY> <WEEK> <MONTH> <QUARTER> <YEAR> <HALF>
                          <ROLL7> <ROLL8W> <RANGE> and the comparison forms)
  * money  -> <CUR>

Chennai -> the UK is a swap and collides. A calendar month -> a rolling seven
days is not: it changes which rows the window selects and which glossary rule
applies (§1.6a). The key also carries population, kind and the compare/series
flags, because an ANS and a DENY that read alike are not the same question.

Not a test. It over-reports by design, and every group it prints is read by hand.

    python eval/questions/_review/skeleton_audit.py
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

QDIR = Path(__file__).resolve().parents[1]

# Longest first inside each group; groups applied in this order.
CURRENCIES = [
    ("in us dollars", "<CUR>"), ("in singapore dollars", "<CUR>"),
    ("in rupees", "<CUR>"), ("in pounds", "<CUR>"), ("in dirhams", "<CUR>"),
    ("in ringgit", "<CUR>"), ("us dollars", "<CUR>"), ("rupees", "<CUR>"),
    ("pounds", "<CUR>"), ("dirhams", "<CUR>"), ("ringgit", "<CUR>"),
]

WINDOWS = [
    # comparison windows keep their comparison shape
    ("this month versus the same days last month", "<MTD_VS_MTD>"),
    ("this month compared with last month", "<MTD_VS_MTD>"),
    ("this month versus last month", "<MTD_VS_MTD>"),
    ("this month versus the same days last month", "<MTD_VS_MTD>"),
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
    ("over the last 7 days", "<ROLL7>"), ("for the last 7 days", "<ROLL7>"),
    ("in the last 7 days", "<ROLL7>"), ("last 7 days", "<ROLL7>"),
    ("over the last 8 weeks", "<ROLL8W>"), ("for the last 8 weeks", "<ROLL8W>"),
    ("last 8 weeks", "<ROLL8W>"),
    ("first half of the year", "<HALF>"),
    ("fiscal q1 of fy2026", "<QUARTER>"), ("fiscal q3 of fy2026", "<QUARTER>"),
    ("fiscal q1 of fy2027", "<QUARTER>"), ("calendar q2 2026", "<QUARTER>"),
    ("last quarter", "<QUARTER>"), ("this quarter", "<QUARTER>"),
    ("next quarter", "<QUARTER>"),
    ("q1 this year with q1 last year", "<QUARTER_VS_QUARTER>"),
    ("this year with last year", "<YEAR_VS_YEAR>"),
    ("so far this year", "<YEAR>"), ("this year", "<YEAR>"), ("last year", "<YEAR>"),
    ("q1", "<QUARTER>"), ("q2", "<QUARTER>"), ("q3", "<QUARTER>"), ("q4", "<QUARTER>"),
    ("the week before", "<WEEK>"), ("last week", "<WEEK>"), ("this week", "<WEEK>"),
    ("last month", "<MONTH>"), ("this month", "<MONTH>"), ("next month", "<MONTH>"),
    ("in july", "in <MONTH>"), ("in august", "in <MONTH>"), ("in june", "in <MONTH>"),
    ("july", "<MONTH>"), ("august", "<MONTH>"),
    ("yesterday", "<DAY>"), ("today", "<DAY>"),
]

PLACES = [
    ("across all countries", "<GLOBAL>"), ("all countries", "<GLOBAL>"),
    ("every region", "<GLOBAL>"), ("the gulf", "<GLOBAL>"),
    ("tamil nadu", "<REGION>"),
    ("anna nagar", "<SHOWROOM>"),
    ("chennai", "<CITY>"), ("coimbatore", "<CITY>"), ("madurai", "<CITY>"),
    ("velachery", "<CITY>"), ("manchester", "<CITY>"), ("dubai", "<CITY>"),
    ("united kingdom", "<COUNTRY>"), ("the uk", "<COUNTRY>"), ("uk", "<COUNTRY>"),
    ("the uae", "<COUNTRY>"), ("uae", "<COUNTRY>"), ("india", "<COUNTRY>"),
    ("indian", "<COUNTRY>"), ("singapore", "<COUNTRY>"), ("malaysia", "<COUNTRY>"),
    ("the us", "<COUNTRY>"), ("malaysia s", "<COUNTRY>"),
]

FILLER = {
    "the", "our", "a", "an", "we", "did", "do", "does", "was", "were", "is",
    "are", "what", "show", "me", "for", "in", "at", "of", "and", "to", "s",
    "please", "give", "still", "much", "many", "how", "over", "across", "so",
    "far", "had", "have", "has", "with", "that", "it", "us", "my", "their",
}


def skeleton(text: str) -> str:
    t = text.casefold()
    t = re.sub(r"[^a-z0-9<>£$ ]+", " ", t)
    for group in (CURRENCIES, WINDOWS, PLACES):
        for token, tag in group:
            t = re.sub(rf"(?<![a-z<]){re.escape(token)}(?![a-z>])", f" {tag} ", t)
    t = t.replace("£", " <CUR> ").replace("$", " <CUR> ")
    words = [w for w in t.split() if w not in FILLER]
    return " ".join(words)


def key(row: dict) -> tuple:
    e = row["expected"]
    return (
        skeleton(row["variants"]["en"]),
        row["population"],
        e["kind"],
        bool(e.get("compare")),
        bool(e.get("series")),
    )


def main() -> int:
    rows: list[dict] = []
    for name in ("dev", "eval", "holdout"):
        p = QDIR / f"{name}.jsonl"
        if not p.exists():
            raise SystemExit(f"{p} is missing")
        rows += [
            json.loads(line)
            for line in p.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        groups[key(r)].append(r)

    colliding = {k: v for k, v in groups.items() if len(v) > 1}
    print(
        f"{len(rows)} questions, {len(groups)} distinct skeletons, "
        f"{len(colliding)} colliding group(s)"
    )
    for k, members in sorted(colliding.items(), key=lambda kv: kv[1][0]["qid"]):
        print(f"\n  skeleton: {k[0]!r}  [{k[1]}/{k[2]}"
              f"{' compare' if k[3] else ''}{' series' if k[4] else ''}]")
        for r in members:
            print(f"    {r['qid']}  {r['variants']['en']}")
    return 1 if colliding else 0


if __name__ == "__main__":
    sys.exit(main())
