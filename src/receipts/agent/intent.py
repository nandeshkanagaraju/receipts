"""receipts.agent.intent — [IO] stage 2: what kind of question is this.

One structured call, deliberately small. It decides the *kind* of question and
whether it refers back to the previous one — not which metric applies, not
whether the data exists. Those need the retrieved slice, which this stage runs
before, and a router that guessed at them would be making the hardest calls with
the least information.

`OUT_OF_SCOPE` here is a routing hint, never a refusal. The planner sees the
catalogue and gets the last word; a question this stage misroutes as out of scope
would otherwise be refused without anything ever checking whether a metric
covered it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..domain.types import Intent
from ..llm.base import LLM, Msg

PROMPT_ID = "intent"

INTENTS = tuple(intent.value for intent in Intent)


def intent_schema() -> dict[str, Any]:
    """Strict mode: every property required, `additionalProperties` false."""
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "intent": {"type": "string", "enum": list(INTENTS)},
            "missing_concept": {"type": "string"},
            "is_followup": {"type": "boolean"},
        },
        "required": ["intent", "missing_concept", "is_followup"],
    }


@dataclass(frozen=True, slots=True)
class IntentResult:
    intent: Intent
    missing_concept: str
    is_followup: bool
    raw: str = ""

    @property
    def is_out_of_scope(self) -> bool:
        return self.intent is Intent.OUT_OF_SCOPE


def route_intent(
    question: str, llm: LLM, *, previous_question: str | None = None, max_tokens: int = 512
) -> IntentResult:
    """Stage 2. The previous question is given only so `is_followup` is decidable.

    Its *answer* is not given, and neither are any result rows (SDD §17): a
    router that could see numbers would start routing on what the last answer
    said rather than on what this question asks.
    """
    messages: list[Msg] = []
    if previous_question:
        messages.append(Msg(role="user", content=f"The previous question was: {previous_question}"))
    messages.append(Msg(role="user", content=question))

    result = llm.structured(
        prompt_id=PROMPT_ID,
        messages=messages,
        schema=intent_schema(),
        max_tokens=max_tokens,
    )
    data = result.data
    return IntentResult(
        intent=Intent(data["intent"]),
        missing_concept=str(data.get("missing_concept") or ""),
        is_followup=bool(data.get("is_followup")),
        raw=result.raw,
    )
