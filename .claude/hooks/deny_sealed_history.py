#!/usr/bin/env python3
"""PreToolUse hook — refuse any Bash command that would display sealed truth.

`.claude/settings.json` can deny `Read(./eval/sealed/**)` and the obvious
`cat`/`head`/`tail` spellings, but a deny list over command prefixes cannot see
`git show 6e2bc38:eval/sealed/holdout_why.jsonl`: the path is an argument to a
subcommand, and the interesting spellings are unbounded (`git log -p`,
`git diff`, `git cat-file -p`, `git grep`, `git blame`, a `sed -n` range, an
`xxd`). History is the specific gap -- the old sealed set is still reachable in
the public history of this repository, so blocking the working copy while
leaving `git show` open would block nothing at all.

So: block when a command names a protected path *and* uses a verb that puts file
contents on the terminal. Exit 2 tells the harness to refuse the call.

Deliberately still allowed, because they reveal nothing and the work needs them:

  - `git ls-files` / `git check-ignore` / `git add` / `git rm --cached`, which
    operate on names and index state.
  - hashing (`hashlib`, `sha256sum`), which reads bytes into a process without
    putting them in front of anyone. Recording hashes is the whole point of
    ADR-012.

This guard is about what reaches a transcript, not about what a process may open.

M3 adds a third protected path: `eval/reference_sql/HO-*`. The reference SQL for
a holdout question restates the question -- metric, window, scope, exclusions --
in a form that is *more* precise than the English, so reading the answer key is
reading the question. Those files are written by an isolated session (see
`docs/ISOLATED_REFERENCE_RUN.md`) and are tracked in git, exactly as
`eval/questions/holdout.jsonl` already is: the control here is not secrecy from
the world, which a public repository cannot offer, but that the *build* context
never held them.

The pattern deliberately protects the whole `eval/reference_sql/` directory
*except* `DV-` and `EV-` files, rather than just the `HO-` prefix. `cat
eval/reference_sql/*.sql` names no holdout file and would display all of them;
a guard that only knows the literal prefix would wave it through.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Never liftable. No marker, no flag, no argument: the seed and the sealed
# answers are not readable from this repository by anything, ever.
ALWAYS_PROTECTED = (
    re.compile(r"eval/sealed", re.I),
    re.compile(r"(?:^|[\s'\"/=])\.env\b", re.I),
)

# Liftable by the isolated-run marker. The holdout questions and their reference
# SQL have to be readable by exactly one session -- the one writing them -- and
# by nothing else. See docs/ISOLATED_REFERENCE_RUN.md.
LIFTABLE = (
    re.compile(r"eval/questions/holdout", re.I),
    # Everything under eval/reference_sql/ that is not demonstrably a dev or
    # eval file. A bare directory reference and any glob match; DV-*/EV-* do not.
    re.compile(r"eval/reference_sql/(?!(?:DV|EV)-)", re.I),
)

PROTECTED = ALWAYS_PROTECTED + LIFTABLE

# The marker is a file, not a flag, so lifting the guard leaves a trace in the
# working tree rather than in one invocation nobody reads back.
MARKER = ".isolated-run"


def isolated(repo: Path | None = None) -> bool:
    root = repo or Path(__file__).resolve().parents[2]
    return (root / MARKER).exists()


# Verbs that put file contents on the terminal.
REVEALING = (
    re.compile(r"\bgit\s+(?:-\S+\s+)*show\b", re.I),
    re.compile(r"\bgit\s+(?:-\S+\s+)*log\b(?=.*(?:\s-p\b|\s-u\b|--patch\b))", re.I),
    re.compile(r"\bgit\s+(?:-\S+\s+)*diff\b", re.I),
    re.compile(r"\bgit\s+(?:-\S+\s+)*cat-file\b", re.I),
    re.compile(r"\bgit\s+(?:-\S+\s+)*grep\b", re.I),
    re.compile(r"\bgit\s+(?:-\S+\s+)*blame\b", re.I),
    re.compile(r"\bgit\s+(?:-\S+\s+)*format-patch\b", re.I),
    re.compile(r"\bgit\s+(?:-\S+\s+)*archive\b", re.I),
    re.compile(r"\b(?:cat|bat|head|tail|less|more|nl|strings|xxd|od|hexdump)\b", re.I),
    re.compile(r"\bsed\b(?!.*-i\b)", re.I),
    re.compile(r"\bawk\b", re.I),
    re.compile(r"\bgrep\b", re.I),
    re.compile(r"\brg\b", re.I),
    re.compile(r"\bjq\b", re.I),
    re.compile(r"\bcp\b", re.I),  # copying it somewhere readable is the same leak
)


# Commands that record or transmit but never display file contents. Their
# argument text routinely *quotes* the spellings above -- a commit message
# describing this very rule matched `git show` and was refused three times while
# the rule was being written. Matching a verb inside a message is a false
# positive, and a guard that blocks writing the commit is a guard someone turns
# off. Note these are exempt from matching, not trusted with contents: none of
# them can put a sealed file on the terminal.
NON_DISPLAYING = re.compile(r"^\s*git\s+(?:commit|tag|push|fetch|add|rm)\b", re.I)

# `<<'TAG' ... TAG` and `<<TAG ... TAG`.
HEREDOC = re.compile(r"<<-?\s*['\"]?(\w+)['\"]?.*?^\1$", re.M | re.S)

# Shell separators. A command is judged one segment at a time, so an exempt verb
# cannot carry a blocked one behind it: `git commit -m x && git show …:<sealed>`
# is two segments and the second one is refused.
SEPARATORS = re.compile(r"&&|\|\||;|\||\n")


def segments(command: str) -> list[str]:
    """Split into shell segments, with heredoc bodies removed.

    A heredoc body is *content*, not a command. Writing a file that discusses
    `eval/sealed/` is not reading it, and treating the body as a command refused
    three legitimate calls while this rule was being written -- including the
    heredoc that would have created this hook's own tests.
    """
    return [s for s in SEPARATORS.split(HEREDOC.sub(" ", command)) if s.strip()]


def verdict(
    command: str,
    protected: tuple[re.Pattern[str], ...] | None = None,
    repo: Path | None = None,
) -> str | None:
    """Refusal message, or None to allow.

    `protected` is a parameter so a meta-test can withdraw one pattern and show
    the same command is then allowed -- proving the refusal comes from the rule
    rather than from something else in the command.

    When `.isolated-run` exists the holdout family is permitted and the sealed
    family is not. That asymmetry is the whole design: one session has to read
    the holdout questions in order to write their reference SQL, and no session
    ever has to read the seed or the sealed answers. The marker is a file so the
    lift leaves a trace; it is a tripwire, not a wall, and LIMITATIONS.md says so.
    """
    if protected is None:
        protected = ALWAYS_PROTECTED if isolated(repo) else PROTECTED
    for segment in segments(command):
        if NON_DISPLAYING.match(segment):
            continue
        if not any(p.search(segment) for p in protected):
            continue
        if any(verb.search(segment) for verb in REVEALING):
            return (
                "Refused: this command would display sealed or holdout content.\n"
                "eval/sealed/ holds the answers to the blind set, .env holds the "
                "seed, and eval/reference_sql/HO-* is the holdout answer key; the "
                "holdout is worth something only while nobody has read them "
                "(PDD §5).\n"
                "Names and hashes are fine: git ls-files, git check-ignore, "
                "sha256 of the file. Contents are not."
            )
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    if payload.get("tool_name") != "Bash":
        return 0
    command = str(payload.get("tool_input", {}).get("command", ""))
    message = verdict(command)
    if message is None:
        return 0
    print(message, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
