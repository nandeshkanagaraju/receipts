"""receipts.llm.budget — one question's token allowance (SDD §16).

A per-question budget of input and output tokens. Exceeding it raises
`BudgetExceeded` rather than truncating: a truncated answer is a wrong answer
that looks like an answer, and this project's entire subject is the difference
between those two.

The budget is checked **after** each call, on the usage the provider reported,
because that is the only honest count -- an estimate made before the call is a
guess about a tokeniser.

It is per **question**, and a question is several calls: a first attempt and at
most one retry. Nothing in the type says when a question ends, so the caller must
say, with `new_question()`. The first live smoke run found out what happens
otherwise -- one `BudgetedLLM` is built per *run*, so the counter accumulated
across trials and the third question in a 180-question run died at 48,482 tokens
against a 40,000 budget. A per-question budget that is never reset is a per-run
budget with a misleading name.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .base import LLM, BudgetExceeded, Msg, StructuredResult, TextResult, Usage

DEFAULT_TOKENS_IN = 12000
DEFAULT_TOKENS_OUT = 2000


@dataclass
class QuestionBudget:
    """What one question may spend, and what it has spent."""

    tokens_in: int = DEFAULT_TOKENS_IN
    tokens_out: int = DEFAULT_TOKENS_OUT
    spent_in: int = field(default=0)
    spent_out: int = field(default=0)

    def add(self, usage: Usage) -> None:
        self.spent_in += usage.input_tokens
        self.spent_out += usage.output_tokens
        if self.spent_in > self.tokens_in:
            raise BudgetExceeded(
                f"input tokens {self.spent_in} exceed the per-question budget {self.tokens_in}"
            )
        if self.spent_out > self.tokens_out:
            raise BudgetExceeded(
                f"output tokens {self.spent_out} exceed the per-question budget {self.tokens_out}"
            )

    def reset(self) -> None:
        """A new question starts from zero. The allowance itself is unchanged."""
        self.spent_in = 0
        self.spent_out = 0

    @property
    def remaining_in(self) -> int:
        return max(0, self.tokens_in - self.spent_in)

    @property
    def remaining_out(self) -> int:
        return max(0, self.tokens_out - self.spent_out)


class BudgetedLLM:
    """An `LLM` that counts what passes through it against one question's budget."""

    def __init__(self, inner: LLM, budget: QuestionBudget | None = None) -> None:
        self.inner = inner
        self.budget = budget or QuestionBudget()
        self.provider = getattr(inner, "provider", "")
        self.model = getattr(inner, "model", "")
        self.questions = 0

    def new_question(self) -> None:
        """Start a new question's allowance. Called once per trial, by the caller.

        Explicit rather than inferred. There is no signal inside a call that says
        "this is a different question", and guessing from the message list would
        be wrong the first time two questions shared a prefix -- which, for a
        system whose 16k system prompt is identical across every trial, is always.
        """
        self.budget.reset()
        self.questions += 1

    def structured(
        self, *, prompt_id: str, messages: list[Msg], schema: dict[str, Any], max_tokens: int
    ) -> StructuredResult:
        result = self.inner.structured(
            prompt_id=prompt_id, messages=messages, schema=schema, max_tokens=max_tokens
        )
        self.budget.add(result.usage)
        return result

    def text(self, *, prompt_id: str, messages: list[Msg], max_tokens: int) -> TextResult:
        result = self.inner.text(prompt_id=prompt_id, messages=messages, max_tokens=max_tokens)
        self.budget.add(result.usage)
        return result
