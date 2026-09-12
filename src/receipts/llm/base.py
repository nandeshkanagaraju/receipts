"""receipts.llm.base — [P] pure: the protocol every provider satisfies.

The rest of the system talks to `LLM` and never to a vendor. That is what lets
record/replay sit in the middle as just another `LLM`, and what lets the fallback
chain be a provider too: nothing downstream knows whether it got Anthropic,
OpenAI, or a recording from three weeks ago.

**Every result carries its provenance** (D15): which prompt, which version, and
the SHA-256 of the prompt text that produced it. A run whose numbers cannot be
traced to the exact prompt bytes is a run that cannot be reproduced, and the
recording key is built from the same fields, so a prompt edited by one character
cannot silently reuse an old recording.

Usage is counted in tokens here and priced elsewhere. This module holds no
prices: `observability/metering.py` turns usage into integer micro-dollars, and
keeping the two apart is what stops a float price arriving through a model call.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

Role = Literal["system", "user", "assistant"]


@dataclass(frozen=True)
class Msg:
    """One message. No timestamps: a conversation is content, not an event log."""

    role: Role
    content: str

    def __post_init__(self) -> None:
        if self.role not in ("system", "user", "assistant"):
            raise ValueError(f"unknown role {self.role!r}")


@dataclass(frozen=True)
class Usage:
    """Tokens in and out. Integers, always -- a fractional token is a bug."""

    input_tokens: int = 0
    output_tokens: int = 0

    def __post_init__(self) -> None:
        for name in ("input_tokens", "output_tokens"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool):
                raise TypeError(f"{name} must be int, got {type(value).__name__}")
            if value < 0:
                raise ValueError(f"{name} is negative: {value}")

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True)
class Provenance:
    """Which prompt, which version, which bytes (D15)."""

    prompt_id: str
    version: int
    sha256: str
    provider: str = ""
    model: str = ""


@dataclass(frozen=True)
class StructuredResult:
    """Parsed JSON from a forced-schema call."""

    data: dict[str, Any]
    usage: Usage
    provenance: Provenance
    raw: str = ""


@dataclass(frozen=True)
class TextResult:
    text: str
    usage: Usage
    provenance: Provenance


@runtime_checkable
class LLM(Protocol):
    """SDD §16. Temperature is 0 everywhere and is not a parameter."""

    def structured(
        self,
        *,
        prompt_id: str,
        messages: list[Msg],
        schema: dict[str, Any],
        max_tokens: int,
    ) -> StructuredResult: ...

    def text(self, *, prompt_id: str, messages: list[Msg], max_tokens: int) -> TextResult: ...


class LLMError(RuntimeError):
    """Base for everything this package refuses to do."""


class RealClientUnderPytest(LLMError):
    """D9: a real provider client cannot be constructed inside a test run.

    Not "does not make calls" -- cannot be *built*. A client that exists is a
    client something can call, and the guarantee the charter wants is that a test
    run has no route to the network at all.
    """


class RecordingMissing(LLMError):
    """Replay was asked for a key it does not have.

    Raises rather than falling through to the network. A replay that silently
    became a live call would make a deterministic run non-deterministic at exactly
    the moment nobody was watching -- and would spend money doing it.
    """


class ModelUnavailable(LLMError):
    """Primary and secondary both failed."""


class BudgetExceeded(LLMError):
    """One question asked for more tokens than it is allowed."""


@dataclass
class Transient(LLMError):
    """A provider failure worth one retry: 429, 5xx, timeout.

    Carried as a type rather than a status code so the fallback chain does not
    have to know each vendor's error shape.
    """

    status: int = 0
    detail: str = ""
    retryable: bool = field(default=True)

    def __str__(self) -> str:
        return f"transient provider failure {self.status}: {self.detail}"
