"""Write web/src/examples.ts from the frozen dev questions.

The demo answers recorded questions only: the replay key hashes the question
text, so an example that is not in `eval/recordings/receipts` returns 503. Typing
the examples by hand would let them drift from the recordings silently, and the
symptom would be a demo that fails on its own suggestions.

Run: `.venv/bin/python -m scripts.gen_web_examples`
"""

from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
QUESTIONS = REPO / "eval" / "questions" / "dev.jsonl"
TARGET = REPO / "web" / "src" / "examples.ts"
LANGS = ("en", "ta", "hi")

# Chosen because every one answers VERIFIED in all three languages, under the
# role that owns it. `admin` has no dev questions of its own and holds a
# superset of `global_finance`'s scope, so it borrows those.
PICK: dict[str, list[str]] = {
    "rm_tamil_nadu": ["DV-001", "DV-002", "DV-006"],
    "global_finance": ["DV-003", "DV-026", "DV-008"],
    "store_ops_uk": ["DV-004", "DV-007", "DV-024"],
    "admin": ["DV-003", "DV-026", "DV-008"],
}


def build() -> str:
    rows = {
        row["qid"]: row
        for row in (json.loads(line) for line in QUESTIONS.read_text(encoding="utf-8").splitlines())
    }
    picked = {
        role: {lang: [rows[qid]["variants"][lang] for qid in qids] for lang in LANGS}
        for role, qids in PICK.items()
    }
    listing = "\n".join(f"//   {role:<15}{' '.join(qids)}" for role, qids in sorted(PICK.items()))
    body = json.dumps(picked, ensure_ascii=False, indent=2, sort_keys=True)
    return (
        "// GENERATED from eval/questions/dev.jsonl by scripts/gen_web_examples.py.\n"
        "// Do not hand-edit: these are the exact recorded questions, and a question that\n"
        "// is not recorded cannot be answered in replay (see CatalogModeBanner copy).\n"
        "//\n"
        f"{listing}\n"
        "export const EXAMPLES: Record<string, Record<string, readonly string[]>> = "
        f"{body};\n"
    )


def main() -> None:
    TARGET.write_text(build(), encoding="utf-8")
    print(f"wrote {TARGET.relative_to(REPO)}")


if __name__ == "__main__":
    main()
