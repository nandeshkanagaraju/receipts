"""receipts.config — [IO] loads config/*.yaml.

SDD §26. Every model is strict and forbids unknown keys, so a typo or a wrong
type raises at startup rather than silently taking a default. Secrets are never
read from these files: settings name the *environment variable* that holds a
DSN or key, and the value is fetched from the environment on demand.
"""

from __future__ import annotations

import os
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from pydantic import BaseModel, BeforeValidator, ConfigDict

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"


def _to_decimal(v: Any) -> Any:
    """Accept a YAML string and produce an exact Decimal (D1: never float)."""
    return Decimal(v) if isinstance(v, str) else v


def _to_tuple(v: Any) -> Any:
    """YAML gives lists; the domain wants immutable, explicitly ordered tuples (D4)."""
    return tuple(v) if isinstance(v, list) else v


Dec = Annotated[Decimal, BeforeValidator(_to_decimal)]
StrTuple = Annotated[tuple[str, ...], BeforeValidator(_to_tuple)]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


# --------------------------------------------------------------------------- #
# settings.yaml
# --------------------------------------------------------------------------- #
class Paths(Strict):
    data_dir: str
    duckdb: str
    gateway_sqlite: str
    manifest: str
    semantic_dir: str
    prompts_dir: str
    recordings_dir: str
    results_dir: str


class DuckDBAdapter(Strict):
    read_only: bool
    enable_external_access: bool


class PostgresAdapter(Strict):
    dsn_env: str
    statement_timeout_ms: int
    application_name: str


class Adapters(Strict):
    duckdb: DuckDBAdapter
    postgres: PostgresAdapter


class Provider(Strict):
    provider: Literal["anthropic", "openai", "gemini"]
    model: str


class MaxTokens(Strict):
    intent: int
    planner: int
    repair: int
    composer: int
    baseline: int


class Budget(Strict):
    tokens_in: int
    tokens_out: int


class LLMSettings(Strict):
    mode: Literal["live", "record", "replay"]
    temperature: int
    primary: Provider
    secondary: Provider
    max_tokens: MaxTokens
    budget_per_question: Budget


class Freeform(Strict):
    enabled: bool


class WhySettings(Strict):
    min_rel_change: Dec
    min_z: Dec
    concentration: Dec
    max_levels: int
    query_budget: int
    trailing_periods: int
    dimensions: StrTuple


class Routing(Strict):
    prefer_oltp_recent: bool
    postgres_window_days: int


class CacheSettings(Strict):
    path: str
    plan_cache_enabled: bool
    result_cache_enabled: bool


class BridgeSettings(Strict):
    base_url_env: str
    token_env: str
    timeout_s: float
    max_pages: int


class DemoSettings(Strict):
    enabled: bool
    questions_per_minute: int
    daily_spend_cap_micro_usd: int


class TestingSettings(Strict):
    suite_ceiling_seconds: int


class Settings(Strict):
    as_of: date
    paths: Paths
    adapters: Adapters
    llm: LLMSettings
    freeform: Freeform
    row_limit: int
    timeout_s: float
    why: WhySettings
    routing: Routing
    cache: CacheSettings
    bridge: BridgeSettings
    demo: DemoSettings
    testing: TestingSettings


# --------------------------------------------------------------------------- #
# thresholds.yaml  (PDD §10)
# --------------------------------------------------------------------------- #
class Constraint(Strict):
    label: str
    comparator: Literal["<=", ">="]
    value: Dec


class Threshold(Strict):
    measure: str
    constraints: Annotated[tuple[Constraint, ...], BeforeValidator(_to_tuple)]
    ship_blocking: bool = False


class Thresholds(Strict):
    thresholds: dict[str, Threshold]


# --------------------------------------------------------------------------- #
# roles.yaml  (SDD §21)
# --------------------------------------------------------------------------- #
class Role(Strict):
    capabilities: StrTuple
    reporting_currency: str
    countries: StrTuple | Literal["ALL"] | None = None
    regions: StrTuple | None = None


class Roles(Strict):
    roles: dict[str, Role]


# --------------------------------------------------------------------------- #
# pricing.yaml  (SDD §23)
# --------------------------------------------------------------------------- #
class ModelPrice(Strict):
    input_micro_usd_per_mtok: int
    output_micro_usd_per_mtok: int


class Pricing(Strict):
    models: dict[str, ModelPrice]


# --------------------------------------------------------------------------- #
# loading
# --------------------------------------------------------------------------- #
def _read_yaml(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(f"config file missing: {path}")
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_settings(path: Path | None = None) -> Settings:
    return Settings.model_validate(_read_yaml(path or CONFIG_DIR / "settings.yaml"))


def load_thresholds(path: Path | None = None) -> Thresholds:
    return Thresholds.model_validate(_read_yaml(path or CONFIG_DIR / "thresholds.yaml"))


def load_roles(path: Path | None = None) -> Roles:
    return Roles.model_validate(_read_yaml(path or CONFIG_DIR / "roles.yaml"))


def load_pricing(path: Path | None = None) -> Pricing:
    return Pricing.model_validate(_read_yaml(path or CONFIG_DIR / "pricing.yaml"))


def secret_from_env(var_name: str) -> str:
    """Fetch a secret the settings only *named*. Missing is an error, not ''."""
    try:
        return os.environ[var_name]
    except KeyError as exc:
        raise RuntimeError(f"required secret {var_name} is not set in the environment") from exc


__all__ = [
    "Settings",
    "Thresholds",
    "Roles",
    "Pricing",
    "load_settings",
    "load_thresholds",
    "load_roles",
    "load_pricing",
    "secret_from_env",
    "CONFIG_DIR",
]
