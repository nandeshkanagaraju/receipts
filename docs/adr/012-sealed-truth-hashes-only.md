# ADR-012: `eval/sealed/` stays untracked; the freeze records hashes only

**Status** Accepted
**Date** 2026-09-11

## Decision

`eval/sealed/` is not committed. At `gen-frozen` the freeze manifest records a
**SHA-256 per file** in that directory and nothing else — never contents. The
files and the seed are published at G5, after the holdout has run once.

## Why

Committing sealed truth puts the holdout's answers in the repository's permanent
history, where nothing can remove them. Recording their hashes proves the files
did not change without ever revealing what they say.

## Context

SDD §3 lists `eval/sealed/` in the repository layout, which reads as an
instruction to commit it. `.gitignore` treats generator output — `data/`,
`truth/` — as rebuildable and excluded. `eval/sealed/holdout_anomalies.json` is
both: it is generator output, and it is the one artifact whose contents must not
be known while the system is being built. The two conventions point in opposite
directions, so this ADR settles it rather than leaving the next person to guess.

Committing it would mean the sealed parameters are readable by anyone with
repository access, permanently, and removing them later means rewriting history.
The harness deny rules in `.claude/settings.json` stop an assistant reading the
file, but they do not stop `git log -p` from containing it forever.

Leaving it out has a real cost, and it is the reason this is a decision rather
than an obvious call: the file must survive unchanged until G5, which means the
seed in `.env` must survive too. Lose the seed and the sealed anomalies change,
and the holdout is no longer the thing that was sealed.

The hash is what closes that gap. A recorded SHA-256 cannot reconstruct the
parameters, but it can prove at G5 that the file scored against is the file that
was sealed. If the hash does not match, the holdout result is void and we say so
rather than publishing a number we cannot stand behind.

## Consequences

- `scripts/freeze.py` records `sealed_files: {path: sha256}` when the directory
  is present, and a freeze test recomputes them.
- The absence of `eval/sealed/` on a fresh clone is **not** an error: it is
  generator output. The freeze test checks hashes only when the files exist.
- `LIMITATIONS.md` and `docs/M2_NOTES.md` record the G5 publication step, so the
  commitment to publish is written down before there is any incentive not to.
- If the seed is lost before G5, the holdout cannot be run as sealed. That is a
  real single point of failure and is recorded as such.
