"""receipts.observability.tracing — [IO] spans per stage (SDD §23).

**This is the one engine-adjacent package allowed to read a clock** (D2:
`WALL_CLOCK_ALLOWED`). That is not an oversight in the charter, it is the
design: a duration is telemetry, telemetry lives in `Trace` and never in
`Answer` (D12), and the place it may be measured is here.

Which is why the recorder is a **context variable** rather than a parameter
threaded through `orchestrator.answer`. The orchestrator calls `mark_stage`
where it already built a span; with no recorder installed that call adds a
dictionary lookup and nothing else, so the engine's behaviour is identical
whether or not anyone is watching. A pipeline that runs differently when
instrumented is a pipeline whose measurements are about the instrument.

Exporters, per §23: console by default, OTLP when `OTEL_EXPORTER_OTLP_ENDPOINT`
is set (the Compose `obs` profile). Neither is installed by importing this
module -- `configure()` is explicit, because a library that starts exporting
spans on import is one that exports them from the test suite too.
"""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from ..domain.types import Trace

# `receipts.stage.<name>`, per §23.
SPAN_PREFIX = "receipts.stage."


@dataclass
class StageRecord:
    """One stage, and how long it took. Nanoseconds: integers, never a float."""

    name: str
    duration_ns: int
    ok: bool = True
    detail: str = ""
    attributes: dict[str, Any] = field(default_factory=dict)

    @property
    def duration_ms(self) -> float:
        """Display only. Never fed back into arithmetic that anything compares."""
        return self.duration_ns / 1_000_000


@dataclass
class StageRecorder:
    """Times each stage by the gap between consecutive marks.

    The orchestrator marks a stage when it finishes -- which is where it already
    built the span -- so a stage's duration is the time since the previous mark.
    That makes the first stage's duration the time since the recorder started,
    which is correct: the recorder is started by the caller immediately before
    the question goes in.
    """

    started_ns: int = field(default_factory=time.perf_counter_ns)
    _last_ns: int = field(default=0)
    records: list[StageRecord] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._last_ns = self.started_ns

    def mark(self, name: str, *, detail: str = "", ok: bool = True, **attributes: Any) -> None:
        now = time.perf_counter_ns()
        self.records.append(
            StageRecord(
                name=name,
                duration_ns=now - self._last_ns,
                ok=ok,
                detail=detail,
                attributes=attributes,
            )
        )
        self._last_ns = now

    @property
    def total_ns(self) -> int:
        return self._last_ns - self.started_ns

    def by_stage(self) -> dict[str, int]:
        """Nanoseconds per stage name, summed when a stage ran more than once.

        Summed rather than last-wins: answering a clarification runs validate
        and gate a second time (M17.1), and the honest number for "how long did
        validation take" is both of them.
        """
        out: dict[str, int] = {}
        for record in self.records:
            out[record.name] = out.get(record.name, 0) + record.duration_ns
        return out


@dataclass
class UsageMeter:
    """What one question spent, in tokens and in integer micro-dollars (§23).

    SDD §23 says cost is "reported per question in the trace", and until M20
    nothing wrote `Trace.tokens_in`, `tokens_out` or `cost_micro_usd` at all --
    the fields existed, the LLM layer knew the numbers, and no one carried them
    across. The same shape as the other six instances in `docs/M2_NOTES.md` §11.

    Priced per call rather than by summing tokens and pricing once: the cached
    part of a prompt is billed at a different rate, so a total that has lost the
    split cannot be priced correctly afterwards.
    """

    tokens_in: int = 0
    tokens_out: int = 0
    cached_tokens_in: int = 0
    cost_micro_usd: int = 0
    calls: int = 0
    unpriced_models: set[str] = field(default_factory=set)

    def add(self, *, model: str, input_tokens: int, output_tokens: int, cached: int = 0) -> None:
        from .metering import PricingError, cost_micro_usd

        self.calls += 1
        self.tokens_in += input_tokens
        self.tokens_out += output_tokens
        self.cached_tokens_in += cached
        try:
            self.cost_micro_usd += cost_micro_usd(
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cached_input_tokens=cached,
            )
        except PricingError:
            # A model with no published price is recorded as unpriced rather
            # than guessed at. A cost line that silently omits a model is worse
            # than one that says which model it could not price.
            self.unpriced_models.add(model)


_METER: ContextVar[UsageMeter | None] = ContextVar("receipts_usage_meter", default=None)


def record_usage(*, model: str, input_tokens: int, output_tokens: int, cached: int = 0) -> None:
    """Called by the LLM layer. A no-op when nobody is metering."""
    meter = _METER.get()
    if meter is not None:
        meter.add(
            model=model, input_tokens=input_tokens, output_tokens=output_tokens, cached=cached
        )


def current_meter() -> UsageMeter | None:
    return _METER.get()


@contextmanager
def metering() -> Iterator[UsageMeter]:
    meter = UsageMeter()
    token = _METER.set(meter)
    try:
        yield meter
    finally:
        _METER.reset(token)


_RECORDER: ContextVar[StageRecorder | None] = ContextVar("receipts_stage_recorder", default=None)


def current() -> StageRecorder | None:
    return _RECORDER.get()


@contextmanager
def recording() -> Iterator[StageRecorder]:
    """Install a recorder for one question. Nested use replaces, then restores."""
    recorder = StageRecorder()
    token = _RECORDER.set(recorder)
    try:
        yield recorder
    finally:
        _RECORDER.reset(token)


def mark_stage(
    trace: Trace, name: str, detail: str = "", ok: bool = True, **attributes: Any
) -> Trace:
    """Record the span, and time it if anyone is listening.

    Signature-compatible with `Trace.with_span`, deliberately: the orchestrator
    swapped one call for the other and nothing else changed. The return value is
    the new `Trace`, so chained `.with_note(...)` still reads the same.
    """
    recorder = _RECORDER.get()
    if recorder is not None:
        recorder.mark(name, detail=detail, ok=ok, **attributes)
        span = _otel_span(name)
        if span is not None:
            span.set_attribute("receipts.stage.ok", ok)
            if detail:
                span.set_attribute("receipts.stage.detail", detail[:200])
            for key, value in attributes.items():
                span.set_attribute(f"receipts.{key}", value)
            span.end()
    return trace.with_span(name, detail, ok)


# --------------------------------------------------------------------------- #
# OpenTelemetry. Optional at runtime: the demo runs without a collector, and a
# missing exporter must never be the reason a question fails.
# --------------------------------------------------------------------------- #
_TRACER: Any = None


def configure(*, service_name: str = "receipts", exporter: str | None = None) -> str:
    """Install an exporter. Returns the one chosen, for the caller to print.

    `exporter` defaults to `otlp` when `OTEL_EXPORTER_OTLP_ENDPOINT` is set and
    `console` otherwise (§23). `none` is honoured, and is what the test suite
    uses -- a suite that prints a span per stage per question is a suite nobody
    reads the output of.
    """
    global _TRACER
    choice = exporter or ("otlp" if os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT") else "console")
    if choice == "none":
        _TRACER = None
        return choice
    try:
        from opentelemetry import trace as otel_trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

        if choice == "otlp":
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

            span_exporter: Any = OTLPSpanExporter()
        else:
            span_exporter = ConsoleSpanExporter()

        provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
        provider.add_span_processor(BatchSpanProcessor(span_exporter))
        otel_trace.set_tracer_provider(provider)
        _TRACER = otel_trace.get_tracer("receipts")
        return choice
    except Exception:
        # An exporter that cannot start is a monitoring problem, never an
        # answering problem. Recorded as "none" so the caller prints the truth.
        _TRACER = None
        return "none"


def _otel_span(name: str) -> Any:
    if _TRACER is None:
        return None
    try:
        return _TRACER.start_span(f"{SPAN_PREFIX}{name}")
    except Exception:
        return None


__all__ = [
    "SPAN_PREFIX",
    "StageRecord",
    "StageRecorder",
    "UsageMeter",
    "configure",
    "current",
    "current_meter",
    "mark_stage",
    "metering",
    "record_usage",
    "recording",
]
