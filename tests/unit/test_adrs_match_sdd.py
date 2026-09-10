"""Every ADR in SDD §2 exists on disk and states the same decision.

Not required by M0, but the ADR table and the ADR files are another pair of
independent statements: if §2 changes and the file does not, the drift is silent.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ADR_DIR = REPO / "docs" / "adr"


def sdd_rows() -> dict[str, tuple[str, str]]:
    sdd = (REPO / "docs" / "SDD.md").read_text(encoding="utf-8")
    sec = re.search(r"## 2\. Architecture decisions(.*?)^## 3\.", sdd, re.S | re.M)
    assert sec, "SDD §2 not found"
    rows: dict[str, tuple[str, str]] = {}
    for line in sec.group(1).splitlines():
        m = re.match(r"^\|\s*(\d{3})\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*$", line)
        if m:
            rows[m.group(1)] = (m.group(2), m.group(3))
    return rows


def _section(text: str, heading: str) -> str:
    m = re.search(rf"^## {heading}\n\n(.+?)(?=\n## |\Z)", text, re.S | re.M)
    assert m, f"ADR is missing a '{heading}' section"
    return m.group(1).strip()


def test_every_sdd_adr_has_a_file_stating_the_same_decision() -> None:
    rows = sdd_rows()
    assert rows, "precondition: SDD §2 parsed to nothing"
    files = {p.name[:3]: p for p in ADR_DIR.glob("[0-9][0-9][0-9]-*.md") if p.name[:3] != "000"}

    print(f"\nSDD §2 lists {len(rows)} ADRs; docs/adr holds {len(files)} numbered files")
    missing = sorted(set(rows) - set(files))
    assert not missing, f"ADRs in SDD §2 with no file: {missing}"

    for num in sorted(rows):
        decision, why = rows[num]
        text = files[num].read_text(encoding="utf-8")
        found = _section(text, "Decision")
        assert found == decision, (
            f"ADR-{num} Decision differs from SDD §2:\n  file: {found}\n  sdd:  {decision}"
        )
        assert _section(text, "Why") == why, f"ADR-{num} Why differs from SDD §2"
        print(f"  ADR-{num}: {decision[:64]}…")


def test_template_exists() -> None:
    assert (ADR_DIR / "000-template.md").exists(), "docs/adr/000-template.md is missing"
