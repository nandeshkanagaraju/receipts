"""The PreToolUse hook refuses commands that would display sealed truth.

The deny list in `.claude/settings.json` covers `Read` and the obvious
`cat`/`head`/`tail` spellings. It cannot cover
`git show <sha>:eval/sealed/holdout_why.jsonl`, because the path is an argument
to a subcommand and a prefix deny would have to ban `git show` outright. That
gap is not academic: the compromised sealed set is still reachable in the public
history of this repository, so a guard over the working copy alone guards
nothing.

These are unit tests over the hook's decision function. They assert both
directions -- that the revealing spellings are refused, and that the commands
the work actually needs (names, index state, hashing) still run. A guard that
blocks `git ls-files` gets switched off, and then it blocks nothing.

Writing this file was itself the first end-to-end proof: the hook refused the
shell heredoc that would have created it, because the command text quoted the
commands below.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
HOOK = REPO / ".claude" / "hooks" / "deny_sealed_history.py"
sys.path.insert(0, str(REPO / ".claude" / "hooks"))
import deny_sealed_history as hook  # noqa: E402

SEALED = "eval/sealed/holdout_why.jsonl"
ANOM = "eval/sealed/holdout_anomalies.json"
HOLDOUT = "eval/questions/holdout.jsonl"

REFUSED = [
    f"git show 6e2bc38:{SEALED}",
    f"git show e41df75:{ANOM}",
    "git log -p -- eval/sealed/",
    f"git log --patch -- {HOLDOUT}",
    f"git diff HEAD -- {HOLDOUT}",
    f"git cat-file -p HEAD:{SEALED}",
    "git grep seed -- eval/sealed/",
    f"git blame {HOLDOUT}",
    "cat .env",
    f"head -5 {SEALED}",
    f"sed -n '1,3p' {SEALED}",
    f"xxd {ANOM}",
    f"cp {SEALED} /tmp/x",
]

ALLOWED = [
    "git ls-files eval/sealed/",
    f"git check-ignore -v {SEALED}",
    f"git rm --cached {SEALED}",
    "git add -f eval/sealed/_injection_probe.jsonl",
    "git log --oneline -- eval/sealed/",
    "git status --porcelain",
    "python -c \"import hashlib,pathlib;hashlib.sha256(pathlib.Path('x').read_bytes())\"",
    "git diff --stat kestrel_gen/",
    "git show HEAD:kestrel_gen/sealed.py",
    "make data",
    # A commit message may quote the spellings the hook forbids. Matching a verb
    # inside a message is a false positive; this one refused three commits while
    # the rule was being written.
    f'git commit -m "untrack {SEALED}; git show could still read it"',
    "git tag -a gen-frozen -m 'sealed hashes recorded, eval/sealed untracked'",
    "git push origin main --tags",
]


@pytest.mark.parametrize("command", REFUSED)
def test_revealing_commands_are_refused(command: str) -> None:
    assert hook.verdict(command) is not None, f"not refused: {command}"


@pytest.mark.parametrize("command", ALLOWED)
def test_the_work_still_runs(command: str) -> None:
    assert hook.verdict(command) is None, f"wrongly refused: {command}"


def test_the_exemption_does_not_leak_into_the_displaying_verbs() -> None:
    """`git commit` is exempt; `git show` is not, however the command is spelled.

    The exemption is anchored to the start of the command, so it cannot be
    reached by prefixing a blocked command with a permitted one.
    """
    assert hook.verdict(f"git show HEAD:{SEALED}") is not None
    assert hook.verdict(f"git commit -m x && git show HEAD:{SEALED}") is not None, (
        "a blocked command was smuggled in behind an exempt one"
    )


def test_the_refusal_explains_what_is_allowed_instead() -> None:
    message = hook.verdict(f"git show HEAD:{SEALED}")
    assert message and "hash" in message.lower(), (
        "the refusal does not say what to do instead, so it reads as an obstacle"
    )


def test_the_hook_exits_2_end_to_end() -> None:
    """Exit 2 is what the harness reads as `refuse`; 0 would let it through."""
    payload = {"tool_name": "Bash", "tool_input": {"command": f"git show HEAD:{SEALED}"}}
    out = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
    )
    print(f"\nhook exit={out.returncode}")
    assert out.returncode == 2, "the hook did not refuse"
    assert "Refused" in out.stderr


def test_the_hook_ignores_other_tools() -> None:
    payload = {"tool_name": "Grep", "tool_input": {"pattern": "eval/sealed"}}
    out = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
    )
    assert out.returncode == 0, "the hook fired on a non-Bash tool"


def test_settings_wires_the_hook_in() -> None:
    """A hook nothing calls is a file, not a control."""
    settings = json.loads((REPO / ".claude" / "settings.json").read_text(encoding="utf-8"))
    wired = json.dumps(settings.get("hooks", {}))
    assert "deny_sealed_history" in wired, ".claude/settings.json does not call the hook"
    assert HOOK.exists(), "settings references a hook that is not there"


# ---------------------------------------------------------------------------
# The isolated-run lift (docs/ISOLATED_REFERENCE_RUN.md).
#
# `.isolated-run` lifts the holdout family and never the sealed one. The
# asymmetry is the design: one session must read the holdout questions to write
# their reference SQL, and no session ever needs the seed or the answers.
# ---------------------------------------------------------------------------

HOLDOUT_READS = (
    "cat eval/questions/holdout.jsonl",
    "head -3 eval/reference_sql/HO-012.sql",
    "grep refund eval/questions/holdout_blind.jsonl",
)
NEVER_LIFTED = (
    "cat .env",
    "cat eval/sealed/holdout_why.jsonl",
    "head -1 eval/sealed/holdout_anomalies.json",
    f"git show HEAD:{SEALED}",
)


@pytest.mark.parametrize("command", HOLDOUT_READS)
def test_meta_without_the_marker_the_holdout_is_refused(command: str, tmp_path: Path) -> None:
    """Marker absent: the lift is not simply always on."""
    assert hook.verdict(command, repo=tmp_path) is not None, (
        f"not refused without a marker: {command}"
    )


@pytest.mark.parametrize("command", HOLDOUT_READS)
def test_reachability_with_the_marker_the_holdout_is_permitted(
    command: str, tmp_path: Path
) -> None:
    """Marker present: the read goes through.

    Asserted by invoking the hook against a tree that has the marker, not by
    reasoning about the pattern lists. A lift nobody can demonstrate is a lift
    the isolated session will discover does not work, at the wall.
    """
    (tmp_path / hook.MARKER).write_text("", encoding="utf-8")
    assert hook.verdict(command, repo=tmp_path) is None, (
        f"the marker is present and this was still refused: {command}"
    )


@pytest.mark.parametrize("command", NEVER_LIFTED)
def test_injection_the_marker_does_not_lift_the_seed_or_the_sealed_answers(
    command: str, tmp_path: Path
) -> None:
    """INJECTION: marker present, and these must still be refused."""
    (tmp_path / hook.MARKER).write_text("", encoding="utf-8")
    message = hook.verdict(command, repo=tmp_path)
    print(f"\nmarker present, {command[:40]!r} -> {'refused' if message else 'ALLOWED'}")
    assert message is not None, (
        f"the isolated-run marker lifted a guard it must never lift: {command}"
    )


def test_the_marker_is_not_present_in_this_tree() -> None:
    """This session is not the isolated one, and the suite should say so."""
    assert not hook.isolated(), (
        "`.isolated-run` exists in this working tree. If this is the isolated "
        "session that is expected; if it is not, the holdout guard is lifted."
    )


def test_the_hook_end_to_end_honours_the_marker(tmp_path: Path) -> None:
    """Exit 2 without the marker, exit 0 with it, same command, same process."""
    fake_repo = tmp_path / "repo" / ".claude" / "hooks"
    fake_repo.mkdir(parents=True)
    shim = tmp_path / "drive.py"
    shim.write_text(
        "import json, sys\n"
        f"sys.path.insert(0, {str(HOOK.parent)!r})\n"
        "import deny_sealed_history as h\n"
        "from pathlib import Path\n"
        f"repo = Path({str(tmp_path / 'repo')!r})\n"
        "marker = repo / h.MARKER\n"
        "before = h.verdict('cat eval/questions/holdout.jsonl', repo=repo) is not None\n"
        "marker.write_text('')\n"
        "after = h.verdict('cat eval/questions/holdout.jsonl', repo=repo) is not None\n"
        "print(f'{before} {after}')\n",
        encoding="utf-8",
    )
    out = subprocess.run([sys.executable, str(shim)], capture_output=True, text=True)
    print(f"\nrefused before marker / after marker: {out.stdout.strip()}")
    assert out.stdout.strip() == "True False", (
        f"the marker did not change the verdict end to end: {out.stdout!r} {out.stderr}"
    )
