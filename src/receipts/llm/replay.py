"""receipts.llm.replay — [IO] record and replay model calls (ADR-005, SDD §16).

The key is the SHA-256 of canonical JSON over

    {provider, model, prompt_id, prompt_sha, messages, schema, max_tokens, temperature}

so every input that could change the answer is in it. Notably `prompt_sha`: edit
one character of a prompt file and every recording made with the old text stops
matching. That is the intended behaviour, not a cost -- a run that silently
reused recordings from a prompt that no longer exists would report numbers
belonging to an experiment nobody ran.

`ReplayLLM` **raises** on a missing key. It has no `inner` to fall through to,
which is a structural guarantee rather than a policy: there is no network client
in the object, so there is nothing for a missing key to fall back onto.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .base import (
    LLM,
    Msg,
    Provenance,
    RecordingMissing,
    StructuredResult,
    TextResult,
    Usage,
)

REPO = Path(__file__).resolve().parents[3]
RECORDINGS = REPO / "recordings"


def key_for(
    *,
    provider: str,
    model: str,
    prompt_id: str,
    prompt_sha: str,
    messages: list[Msg],
    schema: dict[str, Any] | None,
    max_tokens: int,
    temperature: int = 0,
    kind: str = "structured",
) -> str:
    """SDD §16's key. Canonical JSON, sorted keys, no whitespace drift."""
    payload = {
        "kind": kind,
        "max_tokens": max_tokens,
        "messages": [{"content": m.content, "role": m.role} for m in messages],
        "model": model,
        "prompt_id": prompt_id,
        "prompt_sha": prompt_sha,
        "provider": provider,
        "schema": schema,
        "temperature": temperature,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _write(path: Path, body: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(body, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )


class RecordingLLM:
    """Wraps a real client, writes every call to disk, returns what it returned."""

    def __init__(self, inner: LLM, directory: Path = RECORDINGS) -> None:
        self.inner = inner
        self.directory = directory
        self.provider = getattr(inner, "provider", "unknown")
        self.model = getattr(inner, "model", "unknown")

    def _record(self, key: str, body: dict[str, Any]) -> None:
        _write(self.directory / f"{key}.json", body)

    def structured(
        self, *, prompt_id: str, messages: list[Msg], schema: dict[str, Any], max_tokens: int
    ) -> StructuredResult:
        result = self.inner.structured(
            prompt_id=prompt_id, messages=messages, schema=schema, max_tokens=max_tokens
        )
        key = key_for(
            provider=self.provider,
            model=self.model,
            prompt_id=prompt_id,
            prompt_sha=result.provenance.sha256,
            messages=messages,
            schema=schema,
            max_tokens=max_tokens,
            kind="structured",
        )
        self._record(
            key,
            {
                "kind": "structured",
                "data": result.data,
                "raw": result.raw,
                "usage": {
                    "input_tokens": result.usage.input_tokens,
                    "output_tokens": result.usage.output_tokens,
                },
                "provenance": {
                    "prompt_id": result.provenance.prompt_id,
                    "version": result.provenance.version,
                    "sha256": result.provenance.sha256,
                    "provider": result.provenance.provider,
                    "model": result.provenance.model,
                },
            },
        )
        return result

    def text(self, *, prompt_id: str, messages: list[Msg], max_tokens: int) -> TextResult:
        result = self.inner.text(prompt_id=prompt_id, messages=messages, max_tokens=max_tokens)
        key = key_for(
            provider=self.provider,
            model=self.model,
            prompt_id=prompt_id,
            prompt_sha=result.provenance.sha256,
            messages=messages,
            schema=None,
            max_tokens=max_tokens,
            kind="text",
        )
        self._record(
            key,
            {
                "kind": "text",
                "text": result.text,
                "usage": {
                    "input_tokens": result.usage.input_tokens,
                    "output_tokens": result.usage.output_tokens,
                },
                "provenance": {
                    "prompt_id": result.provenance.prompt_id,
                    "version": result.provenance.version,
                    "sha256": result.provenance.sha256,
                    "provider": result.provenance.provider,
                    "model": result.provenance.model,
                },
            },
        )
        return result


class ReplayLLM:
    """Answers from recordings only. Holds no client, so it cannot call out.

    `provider` and `model` are given rather than discovered, because the key
    includes them: replaying against a different model name is a different
    experiment and must miss rather than match.
    """

    def __init__(
        self,
        directory: Path = RECORDINGS,
        *,
        provider: str = "",
        model: str = "",
        prompts: Any = None,
    ) -> None:
        self.directory = directory
        self.provider = provider
        self.model = model
        self._prompts = prompts

    def _prompt_sha(self, prompt_id: str) -> tuple[str, int]:
        from . import prompts as prompt_loader

        loader = self._prompts or prompt_loader
        prompt = loader.load(prompt_id)
        return prompt.sha256, prompt.version

    def _load(self, key: str, prompt_id: str) -> dict[str, Any]:
        path = self.directory / f"{key}.json"
        if not path.exists():
            raise RecordingMissing(
                f"no recording for {prompt_id} (key {key[:12]}…) in {self.directory}. "
                "Replay does not call the network; record the call first, or check "
                "whether the prompt text changed."
            )
        loaded: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return loaded

    def _provenance(self, body: dict[str, Any]) -> Provenance:
        raw = body.get("provenance", {})
        return Provenance(
            prompt_id=raw.get("prompt_id", ""),
            version=int(raw.get("version", 0)),
            sha256=raw.get("sha256", ""),
            provider=raw.get("provider", self.provider),
            model=raw.get("model", self.model),
        )

    def _usage(self, body: dict[str, Any]) -> Usage:
        raw = body.get("usage", {})
        return Usage(
            input_tokens=int(raw.get("input_tokens", 0)),
            output_tokens=int(raw.get("output_tokens", 0)),
        )

    def structured(
        self, *, prompt_id: str, messages: list[Msg], schema: dict[str, Any], max_tokens: int
    ) -> StructuredResult:
        sha, _version = self._prompt_sha(prompt_id)
        key = key_for(
            provider=self.provider,
            model=self.model,
            prompt_id=prompt_id,
            prompt_sha=sha,
            messages=messages,
            schema=schema,
            max_tokens=max_tokens,
            kind="structured",
        )
        body = self._load(key, prompt_id)
        return StructuredResult(
            data=body.get("data", {}),
            usage=self._usage(body),
            provenance=self._provenance(body),
            raw=body.get("raw", ""),
        )

    def text(self, *, prompt_id: str, messages: list[Msg], max_tokens: int) -> TextResult:
        sha, _version = self._prompt_sha(prompt_id)
        key = key_for(
            provider=self.provider,
            model=self.model,
            prompt_id=prompt_id,
            prompt_sha=sha,
            messages=messages,
            schema=None,
            max_tokens=max_tokens,
            kind="text",
        )
        body = self._load(key, prompt_id)
        return TextResult(
            text=body.get("text", ""),
            usage=self._usage(body),
            provenance=self._provenance(body),
        )
