"""receipts.llm.anthropic — [IO] Anthropic provider. Structured output via a forced tool.

Constructing this class inside a test run raises (D9). Not "makes no calls" --
cannot be built. A client that exists is a client something can call, and a
guarantee that depends on nobody calling it is not a guarantee.

Model names come from settings only. A model name in code is a number nobody can
trace to a config file, and the recording key includes the model, so a hard-coded
name would silently invalidate recordings when it changed.
"""

from __future__ import annotations

import sys
from typing import Any

from .base import (
    Msg,
    Provenance,
    RealClientUnderPytest,
    StructuredResult,
    TextResult,
    Transient,
    Usage,
)
from .prompts import load as load_prompt

PROVIDER = "anthropic"
TEMPERATURE = 0

# Statuses worth exactly one retry (SDD §16). Anything else is not transient and
# retrying it would be a second identical failure plus a second charge.
RETRYABLE_STATUSES = frozenset({408, 409, 429, 500, 502, 503, 504, 529})


def _refuse_under_pytest(provider: str) -> None:
    if "pytest" in sys.modules:
        raise RealClientUnderPytest(
            f"{provider} client constructed inside a test run (D9). Tests use "
            "ReplayLLM or a fake; a real client must not exist here at all."
        )


class AnthropicLLM:
    def __init__(self, *, model: str, api_key: str | None = None, client: Any = None) -> None:
        _refuse_under_pytest(PROVIDER)
        if not model:
            raise ValueError("model must come from settings, not from code")
        self.provider = PROVIDER
        self.model = model
        self._client = client
        self._api_key = api_key

    def _sdk(self) -> Any:
        if self._client is None:
            import anthropic  # imported late: absent in a test environment

            self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client

    def _call(self, *, system: str, messages: list[Msg], max_tokens: int, tools: Any = None) -> Any:
        try:
            return self._sdk().messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=TEMPERATURE,
                system=system,
                messages=[{"role": m.role, "content": m.content} for m in messages],
                **(
                    {"tools": tools, "tool_choice": {"type": "tool", "name": tools[0]["name"]}}
                    if tools
                    else {}
                ),
            )
        except Exception as exc:  # noqa: BLE001 - normalised below
            status = getattr(exc, "status_code", 0) or 0
            if status in RETRYABLE_STATUSES:
                raise Transient(status=status, detail=str(exc)[:200]) from exc
            raise

    def structured(
        self, *, prompt_id: str, messages: list[Msg], schema: dict[str, Any], max_tokens: int
    ) -> StructuredResult:
        prompt = load_prompt(prompt_id)
        tool = {"name": "answer", "description": "Return the answer.", "input_schema": schema}
        response = self._call(
            system=prompt.text, messages=messages, max_tokens=max_tokens, tools=[tool]
        )
        data: dict[str, Any] = {}
        for block in getattr(response, "content", []):
            if getattr(block, "type", "") == "tool_use":
                data = dict(getattr(block, "input", {}))
                break
        usage = getattr(response, "usage", None)
        return StructuredResult(
            data=data,
            usage=Usage(
                input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
                output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
            ),
            provenance=Provenance(
                prompt_id=prompt.prompt_id,
                version=prompt.version,
                sha256=prompt.sha256,
                provider=self.provider,
                model=self.model,
            ),
        )

    def text(self, *, prompt_id: str, messages: list[Msg], max_tokens: int) -> TextResult:
        prompt = load_prompt(prompt_id)
        response = self._call(system=prompt.text, messages=messages, max_tokens=max_tokens)
        parts = [
            getattr(b, "text", "") for b in getattr(response, "content", []) if hasattr(b, "text")
        ]
        usage = getattr(response, "usage", None)
        return TextResult(
            text="".join(parts),
            usage=Usage(
                input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
                output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
            ),
            provenance=Provenance(
                prompt_id=prompt.prompt_id,
                version=prompt.version,
                sha256=prompt.sha256,
                provider=self.provider,
                model=self.model,
            ),
        )
