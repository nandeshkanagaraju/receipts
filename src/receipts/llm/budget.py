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

The counters are context-local for the same reason they are reset per question.
One `BudgetedLLM` is built per process, so when the API serves two questions at
once on its threadpool they shared one allowance: each `new_question` zeroed the
other's count, and their combined spend tripped a cap neither had reached alone.
Measured on the demo, 8 concurrent asks of one question answered 3 and abstained
5 with "no plan was produced". A budget shared between questions is not a
per-question budget either.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

from .base import LLM, BudgetExceeded, Msg, StructuredResult, TextResult, Usage

DEFAULT_TOKENS_IN = 12000
DEFAULT_TOKENS_OUT = 2000


@dataclass
class QuestionBudget:
    """What one question may spend, and what it has spent.

    The allowance is shared (it is configuration); the spend is per context, so
    two questions in flight at once cannot spend each other's.
    """

    tokens_in: int = DEFAULT_TOKENS_IN
    tokens_out: int = DEFAULT_TOKENS_OUT

    def __post_init__(self) -> None:
        # Per instance, not module-global: two budgets living in one context are
        # two allowances, and must not read each other's spend.
        # The name is for debuggers only; isolation comes from each instance
        # holding its own ContextVar object, not from the name. It is a constant
        # because D3 forbids `id()` as an identity, and the charter test is right
        # to: an address is not a name.
        self._spent: ContextVar[tuple[int, int]] = ContextVar(
            "receipts_question_spend", default=(0, 0)
        )

    @property
    def spent_in(self) -> int:
        return self._spent.get()[0]

    @property
    def spent_out(self) -> int:
        return self._spent.get()[1]

    def _spend(self, delta_in: int, delta_out: int) -> None:
        current = self._spent.get()
        self._spent.set((current[0] + delta_in, current[1] + delta_out))

    def add(self, usage: Usage) -> None:
        self._spend(usage.input_tokens, usage.output_tokens)
        if self.spent_in > self.tokens_in:
            raise BudgetExceeded(
                f"input tokens {self.spent_in} exceed the per-question budget {self.tokens_in}"
            )
        if self.spent_out > self.tokens_out:
            raise BudgetExceeded(
                f"output tokens {self.spent_out} exceed the per-question budget {self.tokens_out}"
            )

    def check(self) -> None:
        """Refuse before spending, when the allowance is ALREADY gone.

        `add` can only notice a breach after the call it is pricing, because a
        call's output length is not knowable in advance. What is knowable is
        that the budget was blown by an earlier call -- and without this, every
        request after the first breach still reached the provider and was still
        billed, raising `BudgetExceeded` only on the way back. The budget capped
        the answer and not the spend, which is half of what a budget is for.
        """
        if self.spent_in >= self.tokens_in:
            raise BudgetExceeded(
                f"input tokens {self.spent_in} have already reached the "
                f"per-question budget {self.tokens_in}"
            )
        if self.spent_out >= self.tokens_out:
            raise BudgetExceeded(
                f"output tokens {self.spent_out} have already reached the "
                f"per-question budget {self.tokens_out}"
            )

    def reset(self) -> None:
        """A new question starts from zero. The allowance itself is unchanged."""
        self._spent.set((0, 0))

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

    @staticmethod
    def _meter(result: Any) -> None:
        """Report this call's usage to whoever is metering the question (§23).

        Here rather than in the provider clients because every call goes through
        this wrapper -- including replayed ones, which carry the usage that was
        recorded. A meter fed only by live calls would report a replayed run as
        free, and a replayed run is exactly what the eval is.
        """
        from ..observability.tracing import record_usage

        usage = result.usage
        model = getattr(result.provenance, "model", "") or ""
        record_usage(
            model=model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cached=getattr(usage, "cached_input_tokens", 0),
        )

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
        self.budget.check()
        result = self.inner.structured(
            prompt_id=prompt_id, messages=messages, schema=schema, max_tokens=max_tokens
        )
        self.budget.add(result.usage)
        self._meter(result)
        return result

    def text(self, *, prompt_id: str, messages: list[Msg], max_tokens: int) -> TextResult:
        self.budget.check()
        result = self.inner.text(prompt_id=prompt_id, messages=messages, max_tokens=max_tokens)
        self.budget.add(result.usage)
        self._meter(result)
        return result
