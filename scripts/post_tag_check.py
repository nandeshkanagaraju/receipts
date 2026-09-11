"""scripts/post_tag_check.py — [IO] rehearse the world a tag creates, before creating it.

A tag-conditioned guard is dormant until its tag exists. That means its first
real run happens in CI, immediately after the tag is pushed — at the point it is
most awkward to withdraw. It has already happened once here: the standing
`gen-frozen` check asserted gates that CI cannot evaluate, and went red on the
first push after the tag, on a machine where nothing was wrong.

So a freeze rehearses. Before creating a tag, the suite runs once in the state
the tag will produce, and the freeze refuses if anything fails:

- **the tag present** — `RECEIPTS_SIMULATED_TAGS` switches tag-conditioned guards
  on without touching git, so a failed rehearsal leaves nothing to undo.
- **`CI=true`** — CI is the environment the guard will actually wake up in.
- **the sealed files absent** — `RECEIPTS_SEALED_DIR` points at an empty
  directory. Nothing is deleted; the answers stay exactly where they are, and the
  suite simply cannot see them, which is CI's situation precisely.

The counts-only sealed marker is written from the *real* gate first, because that
is what the data job does before the test job runs. A rehearsal that skipped it
would prove the suite passes without the marker, which is the opposite of the
guarantee.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import freeze  # noqa: E402
import freeze_gen  # noqa: E402


def rehearse(tag: str, write_marker: bool = True) -> list[str]:
    """Run the suite as it will run once `tag` exists. Empty means go ahead."""
    if write_marker:
        line = freeze_gen.write_marker()
        if line != freeze_gen.expected_marker():
            return [
                f"the sealed marker reads {line!r}, not {freeze_gen.expected_marker()!r}; "
                "the rehearsal would be checking a gate that is already failing"
            ]

    with tempfile.TemporaryDirectory(prefix="sealed-absent-") as empty:
        env = dict(os.environ)
        env["CI"] = "true"
        env[freeze.SEALED_DIR_ENV] = empty
        simulated = [t for t in (env.get("RECEIPTS_SIMULATED_TAGS", ""), tag) if t]
        env["RECEIPTS_SIMULATED_TAGS"] = ",".join(simulated)
        out = subprocess.run(
            [sys.executable, "-m", "pytest", "-o", "addopts=", "-q"],
            cwd=REPO,
            env=env,
            capture_output=True,
            text=True,
        )

    if out.returncode == 0:
        return []
    failures = [ln.strip() for ln in out.stdout.splitlines() if ln.startswith("FAILED")]
    return [
        f"the suite fails once {tag} exists ({len(failures) or 'unknown'} test(s)). "
        "The tag is not created; fix these first, then freeze:"
    ] + [f"  {f}" for f in failures[:10]]


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("tag", help="the tag whose post-creation world to rehearse")
    ap.add_argument(
        "--no-marker",
        action="store_true",
        help="do not write the sealed marker first (the rehearsal then requires one already there)",
    )
    args = ap.parse_args(argv)

    problems = rehearse(args.tag, write_marker=not args.no_marker)
    if problems:
        print(f"REFUSING: the post-{args.tag} rehearsal failed.", file=sys.stderr)
        for p in problems:
            print(f"  {p}", file=sys.stderr)
        return 1
    print(f"post-{args.tag} rehearsal passed: the suite is green in the world the tag makes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
