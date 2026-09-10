"""D15 — prompts are versioned files in prompts/, never inline strings."""

from __future__ import annotations

from tests.charter.checks import (
    INLINE_PROMPT_LIMIT,
    find_inline_prompts,
    inline_prompt_roots,
)


def test_no_inline_prompts() -> None:
    roots = inline_prompt_roots()
    assert any(r.exists() for r in roots), "precondition: no prompt-bearing roots exist"
    violations = find_inline_prompts()
    print(f"\nD15: scanned {len(roots)} roots, literal limit {INLINE_PROMPT_LIMIT} chars")
    assert not violations, "inline prompt literals:\n" + "\n".join(str(v) for v in violations)
