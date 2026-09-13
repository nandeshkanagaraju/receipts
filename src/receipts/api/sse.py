"""receipts.api.sse — the event stream (SDD §19).

`step {stage, state}` per stage, then `answer`, then `done`. The order is the
contract: a client that has seen `done` knows no more events are coming, and a
client that has seen `answer` knows it has the whole answer.

**Why stream the stages at all.** A question takes several seconds and most of
that is the model. Showing "retrieving, planning, validating" is not a progress
bar for its own sake -- it is the same sequence the receipt will later name, so
the asker watches the reasoning happen and then gets a record of it. A spinner
would be cheaper and would teach them nothing.

Errors are an `error` event followed by `done`, never a dropped connection. A
stream that stops without saying why is indistinguishable from a network fault.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Any

# The stages a client can expect, in the order the orchestrator runs them
# (SDD §9). Published so the front end can render the list before any arrive.
STAGES: tuple[str, ...] = (
    "language",
    "intent",
    "retrieve",
    "plan",
    "validate",
    "gate",
    "compile",
    "guard",
    "execute",
    "compose",
    "ground",
    "receipt",
)

EVENT_TYPES: tuple[str, ...] = ("step", "clarify", "answer", "error", "done")


@dataclass(frozen=True)
class Event:
    """One SSE event. `data` is JSON; `event` is the type line."""

    event: str
    data: dict[str, Any]

    def encode(self) -> str:
        """Wire format. The blank line terminates the event and is not optional."""
        body = json.dumps(self.data, ensure_ascii=False, sort_keys=True)
        return f"event: {self.event}\ndata: {body}\n\n"


def step(stage: str, state: str) -> Event:
    if state not in ("start", "end"):
        raise ValueError(f"step state must be start or end, got {state!r}")
    return Event("step", {"stage": stage, "state": state})


def answer_event(payload: dict[str, Any]) -> Event:
    return Event("answer", payload)


def clarify_event(payload: dict[str, Any]) -> Event:
    return Event("clarify", payload)


def error_event(body: dict[str, Any]) -> Event:
    return Event("error", body)


def done(receipt_id: str | None, trace_id: str) -> Event:
    return Event("done", {"receipt_id": receipt_id, "trace_id": trace_id})


def encode_all(events: Iterable[Event]) -> Iterator[str]:
    for event in events:
        yield event.encode()


def parse(stream: str) -> list[Event]:
    """The inverse, for tests. A client that cannot be parsed is not a contract."""
    out: list[Event] = []
    for block in stream.split("\n\n"):
        if not block.strip():
            continue
        name = ""
        payload = ""
        for line in block.splitlines():
            if line.startswith("event: "):
                name = line[len("event: ") :]
            elif line.startswith("data: "):
                payload = line[len("data: ") :]
        if name:
            out.append(Event(name, json.loads(payload) if payload else {}))
    return out


__all__ = [
    "EVENT_TYPES",
    "STAGES",
    "Event",
    "answer_event",
    "clarify_event",
    "done",
    "encode_all",
    "error_event",
    "parse",
    "step",
]
