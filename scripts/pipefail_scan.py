"""scripts/pipefail_scan.py — [pure] find pipelines whose exit code cannot be trusted.

A shell pipeline reports the exit status of its **last** stage. So

    python -m scripts.double_compute | tail -40

exits 0 when the script dies, and the run looks successful. It did: thirteen
minutes, no output file, and the failure was noticed only because a timestamp had
not moved (HANDOFF §4.11).

`set -o pipefail` makes the pipeline report the first non-zero stage instead. This
scans the shell this repository actually ships — `Makefile` recipes,
`scripts/*.sh`, and `run:` blocks in `.github/workflows/*.yml` — and reports any
multi-command pipeline in a block that never sets it.

Deliberately not flagged, because the exit code genuinely does not matter or is
already guarded:

- a pipeline inside `$(...)` or backticks whose *output* is the value being used,
  and which is not the whole command;
- a pipeline whose stages are all pure text filters over a literal (`echo x | tr`);
- anything in a block that sets `pipefail`, however it is spelled.

The scan is textual and deliberately conservative: it can miss, and it should
never invent. A missed pipeline is the status quo; a false positive teaches people
to ignore it.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

PIPEFAIL = re.compile(r"set\s+-[a-z]*o?\s*pipefail|set\s+-o\s+pipefail|SHELLOPTS.*pipefail", re.I)

# Stages that cannot fail in a way anybody cares about: the pipeline exists to
# format or truncate, and its own exit code is the point of the pipe.
PURE_FILTERS = {
    "tail",
    "head",
    "wc",
    "sort",
    "uniq",
    "tr",
    "cut",
    "column",
    "fmt",
    "nl",
    "tee",
    "cat",
    "sed",
    "awk",
    "grep",
    "rev",
    "paste",
    "fold",
    "expand",
}
# Sources that cannot meaningfully fail: the pipeline's first stage is a literal.
# `echo hello | tr a-z A-Z` has no exit code worth protecting.
PURE_SOURCES = {"echo", "printf", "true", "false", ":", "yes"}

# Commands whose failure is the thing being tested, inside an `if` or `||`.
GUARDED = re.compile(r"^\s*(?:if|while|until)\b|\|\||&&\s*$|\btrue\b\s*$")


def pipelines(block: str) -> list[str]:
    """Lines in a shell block that contain a real pipeline."""
    found = []
    for raw in block.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # Strip the pipe used by `|` in a case pattern or a regex alternation.
        without_or = re.sub(r"\|\|", " ", line)
        if "|" not in without_or:
            continue
        found.append(line)
    return found


def first_stage_is_pure(line: str) -> bool:
    """The first stage is a text filter or a literal source.

    Only the *first* stage is considered, and that is the conservative choice:
    `git log --oneline | head -5` is flagged, because git can fail and the pipe
    would hide it. In a Makefile recipe that failure is small, but the fix is one
    line and the alternative is a scan that reasons about which failures matter.
    """
    head = re.sub(r"^\s*[-@]?\s*", "", line).split("|")[0].strip()
    first_word = head.split()[0] if head.split() else ""
    name = Path(first_word).name
    return name in PURE_FILTERS or name in PURE_SOURCES


def offenders_in(block: str, label: str) -> list[str]:
    if PIPEFAIL.search(block):
        return []
    out = []
    for line in pipelines(block):
        if first_stage_is_pure(line) or GUARDED.search(line):
            continue
        out.append(f"{label}: {line[:96]}")
    return out


def makefile_blocks(repo: Path = REPO) -> list[tuple[str, str]]:
    path = repo / "Makefile"
    if not path.exists():
        return []
    blocks: list[tuple[str, str]] = []
    target = "?"
    body: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if re.match(r"^[A-Za-z0-9_.-]+:", line):
            if body:
                blocks.append((f"Makefile:{target}", "\n".join(body)))
            target, body = line.split(":", 1)[0], []
        elif line.startswith("\t"):
            body.append(line)
    if body:
        blocks.append((f"Makefile:{target}", "\n".join(body)))
    return blocks


def workflow_blocks(repo: Path = REPO) -> list[tuple[str, str]]:
    """Every `run:` block in every workflow, inline or literal.

    Line-based on purpose. The first version sliced the file after a regex match
    and silently produced empty bodies -- a parser that finds a block and reads
    nothing out of it reports no problems and looks like a clean scan, which is
    the worst failure available to a checker.
    """
    blocks: list[tuple[str, str]] = []
    for path in sorted((repo / ".github" / "workflows").glob("*.yml")):
        lines = path.read_text(encoding="utf-8").splitlines()
        i = 0
        while i < len(lines):
            match = re.match(r"^(\s*)(?:-\s+)?run:\s*(\|[-+]?)?\s*(.*)$", lines[i])
            if not match:
                i += 1
                continue
            indent, literal, inline = match.groups()
            if not literal:
                if inline.strip():
                    blocks.append((f"{path.name}:run", inline))
                i += 1
                continue
            body: list[str] = []
            i += 1
            while i < len(lines):
                line = lines[i]
                if line.strip() and not line.startswith(indent + " "):
                    break
                body.append(line)
                i += 1
            blocks.append((f"{path.name}:run", "\n".join(body)))
    return blocks


def script_blocks(repo: Path = REPO) -> list[tuple[str, str]]:
    return [
        (str(p.relative_to(repo)), p.read_text(encoding="utf-8"))
        for p in sorted((repo / "scripts").glob("*.sh"))
    ]


def scan(repo: Path = REPO) -> list[str]:
    problems: list[str] = []
    for label, block in makefile_blocks(repo) + script_blocks(repo) + workflow_blocks(repo):
        problems.extend(offenders_in(block, label))
    return problems


def main() -> int:
    problems = scan()
    if problems:
        print(f"{len(problems)} pipeline(s) whose exit code cannot be trusted:")
        for p in problems:
            print(f"  {p}")
        print("\nAdd `set -o pipefail` to the block, or check the exit code explicitly.")
        return 1
    print("no unguarded pipelines in Makefile recipes, scripts/*.sh or CI run blocks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
