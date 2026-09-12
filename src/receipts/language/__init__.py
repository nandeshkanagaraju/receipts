"""Language stages 1 and 1b (SDD §9).

`detect` and `normalize` are pure and take their lexicon as data. `read` is the
composed entry point for callers that just have a string: it is [IO], because
loading the lexicon is.
"""

from .detect import LangDetection, LanguageError, Lexicons, detect
from .lexicon import LexiconError, load
from .normalize import NormalizedQuestion, normalize, normalize_text


def read(text: str) -> NormalizedQuestion:
    """Stage 1 then 1b, with the lexicon loaded. [IO]"""
    lexicons = load()
    return normalize(text, detect(text, lexicons))


__all__ = [
    "LangDetection",
    "LanguageError",
    "LexiconError",
    "Lexicons",
    "NormalizedQuestion",
    "detect",
    "load",
    "normalize",
    "normalize_text",
    "read",
]
