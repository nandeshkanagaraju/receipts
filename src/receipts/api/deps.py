"""receipts.api.deps — one place where the request path gets its engine.

Built once at startup and handed to routes. The alternative -- each route
reaching for a module global -- is how a test ends up unable to swap the adapter,
and how a second code path for "the same thing but in the API" gets written.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from ..agent.orchestrator import Deps
from ..domain.types import Scope
from ..observability.audit import AuditLog
from ..observability.spend import DailySpend
from .auth import load_roles, scope_for_role
from .ratelimit import RateLimiter

REPO = Path(__file__).resolve().parents[3]

# A fixed, obviously-fake secret for demo mode. Named rather than inlined so that
# `test_no_secrets_in_config` and a reader both see it is a placeholder, and long
# enough for HS256 not to warn -- a warning nobody can act on gets ignored, and
# then so does the next one.
DEMO_SECRET = "demo-secret-not-for-production-32-bytes-minimum"


@dataclass
class Runtime:
    """Everything a route needs that is not the request."""

    deps: Deps
    roles: dict[str, Any]
    places: dict[str, tuple[str, ...]]
    audit: AuditLog
    limiter: RateLimiter
    spend: DailySpend
    as_of: date
    jwt_secret: str
    catalog_mode: bool = False
    demo_mode: bool = True
    _scopes: dict[str, Scope] = field(default_factory=dict)

    def scope(self, role: str) -> Scope:
        """The role's scope, recomputed from `roles.yaml` (D7, §21).

        Cached by role name only. The cache key is the thing the token carries;
        nothing a caller sends can reach this function, which is what makes the
        cache safe.
        """
        if role not in self._scopes:
            self._scopes[role] = scope_for_role(role, self.roles, self.places)
        return self._scopes[role]


def _audit_path() -> Path:
    """Where the append-only audit log lives.

    `RECEIPTS_AUDIT_PATH` exists because some hosts give the application a
    read-only filesystem with one writable directory -- AWS Lambda is the case
    that forced it, where everything outside `/tmp` is read-only. The warehouse
    is opened read-only anyway (D8), so the audit log is the only thing that
    needs somewhere to write, and hardcoding it under `data/` made the whole
    application undeployable on such a host.

    A log on ephemeral storage does not survive a restart. That is stated in
    LIMITATIONS rather than hidden: the receipt itself is deterministic and
    reproducible from the repository, and the audit log is an index over what
    happened, not the evidence.
    """
    override = os.environ.get("RECEIPTS_AUDIT_PATH")
    return Path(override) if override else REPO / "data" / "audit.sqlite"


def _questions_per_minute(default: int) -> int:
    """The demo's rate limit, overridable by `RECEIPTS_QPM`.

    Not a way to switch the limiter off -- it always runs, and its own tests
    assert it fires. It exists because the browser suite is one client asking as
    one role and legitimately exceeds a demo's allowance: the page now answers
    an example on every load, so opening the page costs a question. Waiting out
    a 60-second window per collision made the journey tests slower than the
    journeys they test.

    The deployed demo sets nothing and gets the value from settings.yaml.
    """
    raw = os.environ.get("RECEIPTS_QPM")
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _demo_mode(default: bool) -> bool:
    """`DEMO_MODE` from the environment, else the settings value.

    Anything other than a recognised truthy string is false: a deployment that
    typo'd the variable gets the locked-down behaviour, not the open one.
    """
    raw = os.environ.get("DEMO_MODE")
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def build_runtime(*, audit_path: Path | None = None, llm: Any = None) -> Runtime:
    """Wire the engine for serving. Replay by default; `record` never here."""
    import sys

    sys.path.insert(0, str(REPO / "scripts"))
    import gate_dev

    from ..config import load_settings
    from ..execute.adapters.duckdb import DuckDBAdapter, table_columns
    from ..llm.budget import BudgetedLLM, QuestionBudget
    from ..llm.replay import ReplayLLM
    from ..semantic import loader

    settings = load_settings()
    catalog = loader.load()
    roles = load_roles(REPO / "config" / "roles.yaml")
    places = gate_dev.places_from_db()
    db_path = REPO / "data" / "kestrel.duckdb"

    if llm is None:
        recordings = REPO / "eval" / "recordings" / "receipts"
        llm = ReplayLLM(
            recordings,
            provider=settings.llm.primary.provider,
            model=settings.llm.primary.model,
        )
    budget = settings.llm.budget_per_question
    deps = Deps(
        catalog=catalog,
        llm=BudgetedLLM(
            llm, QuestionBudget(tokens_in=budget.tokens_in, tokens_out=budget.tokens_out)
        ),
        adapter=DuckDBAdapter(db_path),
        roles=roles,
        places=places,
        data_version=os.environ.get("RECEIPTS_DATA_VERSION", "dev"),
        first_date=settings.data.first_business_date,
        last_date=settings.data.last_business_date,
        row_limit=settings.row_limit,
        timeout_s=settings.timeout_s,
        freeform_enabled=settings.freeform.enabled,
        columns=table_columns(db_path),
    )
    return Runtime(
        deps=deps,
        roles=roles,
        places=places,
        audit=AuditLog(audit_path or _audit_path()),
        limiter=RateLimiter(per_minute=_questions_per_minute(settings.demo.questions_per_minute)),
        spend=DailySpend(cap_micro_usd=settings.demo.daily_spend_cap_micro_usd),
        # SDD §28: DEMO_MODE enables demo login, the rate limit and the
        # daily cap. The env var wins over the file so one image serves
        # both a demo and a real deployment; `settings.demo.enabled` is
        # the default and, until M20, was read by nothing at all.
        demo_mode=_demo_mode(settings.demo.enabled),
        as_of=settings.as_of,
        jwt_secret=os.environ.get("RECEIPTS_JWT_SECRET", DEMO_SECRET),
    )


__all__ = ["REPO", "Runtime", "build_runtime"]
