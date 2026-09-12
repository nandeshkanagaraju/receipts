"""receipts.language.lexicon — [IO] reads the romanised-word lists from disk.

This module exists because SDD §3 and SDD §9 cannot both be satisfied by one
file. §3 marks `language/detect.py` as **[P]**, pure, no I/O of any kind. §9
gives stage 1 a lexicon held in `language/lexicon/*.txt`. Reading a file is I/O
however small and however cached, and the charter guard said so the moment the
two were in the same module.

Detection is pure *given a lexicon*. So the lexicon is loaded here, once, and
passed in. The alternative -- importing this module lazily inside `detect` so the
syntactic scan finds no `read_text` -- would have passed the guard while doing
exactly the thing the guard exists to prevent, and a guard you can walk around is
worse than no guard, because it reads as a guarantee.

The deviation from §9's `detect(text)` signature is recorded in LIMITATIONS.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from .detect import Lexicons

LEXICON_DIR = Path(__file__).resolve().parent / "lexicon"
LANGUAGES = ("ta", "hi")


class LexiconError(ValueError):
    """A lexicon that is missing or empty. Never silently treated as no markers."""


def read_one(language: str, directory: Path = LEXICON_DIR) -> frozenset[str]:
    """One token per line; `#` starts a comment; blank lines ignored."""
    path = directory / f"{language}.txt"
    if not path.exists():
        raise LexiconError(f"no lexicon for {language!r} at {path}")
    words = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        token = line.split("#", 1)[0].strip().casefold()
        if token:
            words.add(token)
    if not words:
        # An empty lexicon would silently turn every code-mixed question into
        # English, which looks like a detector that has stopped working rather
        # than a file that has gone missing.
        raise LexiconError(f"lexicon {path.name} has no entries")
    return frozenset(words)


@lru_cache(maxsize=4)
def load(directory: Path = LEXICON_DIR) -> Lexicons:
    """Every lexicon, cached. The files do not change while the process runs."""
    return Lexicons(**{language: read_one(language, directory) for language in LANGUAGES})
