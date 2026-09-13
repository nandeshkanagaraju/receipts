"""receipts.api.auth — the token says who; `roles.yaml` says what (SDD §21).

**The whole design is one sentence: the token carries a role name and nothing
else that matters, and scope is recomputed server-side on every request.**

A JWT is a bearer credential the holder can read and, if the secret ever leaks,
write. So the safe assumption is that every claim in it is attacker-controlled,
and the only defence that survives that assumption is to use as little of it as
possible. This module reads exactly one claim -- `role` -- and derives everything
else from a file on the server.

`test_extra_claims_are_ignored` puts a `regions: ["AE-DXB"]` claim in a
well-signed token and asserts the resulting scope is unchanged. That test is the
point of the file: a signed token is proof of identity, never of permission.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jwt

from ..domain.types import Scope

ALGORITHM = "HS256"
EXPIRY_SECONDS = 8 * 60 * 60  # §21: eight hours.

# Claims this service reads. Everything else in a token is ignored -- not
# rejected, ignored: a token with extra claims is not an attack to be reported,
# it is simply a token whose extra claims mean nothing here.
READ_CLAIMS = ("role", "exp", "iat")


class AuthError(Exception):
    """Bad, expired, or absent credentials. Becomes AUTH_REQUIRED (401)."""


@dataclass(frozen=True)
class Principal:
    """Who is asking. Deliberately not what they may see."""

    role: str
    token_id: str = ""


def issue(role: str, secret: str, *, now: int | None = None) -> str:
    """A demo token carrying the role name and the times, and nothing else.

    No regions, no capabilities, no currency. Anything put in here would have to
    be ignored on the way back in, and a claim that is written and then ignored
    invites somebody to start trusting it.
    """
    issued = int(time.time()) if now is None else now
    payload = {"role": role, "iat": issued, "exp": issued + EXPIRY_SECONDS}
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def principal_from(token: str, secret: str) -> Principal:
    """Verify the signature and expiry, and read the role. Nothing else."""
    if not token:
        raise AuthError("no token")
    try:
        claims: dict[str, Any] = jwt.decode(token, secret, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("token expired") from exc
    except jwt.InvalidTokenError as exc:
        # Covers a tampered payload, a wrong signature, and an `alg: none`
        # header -- `algorithms=` is what makes the last one an error rather
        # than an accepted unsigned token.
        raise AuthError("token is not valid") from exc
    role = str(claims.get("role") or "")
    if not role:
        raise AuthError("token carries no role")
    return Principal(role=role, token_id=str(claims.get("jti") or ""))


def bearer_token(header: str | None) -> str:
    """The token out of an `Authorization` header, or "" if there is none."""
    if not header:
        return ""
    scheme, _, value = header.partition(" ")
    if scheme.lower() != "bearer":
        return ""
    return value.strip()


def scope_for_role(role: str, roles: dict[str, Any], places: dict[str, tuple[str, ...]]) -> Scope:
    """Scope from `roles.yaml`, every request, for the role the token named.

    This is the only way a `Scope` is built on the request path. It takes the
    role name and the server's own files; there is no parameter through which a
    caller could influence the result, which is what D7 asks for.
    """
    spec = roles.get(role)
    if spec is None:
        raise AuthError(f"unknown role {role!r}")
    capabilities = tuple(spec.get("capabilities") or [])
    if spec.get("regions"):
        regions: Any = tuple(spec["regions"])
    elif spec.get("countries") and spec["countries"] != "ALL":
        wanted = set(spec["countries"])
        regions = tuple(sorted(r for r, names in places.items() if wanted & set(names)))
    else:
        regions = "ALL"
    return Scope(
        role=role,
        region_ids=regions,
        capabilities=capabilities,
        reporting_currency=str(spec.get("reporting_currency") or ""),
    ).with_hash()


def load_roles(path: Path) -> dict[str, Any]:
    import yaml

    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    roles: dict[str, Any] = loaded.get("roles", {})
    return roles


__all__ = [
    "ALGORITHM",
    "AuthError",
    "Principal",
    "bearer_token",
    "issue",
    "load_roles",
    "principal_from",
    "scope_for_role",
]
