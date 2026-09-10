"""The checkout carries tags — in CI as well as on a developer's machine.

`freeze_questions.check_documents` chooses between its two branches by asking git
whether `questions-frozen` exists:

* **no tag** — the glossary is still a working document, an unrecorded hash is
  legitimate, and the guard reports clean;
* **tag** — the questions are frozen, so an unrecorded glossary means the
  reference SQL was written from a document that can still move, and the guard
  refuses.

A clone without tags answers "no" to every tag. The guard would then report clean
on a repository it should refuse, and it would do so **silently**, because that
is exactly what the legitimate pre-freeze case looks like. `actions/checkout`
clones shallow and tagless by default, so this is the normal state of a CI
checkout unless the workflow asks otherwise.

This is not hypothetical: run 34518669766 failed because a test borrowed
`specs-frozen` as a stand-in for a tag that exists, and in CI it did not. The
test was fixed to state the case; **this file makes sure the environment can
still answer the question**, so the production path is not quietly untested.

Every clone of this repository has `specs-frozen` — it is the G0 freeze tag — so
the assertion is the same everywhere and this file never skips.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
import freeze_questions as fq  # noqa: E402

SPECS_TAG = "specs-frozen"
ABSENT_TAG = "a-tag-this-repository-does-not-have"

SHALLOW = (
    f"`git tag -l {SPECS_TAG}` found nothing, so this checkout is shallow or "
    f"tagless and every tag-dependent guard in the repository is answering "
    f"'no tag' by default. In .github/workflows/ci.yml the `test` job's "
    f"actions/checkout step needs:\n"
    f"    with:\n"
    f"      fetch-tags: true\n"
    f"      fetch-depth: 0\n"
    f"Locally, `git fetch --tags` restores them."
)


def in_ci() -> bool:
    return os.environ.get("CI", "").lower() == "true"


def test_the_checkout_can_answer_a_tag_question() -> None:
    present = fq.tag_exists(SPECS_TAG)
    print(f"\nCI={in_ci()}  tag_exists({SPECS_TAG!r}) = {present}")
    assert present, ("running in CI: " if in_ci() else "") + SHALLOW


def test_tag_exists_says_no_to_a_tag_that_is_absent() -> None:
    """The precondition above means nothing if the helper answers yes to
    everything. It must distinguish, not merely respond."""
    assert not fq.tag_exists(ABSENT_TAG), f"{ABSENT_TAG!r} should not exist"
    print(f"tag_exists({ABSENT_TAG!r}) = False")


# --------------------------------------------------------------------------- #
# The real git-reading path, end to end. No injected `frozen`.
# --------------------------------------------------------------------------- #
def doc_repo(tmp_path: Path, section: dict | None) -> tuple[Path, Path]:
    """A repo copy of the question documents plus a manifest recording `section`."""
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    for rel in fq.QUESTION_DOCS:
        shutil.copy2(fq.REPO / rel, repo / rel)
    manifest = repo / "docs" / "FREEZE_MANIFEST.json"
    payload: dict = {"questions": {}}
    if section is not None:
        payload["question_documents"] = section
    manifest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return repo, manifest


def test_a_wrong_recorded_hash_is_caught_on_the_real_tag_path(tmp_path: Path) -> None:
    """INJECTION: record a hash that is not the document's, and read the tag from git."""
    wrong = "0" * 64
    repo, manifest = doc_repo(tmp_path, {**fq.document_digests(), "docs/GLOSSARY.md": wrong})

    problems = fq.check_documents(manifest, repo, tag=SPECS_TAG)
    print(f"\nwrong recorded hash, tag read from git -> {len(problems)} problem(s)")
    for p in problems:
        print(f"  {p}")
    assert problems, "a manifest recording the wrong glossary hash was accepted"
    assert any("GLOSSARY.md" in p for p in problems), f"refusal does not name the file: {problems}"


def test_the_same_manifest_recorded_correctly_is_clean(tmp_path: Path) -> None:
    """META for the injection above: the refusal comes from the hash, not the path."""
    repo, manifest = doc_repo(tmp_path, fq.document_digests())
    problems = fq.check_documents(manifest, repo, tag=SPECS_TAG)
    print(f"\ncorrect hashes, same code path -> {len(problems)} problem(s) — expected 0")
    assert not problems, problems


def test_an_unrecorded_glossary_is_refused_when_the_tag_really_exists(tmp_path: Path) -> None:
    """The branch the tag actually decides, exercised through git rather than a flag."""
    repo, manifest = doc_repo(tmp_path, None)
    problems = fq.check_documents(manifest, repo, tag=SPECS_TAG)
    print(f"\nunrecorded, {SPECS_TAG} exists -> {len(problems)} problem(s)")
    for p in problems:
        print(f"  {p}")
    assert problems, "a tagged repo with an unpinned glossary was accepted"
    assert SPECS_TAG in problems[0]


def test_meta_the_same_manifest_is_clean_when_the_tag_is_absent(tmp_path: Path) -> None:
    """META: swap the tag for one git does not have and the refusal disappears.

    This is what proves the two tests above went through git. If the branch were
    decided by anything else, this would still refuse.
    """
    repo, manifest = doc_repo(tmp_path, None)
    problems = fq.check_documents(manifest, repo, tag=ABSENT_TAG)
    print(f"\nunrecorded, {ABSENT_TAG!r} -> {len(problems)} problem(s) — expected 0")
    assert not problems, f"the guard refused without a tag to justify it: {problems}"
