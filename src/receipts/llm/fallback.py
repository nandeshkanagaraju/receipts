"""receipts.llm.fallback — primary, one retry, secondary, then give up (SDD §16).

    primary → 1 retry on 429/5xx/timeout → secondary → ModelUnavailable

**Exactly one** retry on the primary. Not "up to one": the count is asserted,
because a retry loop that quietly became two is a doubled bill and a doubled
latency that no test would notice. A non-transient failure is not retried at all,
since a second identical request produces a second identical failure plus a
second charge.

With no secondary configured -- the M5 cut-line -- the chain goes straight to
`ModelUnavailable` rather than pretending a second opinion exists.
"""

from __future__ import annotations

from typing import Any

from .base import LLM, ModelUnavailable, Msg, StructuredResult, TextResult, Transient

PRIMARY_RETRIES = 1


class FallbackLLM:
    """Two providers and a policy. Itself an `LLM`, so nothing downstream knows."""

    def __init__(self, primary: LLM, secondary: LLM | None = None) -> None:
        self.primary = primary
        self.secondary = secondary
        # Observable for tests and for the report: how the last call was served.
        self.primary_attempts = 0
        self.secondary_attempts = 0
        self.last_provider = ""

    def _try(self, client: LLM, attempts: int, call: str, **kwargs: Any) -> Any:
        last: Exception | None = None
        for _ in range(attempts):
            try:
                if client is self.primary:
                    self.primary_attempts += 1
                else:
                    self.secondary_attempts += 1
                result = getattr(client, call)(**kwargs)
                self.last_provider = getattr(client, "provider", "")
                return result
            except Transient as exc:
                last = exc
        raise last if last else ModelUnavailable("no attempt was made")

    def _run(self, call: str, **kwargs: Any) -> Any:
        self.primary_attempts = 0
        self.secondary_attempts = 0
        try:
            return self._try(self.primary, 1 + PRIMARY_RETRIES, call, **kwargs)
        except Transient as primary_failure:
            if self.secondary is None:
                raise ModelUnavailable(
                    f"primary failed ({primary_failure}) and no secondary is configured"
                ) from primary_failure
            try:
                return self._try(self.secondary, 1, call, **kwargs)
            except Transient as secondary_failure:
                raise ModelUnavailable(
                    f"primary and secondary both failed; last: {secondary_failure}"
                ) from secondary_failure

    def structured(
        self, *, prompt_id: str, messages: list[Msg], schema: dict[str, Any], max_tokens: int
    ) -> StructuredResult:
        result: StructuredResult = self._run(
            "structured",
            prompt_id=prompt_id,
            messages=messages,
            schema=schema,
            max_tokens=max_tokens,
        )
        return result

    def text(self, *, prompt_id: str, messages: list[Msg], max_tokens: int) -> TextResult:
        result: TextResult = self._run(
            "text", prompt_id=prompt_id, messages=messages, max_tokens=max_tokens
        )
        return result
