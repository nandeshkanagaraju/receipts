"""receipts.domain.ids — [P] pure: canonical JSON, and hashes built from it (D3).

Every identity in this system is a SHA-256 over canonical JSON. Not `hash()`, not
`id()`, not a uuid: those differ between two runs of the same code on the same
input, and an identity that differs between runs cannot be used to say "this is
the same plan as last time", which is the only reason to have one.

Canonical means: sorted keys, no insignificant whitespace, UTF-8 without escapes,
`Decimal` and `date` rendered as strings rather than coerced to float. The last
part matters most — `json.dumps` turns a `Decimal` into a float given the chance,
and a plan hash that depended on float repr would be stable on one machine and
not on another.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any


class IdentityError(TypeError):
    """A value with no canonical form. Never guessed at."""


def _plain(value: Any) -> Any:
    """Everything reduced to JSON's own types, losing nothing that identifies it."""
    if value is None or isinstance(value, bool | int | str):
        return value
    if isinstance(value, float):
        # Refused rather than rendered. A float in an identity is the one thing
        # that makes a hash machine-dependent, and there is no value of it here
        # that a Decimal would not carry better.
        raise IdentityError(f"float {value!r} cannot be part of an identity (D1, D3); use Decimal")
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return _plain(value.value)
    if isinstance(value, datetime):
        raise IdentityError(
            "a datetime cannot be part of an identity (D2): it is a clock reading. "
            "Use the injected date."
        )
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    if isinstance(value, list | tuple | set | frozenset):
        items = [_plain(v) for v in value]
        if isinstance(value, set | frozenset):
            # A set has no order, so its canonical form is sorted. Sorted by the
            # rendered form, so the ordering does not depend on Python's.
            items.sort(key=lambda item: json.dumps(item, sort_keys=True, ensure_ascii=False))
        return items
    if hasattr(value, "model_dump"):
        return _plain(value.model_dump(mode="python"))
    if hasattr(value, "__dataclass_fields__"):
        return _plain({f: getattr(value, f) for f in value.__dataclass_fields__})
    raise IdentityError(f"{type(value).__name__} has no canonical form")


def canonical_json(value: Any) -> str:
    """The one rendering everything else hashes."""
    return json.dumps(
        _plain(value),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )


def content_hash(value: Any, *, length: int | None = None) -> str:
    """SHA-256 of the canonical JSON, hex. `length` truncates for display only."""
    digest = hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
    return digest[:length] if length else digest


def short_hash(value: Any) -> str:
    """The 16-character form receipts use (SDD §8)."""
    return content_hash(value, length=16)
