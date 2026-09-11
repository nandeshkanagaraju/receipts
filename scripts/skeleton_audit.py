"""scripts/skeleton_audit.py — rule 7 (near-copies) and GLOSSARY §6.2 (clarify terms).

Both are preconditions of `questions-frozen`, not always-on tests: they check the
corpus as a whole, and the corpus is not finished until it is frozen.

**Rule 7.** Two questions that differ only by a filter value, a window or a
currency are the same question asked twice. The audit masks those and compares
what is left.

**§6.2.** A term the glossary says must be clarified has no business in an ANS
question. The scan must not fire on *defined metric names* that happen to contain
such a word — "net revenue" is a metric, "revenue" alone is not.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
QDIR = REPO / "eval" / "questions"
SETS = ("dev", "eval", "holdout")

PLACE = re.compile(
    r"\b(Chennai|Coimbatore|Madurai|Velachery|Anna Nagar|Tamil Nadu|India|UK|Manchester"
    r"|UAE|Dubai|Singapore|Malaysia|USA|US|Kestrel Dubai Garden Road)\b"
)
WINDOW = re.compile(
    r"\b(yesterday|last week|last 7 days|last month|this month|last quarter|this quarter"
    r"|last 8 weeks|the 8 weeks before|the week before|this week so far|this month so far"
    r"|July|August|September)\b",
    re.I,
)
CURRENCY = re.compile(r"\bin (US dollars|rupees|pounds|ringgit|dirhams|Singapore dollars)\b", re.I)

# --------------------------------------------------------------------------- #
# Rule-7 exceptions. A collision is allowed ONLY with a written reason.
# --------------------------------------------------------------------------- #
SKELETON_EXCEPTIONS: dict[frozenset[str], str] = {
    frozenset({"EV-142", "HO-043", "HO-044"}): (
        "deny vs legitimate-zero vs calendar-ambiguous. EV-142 is a DENY: a UK role "
        "asking about Malaysia, refused before any metric resolves. HO-043 asks for "
        "EMI share in the UK, where EMI does not exist, so the correct answer is a "
        "legitimate zero rather than an error or an abstention. HO-044 asks for "
        "India 'last quarter', which is calendar-ambiguous under a fiscal year "
        "starting in April. The three share a surface shape and test three "
        "unrelated behaviours."
    ),
}

# --------------------------------------------------------------------------- #
# §6.2 terms, and the defined metric names that contain them
# --------------------------------------------------------------------------- #
CLARIFY_TERMS = ("revenue", "best", "top", "worst", "performance", "growth")
DEFINED_PHRASES = (
    "net revenue",  # §2.5
    "captured gmv",  # §2.3
    "gross revenue",
    "top 5",
    "top 10",
    "top-5",
    "top-10",
)
TOPK = re.compile(r"\btop \d+\b|\btop-\d+\b|\bwhich (five|ten|\d+)\b", re.I)


def load() -> dict[str, dict]:
    rows: dict[str, dict] = {}
    for s in SETS:
        p = QDIR / f"{s}.jsonl"
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                rows[r["qid"]] = r
    return rows


def skeleton(text: str) -> str:
    s = PLACE.sub("<P>", text)
    s = WINDOW.sub("<W>", s)
    s = CURRENCY.sub("<C>", s)
    s = s.lower()
    for w in (" the ", " our ", " showrooms", " showroom", " stores", " store"):
        s = s.replace(w, " ")
    return re.sub(r"[^a-z<>]+", " ", s).strip()


def skeleton_collisions(rows: dict[str, dict]) -> tuple[list[tuple], list[tuple]]:
    groups: dict[str, list[str]] = {}
    for qid, r in rows.items():
        groups.setdefault(skeleton(r["variants"]["en"]), []).append(qid)
    allowed, failing = [], []
    for shape, qids in sorted(groups.items()):
        if len(qids) < 2:
            continue
        key = frozenset(qids)
        (allowed if key in SKELETON_EXCEPTIONS else failing).append((shape, sorted(qids)))
    return allowed, failing


def clarify_hits(rows: dict[str, dict]) -> list[tuple[str, str, str]]:
    """ANS questions using a §6.2 term that is not part of a defined metric name."""
    hits = []
    for qid, r in sorted(rows.items()):
        if r["population"] != "ANS":
            continue
        en = r["variants"]["en"]
        low = en.lower()
        masked = low
        for phrase in DEFINED_PHRASES:
            masked = masked.replace(phrase, " ")
        masked = TOPK.sub(" ", masked)
        for term in CLARIFY_TERMS:
            if re.search(rf"\b{term}\b", masked):
                hits.append((qid, term, en))
    return hits


def duplicate_text(rows: dict[str, dict]) -> list[str]:
    counts = Counter(r["variants"]["en"] for r in rows.values())
    return [t for t, n in counts.items() if n > 1]


def main() -> int:
    rows = load()
    if not rows:
        print("no question files found", file=sys.stderr)
        return 1

    allowed, failing = skeleton_collisions(rows)
    hits = clarify_hits(rows)
    dupes = duplicate_text(rows)

    print(f"rule 7: {len(rows)} questions")
    print(f"  allowed collisions (with a written reason): {len(allowed)}")
    for _shape, qids in allowed:
        print(f"    {', '.join(qids)}")
        print(f"      reason: {SKELETON_EXCEPTIONS[frozenset(qids)][:96]}…")
    print(f"  unlisted collisions: {len(failing)}")
    for shape, qids in failing:
        print(f"    {', '.join(qids)}  shape: {shape}")
    print(f"  exact duplicate text: {len(dupes)}")

    print(f"\nGLOSSARY §6.2: {len(hits)} ANS question(s) using a clarify term")
    for qid, term, en in hits:
        print(f"    {qid} [{term}] {en}")

    problems = []
    if failing:
        problems.append(f"{len(failing)} unlisted rule-7 collision(s)")
    if dupes:
        problems.append(f"{len(dupes)} duplicated question text(s)")
    if hits:
        problems.append(f"{len(hits)} ANS question(s) using a §6.2 clarify term")
    if problems:
        print("\nFAIL: " + "; ".join(problems), file=sys.stderr)
        return 1
    print("\nall clear")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
