"""receipts.api.errors — every engine exception becomes a typed code (SDD §19).

The rule this file exists for: **no handler returns a bare 500.** A 500 tells the
asker the system broke and tells the operator nothing about which part; a typed
code says which dependency failed and whether trying again is worth anything.

`DENIED` and `ABSTAIN` are deliberately absent. They are answer *statuses*, not
errors -- a refusal is a successful outcome of a question the system understood,
and turning it into an HTTP error would make "you may not see UAE" indistinguish-
able from "the database is down".

The mapping is a table rather than a chain of `except` clauses so that
`test_every_exception_maps_to_code` can walk it: a new engine exception with no
entry here fails that test rather than reaching a user as a 500.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..compile.compiler import CompileError
from ..compile.currency import CurrencyError
from ..compile.scope import CapabilityRequired, MissingScope, ScopeUnreachable
from ..execute.adapters.base import DbError, DbSchemaMissing, DbTimeout, DbUnavailable
from ..llm.base import BudgetExceeded, LLMError, ModelUnavailable, RecordingMissing, Transient
from ..safety.guard import GuardError
from ..safety.rewrite import RewriteError
from ..semantic.catalog import CatalogError


@dataclass(frozen=True)
class ErrorBody:
    """SDD §19's error shape. `retryable` is advice, not decoration.

    It answers the only question the caller has when something fails: is this
    worth trying again, or is it the same answer every time? A rate limit clears;
    a rejected query does not.
    """

    code: str
    message: str
    retryable: bool
    receipt_id: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def payload(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
        }
        if self.receipt_id:
            body["receipt_id"] = self.receipt_id
        body.update(self.extra)
        return body


class ApiError(Exception):
    """An error already carrying its code. Raised by routes, never by the engine."""

    def __init__(self, body: ErrorBody, status: int) -> None:
        super().__init__(body.message)
        self.body = body
        self.status = status


# code -> (HTTP status, retryable). One place, so the table below stays readable.
CODES: dict[str, tuple[int, bool]] = {
    "AUTH_REQUIRED": (401, False),
    "FORBIDDEN": (403, False),
    "RATE_LIMITED": (429, True),
    "BUDGET_EXCEEDED": (429, False),
    "MODEL_UNAVAILABLE": (503, True),
    "DB_TIMEOUT": (504, True),
    "DB_UNAVAILABLE": (503, True),
    "BRIDGE_UNAVAILABLE": (503, True),
    "GUARD_REJECTED": (422, False),
    "VALIDATION_FAILED": (422, False),
    "NOT_FOUND": (404, False),
    "INTERNAL": (500, False),
}

# Engine exception -> code. Ordered most specific first: `DbTimeout` is a
# `DbError`, and a dict walk takes the first match.
EXCEPTION_CODES: tuple[tuple[type[BaseException], str], ...] = (
    (DbTimeout, "DB_TIMEOUT"),
    (DbUnavailable, "DB_UNAVAILABLE"),
    (DbSchemaMissing, "DB_UNAVAILABLE"),
    (DbError, "DB_UNAVAILABLE"),
    (BudgetExceeded, "BUDGET_EXCEEDED"),
    (ModelUnavailable, "MODEL_UNAVAILABLE"),
    (RecordingMissing, "MODEL_UNAVAILABLE"),
    (Transient, "MODEL_UNAVAILABLE"),
    (LLMError, "MODEL_UNAVAILABLE"),
    (GuardError, "GUARD_REJECTED"),
    (RewriteError, "GUARD_REJECTED"),
    (CapabilityRequired, "FORBIDDEN"),
    (MissingScope, "INTERNAL"),
    (ScopeUnreachable, "VALIDATION_FAILED"),
    (CompileError, "VALIDATION_FAILED"),
    (CurrencyError, "VALIDATION_FAILED"),
    (CatalogError, "VALIDATION_FAILED"),
)

# Codes that tell the caller a model-free path is still open (§24, J7).
CATALOG_MODE_CODES = frozenset({"MODEL_UNAVAILABLE", "BUDGET_EXCEEDED"})


def code_for(exc: BaseException) -> str:
    """The typed code for an engine exception, or `INTERNAL`.

    `INTERNAL` is the honest answer for something unrecognised, and it is still a
    typed body rather than a stack trace: the caller learns that the failure is
    ours and not theirs, which is all an unknown failure can honestly say.
    """
    for exception_type, code in EXCEPTION_CODES:
        if isinstance(exc, exception_type):
            return code
    return "INTERNAL"


def body_for(exc: BaseException, *, receipt_id: str | None = None) -> ErrorBody:
    """An engine exception as an `ErrorBody`, with no internals leaking.

    The message is the code's own sentence, not `str(exc)`. An adapter's message
    can name a table the asker may not see, and a scope refusal that discloses
    the table it refused is not a refusal.
    """
    code = code_for(exc)
    status, retryable = CODES[code]
    extra: dict[str, Any] = {"catalog_mode": True} if code in CATALOG_MODE_CODES else {}
    return ErrorBody(
        code=code,
        message=MESSAGES[code],
        retryable=retryable,
        receipt_id=receipt_id,
        extra=extra,
    )


def status_for(code: str) -> int:
    return CODES[code][0]


MESSAGES: dict[str, str] = {
    "AUTH_REQUIRED": "This endpoint needs a token.",
    "FORBIDDEN": "That is outside what this role may see.",
    "RATE_LIMITED": "Too many questions in a short time. Try again shortly.",
    "BUDGET_EXCEEDED": "This question would cost more than its budget allows.",
    "MODEL_UNAVAILABLE": ("The model is unavailable. Catalog mode still answers from saved plans."),
    "DB_TIMEOUT": "The query took longer than the time allowed.",
    "DB_UNAVAILABLE": "The warehouse could not be reached.",
    "BRIDGE_UNAVAILABLE": "The live gateway could not be reached.",
    "GUARD_REJECTED": "That query is not one this service may run.",
    "VALIDATION_FAILED": "That request could not be mapped to a governed query.",
    "NOT_FOUND": "No such receipt.",
    "INTERNAL": "Something on our side failed. The failure is recorded.",
}

__all__ = [
    "CATALOG_MODE_CODES",
    "CODES",
    "EXCEPTION_CODES",
    "ApiError",
    "ErrorBody",
    "body_for",
    "code_for",
    "status_for",
]
