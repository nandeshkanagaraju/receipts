"""receipts.agent.compose — [IO] one to four sentences over a result table.

SDD §14.1. The table is wrapped in a fenced data block with an instruction that
its contents are data and never instructions (D14) -- and that instruction is
made *enforceable* by the grounding check that runs afterwards (D13), not by the
model's goodwill.

That pairing is the design. A prompt asking a model not to follow embedded
instructions is a request; a check that throws away any narration containing a
number the table does not have is a guarantee. The prompt reduces how often the
check has to fire; the check is what makes the prompt safe to rely on.

At most 50 rows reach the model (§14.1), plus a totals row beyond that. A
narration is about the shape of a result, and fifty rows is more than enough to
describe a shape -- while a thousand rows is a thousand chances for one of them
to contain something that reads like an instruction.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from ..domain.types import ResolvedPlan, ResultTable
from ..llm.base import LLM, Msg

PROMPT_ID = "composer"
MAX_ROWS = 50


@dataclass(frozen=True, slots=True)
class Narration:
    text: str
    rows_shown: int = 0
    truncated: bool = False


def render_table(table: ResultTable | None, *, max_rows: int = MAX_ROWS) -> tuple[str, int, bool]:
    """The table as text, capped, with a totals row when it was capped."""
    if table is None or not table.columns:
        return "(no rows)", 0, False
    header = " | ".join(c.name for c in table.columns)
    lines = [header, "-" * len(header)]
    shown = table.rows[:max_rows]
    for row in shown:
        lines.append(" | ".join("" if cell is None else str(cell) for cell in row))
    truncated = len(table.rows) > max_rows
    if truncated:
        # A totals row rather than a silent cut. "Showing 50 of 264" tells the
        # model the shape it is describing is a sample; nothing tells it that if
        # the rows simply stop.
        totals = []
        for index, column in enumerate(table.columns):
            if column.kind != "value":
                totals.append("(all rows)")
                continue
            values = [
                Decimal(str(r[index])) for r in table.rows if isinstance(r[index], int | Decimal)
            ]
            totals.append(str(sum(values, Decimal(0))) if values else "")
        lines.append("-" * len(header))
        lines.append(" | ".join(totals) + f"   [total over all {len(table.rows)} rows]")
    return "\n".join(lines), len(shown), truncated


def plan_summary(resolved: ResolvedPlan, metric_label: str = "") -> str:
    """What was measured, in words the model can repeat without inventing."""
    from datetime import timedelta

    last = resolved.end_exclusive - timedelta(days=1)
    parts = [
        f"Metric: {metric_label or resolved.plan.name}",
        f"Window: {resolved.start.isoformat()} to {last.isoformat()} (business dates)",
    ]
    if resolved.plan.dimensions:
        parts.append(f"Broken down by: {', '.join(resolved.plan.dimensions)}")
    if resolved.plan.filters:
        shown = ", ".join(
            f"{f.dimension} {f.op} {', '.join(f.values)}" for f in resolved.plan.filters
        )
        parts.append(f"Filtered to: {shown}")
    if resolved.plan.compare_to:
        parts.append(f"Compared with: {resolved.plan.compare_to.replace('_', ' ')}")
    parts.append(f"Reporting currency: {resolved.reporting_currency}")
    if resolved.defaults_applied:
        parts.append("Defaults applied: " + "; ".join(resolved.defaults_applied))
    return "\n".join(f"- {p}" for p in parts)


def render_prompt(
    *, question: str, table: ResultTable | None, summary: str, template: str | None = None
) -> tuple[str, int, bool]:
    from ..llm.prompts import load as load_prompt

    text = template if template is not None else load_prompt(PROMPT_ID).body
    rendered, shown, truncated = render_table(table)
    filled = (
        text.replace("{{TABLE}}", rendered)
        .replace("{{SUMMARY}}", summary)
        .replace("{{QUESTION}}", question)
    )
    return filled, shown, truncated


def compose(
    question: str,
    resolved: ResolvedPlan,
    table: ResultTable | None,
    language: str,
    llm: LLM,
    *,
    metric_label: str = "",
    max_tokens: int = 1024,
) -> Narration:
    """Stage 10. One call; the grounding check decides whether it is used."""
    summary = plan_summary(resolved, metric_label)
    prompt, shown, truncated = render_prompt(question=question, table=table, summary=summary)
    result = llm.text(
        prompt_id=PROMPT_ID,
        messages=[
            Msg(role="system", content=prompt),
            Msg(role="user", content=f"Answer in {language}. The question was: {question}"),
        ],
        max_tokens=max_tokens,
    )
    return Narration(text=result.text.strip(), rows_shown=shown, truncated=truncated)


TEMPLATES = Path(__file__).resolve().parent / "templates"


def load_templates(language: str, directory: Path = TEMPLATES) -> dict[str, str]:
    """The fallback sentences for a language, falling back to English itself.

    This lives in compose rather than in grounding because grounding is declared
    [P] in SDD §3 and reading a file is I/O. The charter test caught it.
    """
    base = language.split("-")[0]
    path = directory / f"{base}.json"
    if not path.exists():
        path = directory / "en.json"
    loaded = json.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in loaded.items() if not k.startswith("_")}


def template_narration(
    templates: dict[str, str],
    *,
    key: str,
    **fields: Any,
) -> str:
    """A deterministic sentence, with any missing field left visible rather than blank.

    A template that silently rendered `{metric}` as an empty string would produce
    a grammatical sentence missing its subject, which reads as a bug in the data
    rather than a bug in the template.
    """
    text = templates.get(key) or templates.get("scalar", "{value}")
    for name, value in fields.items():
        text = text.replace("{" + name + "}", str(value))
    return text
