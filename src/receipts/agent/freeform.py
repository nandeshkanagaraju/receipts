"""receipts.agent.freeform — SDD §10 rule 5. The model writes SQL, and every layer still applies.

This is the path the thesis needs and the one it is most exposed by. Without it,
"coverage" means only what the semantic layer happens to cover, and the honest
comparison against a baseline that will answer anything becomes a comparison
between a system that answers and a system that declines. With it, Receipts can
answer outside the layer **and say so**: the status is `UNVERIFIED`, the receipt
says in words that no governed metric was used and nobody has agreed the
definition behind the number, and the scorer files a wrong answer here as
`Wrong-flagged` rather than `Silent-wrong` (SDD §25.3) because the asker was told.

What makes it safe is not this module. It is that the SQL goes through
`rewrite_and_guard` (§12.2): guard, then scope rewrite, then guard **again** on
the rewritten text. This module's only jobs are to ask for SQL and to refuse to
pretend when it does not get any.

Two things deliberately absent from the prompt, both asserted by tests:

- **Scope.** The model is never told which regions the asker may see. The rewrite
  injects the predicate afterwards, wherever the scoped table appears (D7).
- **Result rows.** The model writes the query blind, as the planner does.

The tables it *is* given are the role's allowlist and nothing else, so a role
without the finance capability is not informed that `settlements` exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..llm.base import LLM, Msg

PROMPT_ID = "freeform"

UNITS: tuple[str, ...] = ("count", "ratio", "other", "INR", "GBP", "USD", "AED", "SGD", "MYR")

SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["sql", "unit", "why_not", "assumption"],
    "properties": {
        "sql": {
            "type": ["string", "null"],
            "description": "One read-only SELECT over the listed tables, or null.",
        },
        "unit": {"type": "string", "enum": list(UNITS)},
        "why_not": {"type": "string"},
        "assumption": {"type": "string"},
    },
}


@dataclass(frozen=True)
class FreeformDraft:
    """What the model returned, before anything has been allowed to run it."""

    sql: str
    unit: str
    why_not: str
    assumption: str
    raw: str = ""

    @property
    def wrote_sql(self) -> bool:
        return bool(self.sql.strip())


def schema_text(columns: dict[str, tuple[str, ...]], allowlist: frozenset[str]) -> str:
    """The allowlisted tables, as `table(col, col, ...)`, sorted.

    Sorted because D5 applies to prompts as much as to SQL: an unordered dict
    walk would make the prompt -- and therefore the replay key, which is a hash
    over the messages -- differ between runs of identical code.
    """
    return "\n".join(
        f"- `{table}({', '.join(columns[table])})`"
        for table in sorted(columns)
        if table in allowlist
    )


def render_prompt(
    columns: dict[str, tuple[str, ...]],
    allowlist: frozenset[str],
    *,
    as_of: str,
    template: str | None = None,
) -> str:
    from ..llm.prompts import load as load_prompt

    text = template if template is not None else load_prompt(PROMPT_ID).body
    return text.replace("{{SCHEMA}}", schema_text(columns, allowlist)).replace("{{AS_OF}}", as_of)


def parse_draft(data: dict[str, Any], *, raw: str = "") -> FreeformDraft:
    sql = data.get("sql")
    return FreeformDraft(
        sql=(sql or "").strip(),
        unit=str(data.get("unit") or "other"),
        why_not=str(data.get("why_not") or ""),
        assumption=str(data.get("assumption") or ""),
        raw=raw,
    )


def draft_sql(
    question: str,
    columns: dict[str, tuple[str, ...]],
    allowlist: frozenset[str],
    llm: LLM,
    *,
    as_of: str,
    max_tokens: int = 1200,
) -> FreeformDraft:
    """One structured call. The SQL it returns has not been checked by anything yet."""
    messages: list[Msg] = [
        Msg(role="system", content=render_prompt(columns, allowlist, as_of=as_of)),
        Msg(role="user", content=question),
    ]
    result = llm.structured(
        prompt_id=PROMPT_ID, messages=messages, schema=SCHEMA, max_tokens=max_tokens
    )
    return parse_draft(result.data, raw=result.raw)
