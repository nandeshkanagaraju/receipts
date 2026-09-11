"""The holdout answer key is unreadable from this build context.

M3 writes `eval/reference_sql/<qid>.sql` for every ANS and LIVE question. For
dev and eval that is ordinary work. For the holdout it is not: a reference query
restates its question — metric, numerator and denominator, date key, window,
scope, currency, exclusions — in a form *more* precise than the English. Reading
the answer key is reading the question, and then the semantic layer, the
glossary and the synonym lists get written by someone who cannot un-know what
the holdout needed. That is the leak the holdout exists to exclude, and it is
invisible afterwards.

So the holdout reference SQL is written by an isolated session
(`docs/ISOLATED_REFERENCE_RUN.md`) and blocked here. Two controls, because
neither is sufficient alone:

1. **Deny rules** in `.claude/settings.json` — the `Read` tool and the obvious
   Bash spellings, mirroring what already exists for `eval/questions/holdout*`.
   A prefix deny cannot express the rest.
2. **The `PreToolUse` hook** — `git show HEAD:eval/reference_sql/HO-001.sql`,
   and the wildcard `cat eval/reference_sql/*.sql`, which names no holdout file
   and would display all of them.

The files are tracked in git, exactly as `eval/questions/holdout.jsonl` already
is. The claim is not secrecy from the world — a public repository cannot offer
that — but that the *build* context never held them, and that reaching them is
a deliberate act that leaves a trace.

**The block exists before the files do.** That ordering is the whole control: a
rule added after the first HO file lands has a window in it, and the window is
exactly when the file is new and interesting.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
HOOK = REPO / ".claude" / "hooks" / "deny_sealed_history.py"
SETTINGS = REPO / ".claude" / "settings.json"
sys.path.insert(0, str(REPO / ".claude" / "hooks"))
import deny_sealed_history as hook  # noqa: E402

HO = "eval/reference_sql/HO-001.sql"
HOB = "eval/reference_sql/HO-B07.sql"
DV = "eval/reference_sql/DV-001.sql"
EV = "eval/reference_sql/EV-017.sql"


# ---------------------------------------------------------------------------
# The hook
# ---------------------------------------------------------------------------

REFUSED = [
    f"cat {HO}",
    f"cat ./{HO}",
    f"head -20 {HO}",
    f"tail -5 {HOB}",
    f"sed -n '1,10p' {HO}",
    f"awk '{{print}}' {HO}",
    f"grep -i sum {HO}",
    f"rg captured {HO}",
    f"xxd {HO}",
    f"cp {HO} /tmp/x.sql",
    # History. The deny list cannot see a path that is an argument to a
    # subcommand, which is the entire reason the hook exists.
    f"git show HEAD:{HO}",
    f"git show 3677b05:{HOB}",
    f"git diff HEAD -- {HO}",
    "git log -p -- eval/reference_sql/HO-001.sql",
    f"git cat-file -p HEAD:{HO}",
    "git grep captured -- eval/reference_sql/HO-001.sql",
    f"git blame {HO}",
    # The wildcard cases: no holdout file is named, every one is displayed.
    "cat eval/reference_sql/*.sql",
    "cat eval/reference_sql/*",
    "grep -r rate eval/reference_sql/",
    "head -3 eval/reference_sql/*.sql",
    # Mixed: a permitted file first does not launder the rest of the argv.
    f"cat {DV} {HO}",
]

ALLOWED = [
    # This session's own work. A guard that blocks it is a guard someone
    # switches off, and then it blocks nothing.
    f"cat {DV}",
    f"cat ./{DV}",
    f"head -20 {EV}",
    f"sed -n '1,5p' {DV}",
    f"grep -c sum {EV}",
    "cat eval/reference_sql/DV-001.sql eval/reference_sql/EV-017.sql",
    # Names and index state, for either session.
    "ls eval/reference_sql/",
    "ls -la eval/reference_sql/",
    "git ls-files eval/reference_sql/",
    "git status --porcelain eval/reference_sql/",
    f"git add {HO}",
    "git log --oneline -- eval/reference_sql/",
    # Counts and hashes. ADR-012's whole posture: record the hash, not the file.
    f"sha256sum {HO}",
    f"wc -l {HO}",
    "wc -l eval/reference_sql/*.sql",
    f'git commit -m "add {HO}; a cat of it is refused"',
]


@pytest.mark.parametrize("command", REFUSED)
def test_the_hook_refuses_reading_the_holdout_answer_key(command: str) -> None:
    assert hook.verdict(command) is not None, f"not refused: {command}"


@pytest.mark.parametrize("command", ALLOWED)
def test_the_hook_leaves_dev_eval_names_and_hashes_alone(command: str) -> None:
    assert hook.verdict(command) is None, f"wrongly refused: {command}"


def test_the_refusal_names_the_answer_key() -> None:
    """A refusal that does not say why reads as a bug, and gets worked around."""
    message = hook.verdict(f"cat {HO}")
    assert message is not None
    print(f"\nrefusal message:\n{message}")
    assert "reference_sql" in message, "the refusal does not mention the answer key"
    assert "hash" in message.lower(), "the refusal does not say what is allowed instead"


# ---------------------------------------------------------------------------
# Fault injection and meta-test (HANDOFF §4.2: a guard is not done until an
# injection makes it fire AND the same injection passes with the guard off).
# ---------------------------------------------------------------------------

HO_PATTERN = re.compile(r"eval/reference_sql/", re.I)

INJECTIONS = [
    f"cat {HO}",
    f"git show HEAD:{HOB}",
    "cat eval/reference_sql/*.sql",
]


@pytest.mark.parametrize("command", INJECTIONS)
def test_injection_a_read_of_the_answer_key_fires_the_guard(command: str) -> None:
    """INJECTION: three ways to put holdout reference SQL on the terminal."""
    message = hook.verdict(command)
    print(f"\ninjection {command!r} -> {'REFUSED' if message else 'allowed'}")
    assert message is not None, f"the guard did not fire on: {command}"


@pytest.mark.parametrize("command", INJECTIONS)
def test_meta_with_the_reference_pattern_withdrawn_the_injection_passes(
    command: str,
) -> None:
    """META: the refusal comes from the new rule, not from something else.

    Withdraw only the `eval/reference_sql/` pattern and keep the rest. If these
    commands were still refused, the test above would be proving nothing about
    the rule this module adds.
    """
    without = tuple(p for p in hook.PROTECTED if not HO_PATTERN.search(p.pattern))
    assert len(without) == len(hook.PROTECTED) - 1, (
        "expected exactly one reference_sql pattern to withdraw; "
        f"{len(hook.PROTECTED) - len(without)} matched"
    )
    message = hook.verdict(command, protected=without)
    print(f"\nmeta (rule off) {command!r} -> {'REFUSED' if message else 'allowed'}")
    assert message is None, (
        f"still refused with the rule withdrawn, so the rule is not what refuses: {command}"
    )


def test_meta_withdrawing_the_rule_does_not_unblock_the_sealed_paths() -> None:
    """The withdrawal is surgical: the older guards keep working without it."""
    without = tuple(p for p in hook.PROTECTED if not HO_PATTERN.search(p.pattern))
    for command in (
        "cat eval/sealed/holdout_anomalies.json",
        "cat eval/questions/holdout.jsonl",
        "cat .env",
    ):
        assert hook.verdict(command, protected=without) is not None, (
            f"withdrawing the reference rule disabled an unrelated guard: {command}"
        )


# ---------------------------------------------------------------------------
# Reachability: the guard is wired in, not merely correct.
#
# Two §6.2 gates were once written, tested in isolation, reported as wired in,
# and never called. A gate nobody calls cannot fail.
# ---------------------------------------------------------------------------


def test_reachability_the_hook_refuses_end_to_end_with_exit_2() -> None:
    """Exit 2 is what the harness reads as `refuse`. 0 lets the call through."""
    payload = {"tool_name": "Bash", "tool_input": {"command": f"cat {HO}"}}
    out = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
    )
    print(f"\nhook subprocess exit={out.returncode}")
    assert out.returncode == 2, "the hook did not refuse the holdout answer key"
    assert "Refused" in out.stderr


def test_reachability_the_hook_is_still_wired_into_settings() -> None:
    settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
    wired = json.dumps(settings.get("hooks", {}))
    assert "deny_sealed_history" in wired, ".claude/settings.json does not call the hook"


def _deny_rules() -> list[str]:
    settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
    rules = settings["permissions"]["deny"]
    assert rules, "precondition: the deny list is empty, so the scan proves nothing"
    return [str(r) for r in rules]


def test_reachability_the_read_tool_is_denied_on_the_answer_key() -> None:
    rules = _deny_rules()
    reads = [r for r in rules if r.startswith("Read(") and "reference_sql/HO-" in r]
    print(f"\nRead deny rules for the answer key: {reads}")
    assert reads, (
        "no Read deny rule covers eval/reference_sql/HO-*. The hook only sees "
        "Bash; without this the Read tool opens the file directly."
    )


def _verbs_covered(needle: str, rules: list[str]) -> set[str]:
    """The leading Bash verb of every deny rule naming `needle`."""
    out = set()
    for rule in rules:
        if not rule.startswith("Bash(") or needle not in rule:
            continue
        body = rule[len("Bash(") : -1].strip()
        out.add(body.split()[0])
    return out


def test_reachability_bash_coverage_matches_the_holdout_questions() -> None:
    """Parity, so the two lists cannot drift apart.

    `eval/questions/holdout*` and `eval/reference_sql/HO-*` are the question and
    its answer key: protecting one and not the other protects neither. Asserting
    equality rather than a fixed list means a verb added to either side must be
    added to both, which is the failure this catches.
    """
    rules = _deny_rules()
    questions = _verbs_covered("eval/questions/holdout", rules)
    answers = _verbs_covered("eval/reference_sql/HO-", rules)
    print(f"\nverbs denied for holdout questions ({len(questions)}): {sorted(questions)}")
    print(f"verbs denied for the answer key   ({len(answers)}): {sorted(answers)}")
    assert questions, "precondition: no Bash deny rules for the holdout questions"
    missing = questions - answers
    assert not missing, (
        f"the answer key is readable by verbs the questions are protected from: {sorted(missing)}"
    )


def test_injection_a_settings_file_missing_the_rules_is_caught() -> None:
    """INJECTION: strip the answer-key rules; the parity check must notice.

    Operating on a copy of the real deny list, so this fails if the rules are
    removed from the real file for any reason — including a merge that drops them.
    """
    rules = _deny_rules()
    stripped = [r for r in rules if "reference_sql" not in r]
    removed = len(rules) - len(stripped)
    questions = _verbs_covered("eval/questions/holdout", rules)
    answers = _verbs_covered("eval/reference_sql/HO-", stripped)
    print(f"\ninjection: removed {removed} rule(s); uncovered verbs: {len(questions - answers)}")
    assert removed > 0, "precondition: there were no answer-key rules to remove"
    assert questions - answers, "stripping every answer-key rule left the check happy"
    assert not [r for r in stripped if r.startswith("Read(") and "reference_sql/HO-" in r]


# ---------------------------------------------------------------------------
# The isolated run's side of the contract.
# ---------------------------------------------------------------------------


def test_the_isolated_run_brief_exists_and_names_the_block() -> None:
    """The brief is what makes the block a workflow rather than an obstacle.

    Without a written route for the work the block prevents, the block is a
    thing to be switched off the first time someone needs an HO file.
    """
    brief = REPO / "docs" / "ISOLATED_REFERENCE_RUN.md"
    assert brief.exists(), "docs/ISOLATED_REFERENCE_RUN.md is missing"
    text = brief.read_text(encoding="utf-8")
    for needle in ("eval/reference_sql/HO-", "sha256", "eval/questions/holdout.jsonl"):
        assert needle in text, f"the brief never mentions {needle}"
    print(f"\nbrief: {len(text.splitlines())} lines")
