"""receipts.llm.prompts — [IO] load `prompts/<id>.v<N>.md` and hash it (D15).

A prompt is a versioned file, not a string in the code. The version is in the
filename so a change is a new file rather than an edit, and the SHA-256 travels
with every call so a result can be traced to the exact bytes that produced it.

The hash is also part of the recording key (SDD §16). That is the property worth
stating plainly: **edit one character of a prompt and every recording made with
the old one stops matching.** Not "should be regenerated" -- stops matching, and
replay raises. A prompt edit that silently reused old recordings would produce a
run whose numbers belong to a prompt that no longer exists.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PROMPTS = REPO / "prompts"

NAME = re.compile(r"^(?P<id>[a-z0-9_.-]+)\.v(?P<version>\d+)\.md$")


class PromptError(FileNotFoundError):
    """A prompt that is missing, ambiguous, or misnamed."""


# A line that is exactly three hyphens separates a prompt file's documentation
# from the prompt itself. Everything above it explains the file to a person;
# everything below is sent to the model.
BODY_SEPARATOR = "---"


@dataclass(frozen=True)
class Prompt:
    prompt_id: str
    version: int
    sha256: str
    text: str
    path: Path

    @property
    def body(self) -> str:
        """The part meant for the model, with the file's own notes removed.

        The notes are not harmless. `planner.v1.md` opens by explaining that
        scope is recomputed server-side from the role -- a sentence about the
        architecture, written for a reader, and exactly the kind of thing the
        planner must never be told (D7). Sending a file's commentary to the model
        also spends tokens on text that describes the prompt instead of being it.

        `sha256` still covers the WHOLE file, and `text` still returns it. That
        is deliberate: the recording key is built from the sha (SDD §16), and
        changing what it covers would invalidate the 162 baseline recordings --
        which cannot be re-recorded without changing the measurement, since the
        model is not temperature-controllable (ADR-018). So the hash keeps
        identifying the file and the body is what travels.
        """
        lines = self.text.splitlines()
        for index, line in enumerate(lines):
            if line.strip() == BODY_SEPARATOR:
                return "\n".join(lines[index + 1 :]).strip()
        return self.text.strip()


def _candidates(prompt_id: str, directory: Path) -> list[tuple[int, Path]]:
    found: list[tuple[int, Path]] = []
    for path in sorted(directory.glob(f"{prompt_id}.v*.md")):
        match = NAME.match(path.name)
        if match and match.group("id") == prompt_id:
            found.append((int(match.group("version")), path))
    return sorted(found)


def load(prompt_id: str, *, version: int | None = None, directory: Path | None = None) -> Prompt:
    """The newest version of a prompt, or the one asked for.

    Raises when there is none. A missing prompt must not become an empty string:
    an empty system prompt is a different experiment, and it would run.
    """
    # Resolved at call time, not bound as a default. A default argument captures
    # the module attribute at import, so redirecting `PROMPTS` -- which a test
    # does, and a deployment could -- would have had no effect at all, silently.
    directory = PROMPTS if directory is None else directory
    if not directory.exists():
        raise PromptError(f"no prompts directory at {directory}")
    candidates = _candidates(prompt_id, directory)
    if not candidates:
        raise PromptError(f"no prompt file for {prompt_id!r} in {directory}")
    if version is None:
        chosen_version, path = candidates[-1]
    else:
        matches = [(v, p) for v, p in candidates if v == version]
        if not matches:
            available = [v for v, _ in candidates]
            raise PromptError(f"{prompt_id} has no v{version}; available: {available}")
        chosen_version, path = matches[0]
    text = path.read_text(encoding="utf-8")
    return Prompt(
        prompt_id=prompt_id,
        version=chosen_version,
        sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        text=text,
        path=path,
    )


def available(directory: Path | None = None) -> dict[str, list[int]]:
    """Every prompt id and the versions on disk."""
    directory = PROMPTS if directory is None else directory
    out: dict[str, list[int]] = {}
    if not directory.exists():
        return out
    for path in sorted(directory.glob("*.v*.md")):
        match = NAME.match(path.name)
        if match:
            out.setdefault(match.group("id"), []).append(int(match.group("version")))
    return {k: sorted(v) for k, v in sorted(out.items())}
