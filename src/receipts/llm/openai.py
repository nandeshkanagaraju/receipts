"""receipts.llm.openai — [IO] OpenAI provider. Structured output via json_schema.

The **primary**, since ADR-018. Same D9 refusal either way: constructing this
inside a test run raises, because a client that exists is a client something can
call.

Four things the gpt-5 family needs that the first version of this file got
wrong, all found by probing the live API before the paid run rather than during
it:

1. **`max_completion_tokens`, not `max_tokens`.** The old name is refused
   outright with a 400.
2. **Temperature is not settable.** These models accept only the default, and
   send back `Unsupported value: 'temperature' does not support 0`. So it is
   omitted rather than forced, and determinism comes from replay instead
   (ADR-018, LIMITATIONS).
3. **A caller-supplied system message must not be shadowed.** `_messages`
   unconditionally prepended the prompt *file*, so the baseline -- whose system
   message is a 16k rendered prompt -- would have sent the unrendered template
   with `{{DDL}}` still in it, in front of the real one, on every call.
4. **Caching is automatic here but not free of conditions.** OpenAI caches a
   prompt prefix over 1024 tokens with no annotation, provided the prefix is
   byte-identical and routed together, so `prompt_cache_key` is passed to keep
   same-prefix calls on one cache, and `cached_tokens` is read back so the run
   can show whether it worked.
"""

from __future__ import annotations

from typing import Any

from .anthropic import RETRYABLE_STATUSES, _refuse_under_pytest
from .base import Msg, Provenance, StructuredResult, TextResult, Transient, Usage
from .prompts import load as load_prompt

PROVIDER = "openai"


class OpenAILLM:
    def __init__(
        self,
        *,
        model: str,
        api_key: str | None = None,
        client: Any = None,
        temperature: int | None = None,
        cache_key: str | None = None,
    ) -> None:
        _refuse_under_pytest(PROVIDER)
        if not model:
            raise ValueError("model must come from settings, not from code")
        self.provider = PROVIDER
        self.model = model
        self._client = client
        self._api_key = api_key
        self.temperature = temperature
        self.cache_key = cache_key

    def _sdk(self) -> Any:
        if self._client is None:
            import openai  # imported late: absent in a test environment

            self._client = openai.OpenAI(api_key=self._api_key)
        return self._client

    def _call(self, *, messages: list[dict[str, str]], max_tokens: int, fmt: Any = None) -> Any:
        extra: dict[str, Any] = {}
        if self.temperature is not None:
            extra["temperature"] = self.temperature
        if self.cache_key:
            extra["prompt_cache_key"] = self.cache_key
        try:
            return self._sdk().chat.completions.create(
                model=self.model,
                max_completion_tokens=max_tokens,
                messages=messages,
                **extra,
                **({"response_format": fmt} if fmt else {}),
            )
        except Exception as exc:  # noqa: BLE001 - normalised below
            status = getattr(exc, "status_code", 0) or 0
            if status in RETRYABLE_STATUSES:
                raise Transient(status=status, detail=str(exc)[:200]) from exc
            raise

    def _messages(self, system: str, messages: list[Msg]) -> list[dict[str, str]]:
        """The prompt file is the system message -- unless the caller brought one.

        A caller that renders its own system prompt (the baseline does: DDL,
        glossary, examples) would otherwise have the raw template prepended in
        front of it, placeholders and all.
        """
        carried = [{"role": m.role, "content": m.content} for m in messages]
        if any(m.role == "system" for m in messages):
            return carried
        return [{"role": "system", "content": system}, *carried]

    def _usage(self, response: Any) -> Usage:
        usage = getattr(response, "usage", None)
        details = getattr(usage, "prompt_tokens_details", None)
        return Usage(
            input_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
            output_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
            cached_input_tokens=int(getattr(details, "cached_tokens", 0) or 0),
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
