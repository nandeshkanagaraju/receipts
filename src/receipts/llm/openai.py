"""receipts.llm.openai — [IO] OpenAI provider. Structured output via json_schema.

The secondary. Same D9 refusal as the primary: constructing this inside a test
run raises, because a client that exists is a client something can call.

CUT-LINE (BUILD_PROMPTS M5): if this provider is dropped, `secondary` becomes
"none" in settings and the fallback chain goes straight to `ModelUnavailable`
rather than pretending a second opinion exists.
"""

from __future__ import annotations

from typing import Any

from .anthropic import RETRYABLE_STATUSES, TEMPERATURE, _refuse_under_pytest
from .base import Msg, Provenance, StructuredResult, TextResult, Transient, Usage
from .prompts import load as load_prompt

PROVIDER = "openai"


class OpenAILLM:
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
            import openai  # imported late: absent in a test environment

            self._client = openai.OpenAI(api_key=self._api_key)
        return self._client

    def _call(self, *, messages: list[dict[str, str]], max_tokens: int, fmt: Any = None) -> Any:
        try:
            return self._sdk().chat.completions.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=TEMPERATURE,
                messages=messages,
                **({"response_format": fmt} if fmt else {}),
            )
        except Exception as exc:  # noqa: BLE001 - normalised below
            status = getattr(exc, "status_code", 0) or 0
            if status in RETRYABLE_STATUSES:
                raise Transient(status=status, detail=str(exc)[:200]) from exc
            raise

    def _messages(self, system: str, messages: list[Msg]) -> list[dict[str, str]]:
        return [{"role": "system", "content": system}] + [
            {"role": m.role, "content": m.content} for m in messages
        ]

    def _usage(self, response: Any) -> Usage:
        usage = getattr(response, "usage", None)
        return Usage(
            input_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
            output_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
        )

    def structured(
        self, *, prompt_id: str, messages: list[Msg], schema: dict[str, Any], max_tokens: int
    ) -> StructuredResult:
        import json

        prompt = load_prompt(prompt_id)
        fmt = {
            "type": "json_schema",
            "json_schema": {"name": "answer", "schema": schema, "strict": True},
        }
        response = self._call(
            messages=self._messages(prompt.text, messages), max_tokens=max_tokens, fmt=fmt
        )
        raw = response.choices[0].message.content or "{}"
        return StructuredResult(
            data=json.loads(raw),
            usage=self._usage(response),
            provenance=Provenance(
                prompt_id=prompt.prompt_id,
                version=prompt.version,
                sha256=prompt.sha256,
                provider=self.provider,
                model=self.model,
            ),
            raw=raw,
        )

    def text(self, *, prompt_id: str, messages: list[Msg], max_tokens: int) -> TextResult:
        prompt = load_prompt(prompt_id)
        response = self._call(messages=self._messages(prompt.text, messages), max_tokens=max_tokens)
        return TextResult(
            text=response.choices[0].message.content or "",
            usage=self._usage(response),
            provenance=Provenance(
                prompt_id=prompt.prompt_id,
                version=prompt.version,
                sha256=prompt.sha256,
                provider=self.provider,
                model=self.model,
            ),
        )
