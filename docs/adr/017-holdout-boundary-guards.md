# ADR-017: the holdout boundary is guarded in four layers, none of them a wall

**Status** Accepted
**Date** 2026-09-12

## Decision

The holdout questions and their reference SQL are readable by exactly one
context — the isolated reference run (`docs/ISOLATED_REFERENCE_RUN.md`) — and the
boundary is enforced by four independent layers, landed in `835eff8` and the
commit that carries this ADR:

1. **Deny rules** (`.claude/settings.json`) — the `Read` tool and the obvious
   `cat`/`head`/`tail` spellings, for `eval/sealed/**`,
   `eval/questions/holdout*` and `eval/reference_sql/HO-*`.
2. **A `PreToolUse` hook** (`.claude/hooks/deny_sealed_history.py`) — the
   spellings a prefix deny cannot express: reading a path out of an old commit,
   patch output, `cat-file`, `blame`, `grep`, a `sed` range, a copy. It judges
   one shell segment at a time and strips heredoc bodies, so discussing the rule
   is not violating it.
3. **`.gitattributes -diff`** — git never *renders* holdout content, so a merge
   commit, a PR page or a `git log -p` over a wide range cannot volunteer what
   nobody asked for.
4. **Counts-only reporting** — the scans over holdout rows report how many, never
   which, and a charter test drives each scan to a real failure and asserts the
   output carries no qid, no question sentence and no place term.

Two exemptions are deliberate and tested in both directions:

- **`eval/reference_sql/HO_MANIFEST.json` is readable.** It is the one channel
  out of the isolated run — counts, hashes, booleans, no values and no SQL — and
  the main session and the freeze gates are supposed to read it. The exemption is
  anchored, so `HO_MANIFEST.json.bak` is not the manifest.
- **`.isolated-run` lifts the holdout half of the hook**, and never `.env` or
  `eval/sealed/**`. One session must read the holdout questions to write their
  reference SQL; no session ever needs the seed or the sealed answers.

## Why

Because each layer fails in a way the others do not. The deny rules cannot see a
path inside a subcommand. The hook cannot see what git prints unbidden. Neither
can stop a count from naming a row. And `-diff` protects a review, not a request.

The failure mode this ADR is really about is the quiet one. Every layer here was
added after something passed that should not have: a gate that was never called,
a scan that asserted `offending == 0` having read nothing, a guard that matched
its own marker, a manifest blocked along with the answer key. The pattern is
consistent enough to state — **a guard's logic gets tested and its reachability
does not** — and it is why each layer carries an injection, a meta, and a
reachability check rather than only the first.

## What this is not

**None of it is a wall.** The lift is one `touch` away, `git show <sha>:<path>`
still works, and every file involved is tracked in a public repository. A session
holding the working tree can read anything in it.

What the layers buy is that **crossing leaves a trace**: the marker sits in the
working tree until removed, the relaxed deny list is a tracked file a reviewer
can diff, and `test_isolated_lift_does_not_travel` fails if that list ever
reaches `main` — the one crossing that would unblind every future session with
nothing in a later diff to show it.

The control was never secrecy from the world, which a public repository cannot
offer. It is that the *build* context never held the holdout, and that if it ever
does, someone can tell.

## Consequences

- The isolated session's hand-back points here, and so does the G5 report: a
  reader asking "was this holdout really blind?" gets the honest answer,
  including the parts that are advisory.
- `LIMITATIONS.md` carries the same claim in the negative — the lift is one
  `touch` away, it is a tripwire rather than a wall — so the weakness is recorded
  where the weaknesses are, not only where the guards are.
- A future layer is added the same way or not at all: injection, meta,
  reachability. A guard whose reachability is not asserted is assumed absent.
