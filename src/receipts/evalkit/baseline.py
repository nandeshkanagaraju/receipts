"""receipts.evalkit.baseline — [IO] may do I/O (SDD §3): baseline B0, SDD §25.4.

The thing the thesis is measured against. PDD §5 is explicit that this must be a
*strong* free-form text-to-SQL baseline, not a strawman, and the rule it sets is
that the baseline gets the definitions too: full DDL with column comments, the
entire glossary, ten worked examples, one retry, and permission to refuse. We are
testing an architecture, not whether one side knew what "success rate" means.

Built before any Receipts engine code exists, deliberately, so that nothing here
can be shaped by Receipts' results. The only Receipts machinery it shares is the
guard (§12.1) and the read-only connection -- the two safety layers -- and it
does **not** get the scope rewrite (§12.2). Its scope is stated in words in its
prompt instead, and anything out of scope that comes back counts as a leak.
That asymmetry *is* the measurement.

Four things beyond the letter of §25.4, each of which makes the baseline
stronger and none of which Receipts gets exclusively:

1. **`as_of` and yesterday, stated.** Without a date the model cannot resolve
   "yesterday" at all, and the failure would be a harness artefact rather than a
   finding about free-form SQL. Receipts is given the same date.
2. **The distinct values of every low-cardinality enum column.** `status`,
   `method`, `channel`, `card_network`, `failure_reason`. A model that guesses
   `status = 'success'` when the literal is `'captured'` fails for a reason that
   has nothing to do with the thesis. This is the single largest strengthening
   here, and it removes a whole class of cheap wins.
3. **Row counts per table**, so the model can tell a fact from a dimension.
4. **The retry also fires on a guard rejection**, carrying the guard's typed
   reason, not just on a database error. §25.4 says "one retry on SQL failure";
   a refused query is a failed query from the model's side, and a retry the
   model cannot learn from is not a retry.

Still exactly one retry, so the budget in §25.4 is unchanged.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import duckdb

from ..llm.base import LLM, Msg
from ..safety.guard import guard
from .types import ScorableAnswer, Trial

REPO = Path(__file__).resolve().parents[3]
GLOSSARY = REPO / "docs" / "GLOSSARY.md"
REFERENCE_SQL = REPO / "eval" / "reference_sql"
ROLES = REPO / "config" / "roles.yaml"
PROMPT_ID = "baseline"

# Never in the semantic layer or any allowlist (SDD §5.2). Absent from DuckDB
# entirely, but named here so the allowlist says so rather than relying on a
# table happening not to exist in one of the two adapters.
NEVER_ALLOWLISTED: frozenset[str] = frozenset({"customers"})

# Capability-gated (SDD §11.3): excluded from the allowlist for roles without
# `finance`. The baseline is told, in words, that it cannot see them.
FINANCE_TABLES: frozenset[str] = frozenset({"settlements", "settlement_items"})

# Ten fixed examples, chosen once and never tuned. Spread across traps and
# shapes rather than picked for being easy: six of the eleven trap families are
# represented, and three of the ten are non-answerable so the escape hatches are
# demonstrated rather than merely described. Listed by qid in the prompt header,
# per §25.4, so a reader can check them against the dev set.
FEWSHOT_QIDS: tuple[str, ...] = (
    "DV-001",  # attempts_vs_orders   scalar, ratio
    "DV-002",  # local_time           scalar, count
    "DV-003",  # multi_currency       scalar, money, cross-currency
    "DV-004",  # authorised_vs_captured scalar, money
    "DV-005",  # capture_vs_settlement  scalar, duration
    "DV-006",  # partial_refunds      scalar, ratio
    "DV-007",  # ranking              table, top-k
    "DV-013",  # AMB -> CLARIFY
    "DV-016",  # UNA -> CANNOT_ANSWER (no such data)
    "DV-018",  # DENY -> CANNOT_ANSWER (out of scope)
)

# The refusals the three non-answerable examples demonstrate. Authored here
# rather than read from the question file, because the question file records
# *that* a question is unanswerable and not what a good refusal sounds like.
# Fixed with the qids above and never tuned against a score.
FEWSHOT_REFUSALS: dict[str, str] = {
    "DV-013": (
        'CLARIFY: by "last quarter" do you mean the calendar quarter '
        "(Apr-Jun) or Kestrel's fiscal quarter (Jul-Sep), and which measure "
        "do you want -- captured GMV, orders, or units?"
    ),
    "DV-016": (
        "CANNOT_ANSWER: there is no customer satisfaction data in this "
        "database. The schema covers orders, payments, refunds and "
        "settlements only, so no query can answer this."
    ),
    "DV-018": (
        "CANNOT_ANSWER: Dubai showrooms are in AE, which is outside the "
        "regions this role may see. I can answer the same question for the "
        "regions in scope."
    ),
}


# Columns whose distinct values are small enough to enumerate, and whose literal
# spelling the model cannot guess. Capped: a column that turns out to have a
# thousand values must not silently paste a thousand values into the prompt.
ENUM_COLUMNS: tuple[tuple[str, str], ...] = (
    ("orders", "channel"),
    ("orders", "status"),
    ("orders", "currency"),
    ("payment_attempts", "method"),
    ("payment_attempts", "status"),
    ("payment_attempts", "card_network"),
    ("payment_attempts", "failure_reason"),
    ("payment_attempts", "currency"),
    ("payment_attempts", "emi_tenure_months"),
    ("refunds", "status"),
    ("refunds", "reason"),
    ("settlements", "currency"),
    ("countries", "currency"),
    ("countries", "timezone"),
)
ENUM_VALUE_CAP = 24

COLUMN_COMMENTS: dict[tuple[str, str], str] = {
    ("countries", "country_code"): (
        "ISO country code. One timezone per country (a simplification)."
    ),
    ("countries", "currency"): "The country's local currency. Facts are stored in this currency.",
    ("countries", "timezone"): "IANA timezone used to derive business_date from created_at_utc.",
    ("regions", "region_id"): "Region key, e.g. 'IN-TN' for Tamil Nadu.",
    ("regions", "country_code"): "Joins to countries.country_code.",
    ("cities", "city_id"): "City key. Chennai is in region IN-TN.",
    ("cities", "region_id"): "Joins to regions.region_id.",
    ("showrooms", "showroom_id"): "Store key. Every order happens at one showroom.",
    ("showrooms", "city_id"): "Joins to cities.city_id.",
    ("showrooms", "region_id"): "Denormalised from cities. Use this to scope by region.",
    ("showrooms", "country_code"): "Denormalised. Use this to scope by country.",
    ("showrooms", "opened_on"): "Date the showroom opened. Stored as text (ISO date).",
    ("products", "sku"): "Stock-keeping unit. Primary key.",
    ("products", "model_id"): "Groups SKUs of the same phone model across storage and colour.",
    ("products", "storage_gb"): "Storage in GB. NULL for accessories.",
    ("products", "is_accessory"): "TRUE for cases, chargers and cables, not phones.",
    ("product_notes", "note"): "Free-text note about a SKU.",
    ("prices", "price_minor"): "List price in the country's currency, in MINOR units.",
    ("prices", "valid_from"): "Inclusive start of the price's validity (ISO date text).",
    ("prices", "valid_to"): "Exclusive end. Open-ended prices may be NULL or a far date.",
    ("orders", "order_id"): "Primary key. One order, one basket, one showroom.",
    (
        "orders",
        "showroom_id",
    ): "Joins to showrooms.showroom_id. This is how an order gets a region.",
    ("orders", "channel"): "How the order was placed.",
    ("orders", "created_at_utc"): "Creation time in UTC. NOT the local time.",
    ("orders", "business_date"): (
        "The showroom's LOCAL date for this order, precomputed. "
        "Use this for 'yesterday' and any date grouping; using created_at_utc "
        "instead shifts rows across midnight in every country but the UK."
    ),
    ("orders", "currency"): "The order's currency: the showroom's country's currency.",
    ("orders", "total_minor"): "Order total in MINOR units of `currency`. BIGINT, never a float.",
    ("orders", "status"): ("Order lifecycle status. An order can be paid, abandoned or cancelled."),
    ("orders", "is_test"): (
        "TRUE for internal test orders. These are real rows in the table and are "
        "NOT business activity. Exclude them from every business metric."
    ),
    ("orders", "customer_id"): "Opaque customer key. The customers table is not available here.",
    ("order_items", "line_no"): "Line number within the order.",
    ("order_items", "qty"): "Units of this SKU on this line.",
    ("order_items", "unit_price_minor"): "Price per unit in MINOR units of the order's currency.",
    ("payment_attempts", "attempt_id"): "Primary key. One attempt at paying for one order.",
    ("payment_attempts", "order_id"): (
        "Joins to orders.order_id. An order can have SEVERAL attempts: a failed "
        "attempt followed by a successful one is two rows, one order."
    ),
    ("payment_attempts", "attempt_no"): "1 for the first attempt at an order, 2 for the next, etc.",
    ("payment_attempts", "method"): "Payment method used for this attempt.",
    ("payment_attempts", "card_network"): "Card network. NULL for non-card methods.",
    ("payment_attempts", "issuing_bank"): "The customer's bank. NULL for non-card methods.",
    (
        "payment_attempts",
        "acquiring_bank",
    ): "Kestrel's bank for this attempt. Joins to settlements.",
    ("payment_attempts", "emi_tenure_months"): "EMI tenure in months. NULL unless method is 'emi'.",
    ("payment_attempts", "amount_minor"): "Attempt amount in MINOR units of `currency`.",
    ("payment_attempts", "status"): (
        "Attempt outcome. 'authorized' means the bank approved it but the money "
        "has NOT been taken; 'captured' means it has. They are different events."
    ),
    ("payment_attempts", "failure_reason"): "Why a failed attempt failed. NULL unless failed.",
    ("payment_attempts", "created_at_utc"): "Attempt time in UTC. NOT the local time.",
    ("payment_attempts", "business_date"): "The showroom's LOCAL date for this attempt.",
    ("payment_attempts", "gateway_payment_id"): (
        "The gateway's own id. Two rows sharing one gateway_payment_id are the "
        "SAME payment recorded twice, not two payments."
    ),
    (
        "payment_attempts",
        "is_test",
    ): "TRUE for internal test traffic. Exclude from business metrics.",
    ("refunds", "refund_id"): "Primary key.",
    ("refunds", "attempt_id"): "The payment attempt being refunded.",
    ("refunds", "amount_minor"): (
        "Refund amount in MINOR units. This can be LESS than the attempt amount: "
        "a partial refund is normal and is not a cancelled sale."
    ),
    ("refunds", "status"): (
        "Refund lifecycle status. A pending refund has not moved any money yet."
    ),
    ("refunds", "reason"): "Why the refund was raised.",
    ("refunds", "business_date"): "The showroom's LOCAL date the refund was raised.",
    ("refunds", "processed_on"): "Date the refund actually moved money. NULL while pending.",
    ("settlements", "settlement_id"): "Primary key. One payout from one acquiring bank.",
    ("settlements", "acquiring_bank"): "The bank that paid out.",
    ("settlements", "settled_on"): "Date the money arrived. Later than the capture date.",
    ("settlements", "gross_minor"): "Gross amount in MINOR units before fees.",
    ("settlements", "fees_minor"): "Fees deducted, in MINOR units.",
    ("settlements", "net_minor"): "gross_minor - fees_minor. What actually arrived.",
    ("settlement_items", "settlement_id"): "Joins to settlements.settlement_id.",
    ("settlement_items", "attempt_id"): (
        "The captured attempt this line settles. An attempt that is captured but "
        "not yet settled has no row here."
    ),
    ("cities", "name"): "City name as a person would write it, e.g. 'Chennai'.",
    ("countries", "name"): "Country name.",
    ("regions", "name"): "Region name as a person would write it, e.g. 'Tamil Nadu'.",
    ("showrooms", "name"): "Showroom name. Use this when a question asks 'which store'.",
    ("order_items", "order_id"): "Joins to orders.order_id.",
    ("order_items", "sku"): "Joins to products.sku.",
    ("payment_attempts", "currency"): "The attempt's currency: the showroom's country's currency.",
    ("prices", "sku"): "Joins to products.sku.",
    ("prices", "country_code"): "The country this price applies in.",
    ("product_notes", "sku"): "Joins to products.sku.",
    ("products", "model_name"): "Human-readable model name, e.g. 'Kestrel 12 Pro'.",
    ("products", "colour"): "Colour. NULL for some accessories.",
    ("products", "launch_date"): "Launch date (ISO date text).",
    ("refunds", "order_id"): "Joins to orders.order_id.",
    ("refunds", "currency"): "The refund's currency: the order's currency.",
    ("refunds", "created_at_utc"): "When the refund was raised, in UTC. NOT the local time.",
    ("settlement_items", "amount_minor"): (
        "The part of the settlement attributable to this attempt, in MINOR units."
    ),
    ("settlements", "currency"): "The payout currency.",
    ("fx_rates", "rate_date"): "The date the rate applies to. One row per currency per date.",
    ("fx_rates", "currency"): "The currency being converted FROM.",
    ("fx_rates", "inr_per_unit"): "INR per one unit of `currency`. DECIMAL, never a float.",
    ("fx_rates", "usd_per_unit"): "USD per one unit of `currency`. DECIMAL, never a float.",
}

TABLE_COMMENTS: dict[str, str] = {
    "orders": "One row per order (basket). Fact table.",
    "order_items": "One row per line within an order. Fact table.",
    "payment_attempts": "One row per ATTEMPT to pay, not per order. Fact table.",
    "refunds": "One row per refund. Fact table.",
    "settlements": "One row per bank payout. Fact table. Requires the finance capability.",
    "settlement_items": "Links settlements to the attempts they settle. Requires finance.",
    "showrooms": "Stores. Dimension. The join path from any fact to a region or country.",
    "cities": "Dimension.",
    "regions": "Dimension. region_id looks like 'IN-TN'.",
    "countries": "Dimension. Carries the currency and timezone.",
    "products": "SKU dimension.",
    "product_notes": "Free-text notes per SKU.",
    "prices": "List price per SKU per country over time.",
    "fx_rates": "Daily FX rates. Use these for any cross-currency total.",
}

# The contract (§25.4). A result that follows it needs no heuristic at all.
CONTRACT_COLUMNS: tuple[str, str] = ("key", "value")

CLARIFY_PREFIX = "CLARIFY:"
CANNOT_PREFIX = "CANNOT_ANSWER:"


class BaselineError(RuntimeError):
    """Something the baseline could not do at all, as opposed to got wrong."""


@dataclass(frozen=True)
class Extraction:
    """What came back from the database, and how it had to be read.

    `mode` is reported, not just used. §25.4 asks for `unparseable` as a separate
    count, and lumping a heuristic read in with a contract-compliant one would
    hide how often the baseline ignored the contract it was given.
    """

    rows: tuple[tuple[str | None, Decimal], ...] = ()
    mode: str = "contract"  # contract | heuristic | unparseable
    detail: str = ""


@dataclass(frozen=True)
class Attempt:
    """One model call and what happened to its SQL."""

    sql: str = ""
    text: str = ""
    guard_reason: str = ""
    db_error: str = ""
    extraction: Extraction | None = None


@dataclass
class Scope:
    """The role's scope, in the two forms the baseline needs it in.

    `words` goes in the prompt because the baseline has no rewrite. `predicate`
    is never given to the model -- it is how the *leak check* knows what was out
    of scope, which is a different job from telling the model what to do.
    """

    role: str
    reporting_currency: str
    words: str
    region_ids: tuple[str, ...] | str = "ALL"
    country_codes: tuple[str, ...] | str = "ALL"
    capabilities: tuple[str, ...] = ()


def load_roles(path: Path = ROLES) -> dict[str, Any]:
    import yaml

    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    roles: dict[str, Any] = loaded.get("roles", {})
    return roles


def allowlist_for(role: str, tables: frozenset[str], *, roles: dict[str, Any]) -> frozenset[str]:
    """Tables this role may reference at all (SDD §11.3, §12.1 item 3)."""
    spec = roles.get(role)
    if spec is None:
        raise BaselineError(f"unknown role {role!r}")
    allowed = set(tables) - set(NEVER_ALLOWLISTED)
    if "finance" not in (spec.get("capabilities") or []):
        allowed -= set(FINANCE_TABLES)
    return frozenset(allowed)


def scope_for(role: str, *, roles: dict[str, Any]) -> Scope:
    """The role's scope as words, built from roles.yaml rather than restated."""
    spec = roles.get(role)
    if spec is None:
        raise BaselineError(f"unknown role {role!r}")
    currency = spec.get("reporting_currency", "USD")
    capabilities = tuple(spec.get("capabilities") or [])
    regions = spec.get("regions")
    countries = spec.get("countries")

    lines: list[str] = []
    region_ids: tuple[str, ...] | str = "ALL"
    country_codes: tuple[str, ...] | str = "ALL"
    if regions:
        region_ids = tuple(regions)
        joined = ", ".join(f"'{r}'" for r in regions)
        lines.append(
            f"You are a regional manager. You may see data for these regions ONLY: {joined}. "
            f"Every query must restrict to them, for example by joining through "
            f"`showrooms` and filtering `showrooms.region_id IN ({joined})`."
        )
    elif countries and countries != "ALL":
        country_codes = tuple(countries)
        joined = ", ".join(f"'{c}'" for c in countries)
        lines.append(
            f"You are a store operations manager. You may see data for these countries "
            f"ONLY: {joined}. Every query must restrict to them, for example by joining "
            f"through `showrooms` and filtering `showrooms.country_code IN ({joined})`."
        )
    else:
        lines.append(
            "You are a global finance analyst. You may see data for every country, so no "
            "geographic restriction applies. You must still exclude test rows."
        )

    if "finance" in capabilities:
        lines.append("You have the finance capability, so settlement tables are available to you.")
    else:
        lines.append(
            "You do NOT have the finance capability. The `settlements` and "
            "`settlement_items` tables are not available to you; a question that needs "
            "them cannot be answered."
        )
    lines.append(
        f"Your reporting currency is {currency}. Where a total spans more than one "
        f"currency, convert to {currency} using `fx_rates` before summing, and say so by "
        f"returning the converted number."
    )
    return Scope(
        role=role,
        reporting_currency=currency,
        words="\n\n".join(lines),
        region_ids=region_ids,
        country_codes=country_codes,
        capabilities=capabilities,
    )


def _enum_values(con: duckdb.DuckDBPyConnection, table: str, column: str) -> list[str] | None:
    rows = con.execute(
        f"select distinct {column} from {table} where {column} is not null "
        f"order by 1 limit {ENUM_VALUE_CAP + 1}"
    ).fetchall()
    if len(rows) > ENUM_VALUE_CAP:
        return None
    return [str(r[0]) for r in rows]


def render_ddl(con: duckdb.DuckDBPyConnection, tables: frozenset[str]) -> str:
    """`CREATE TABLE` for every allowlisted table, with comments and enum values.

    Rendered from the live schema rather than written out, so a column that is
    added or renamed cannot leave the baseline reading a schema that no longer
    exists. The comments are the part that is authored, and they live in
    `COLUMN_COMMENTS` next to a test that every allowlisted column has one.
    """
    enums = {(t, c) for t, c in ENUM_COLUMNS}
    out: list[str] = []
    counts = {
        r[0]: r[1]
        for r in con.execute(
            "select table_name, estimated_size from duckdb_tables() where schema_name='main'"
        ).fetchall()
    }
    for table in sorted(tables):
        columns = con.execute(
            "select column_name, data_type from information_schema.columns "
            "where table_schema='main' and table_name=? order by ordinal_position",
            [table],
        ).fetchall()
        if not columns:
            continue
        header = TABLE_COMMENTS.get(table, "")
        rows_note = f"~{counts.get(table, 0):,} rows" if table in counts else ""
        summary = " ".join(part for part in (header, rows_note) if part)
        if summary:
            out.append(f"-- {summary}")
        out.append(f"CREATE TABLE {table} (")
        rendered: list[str] = []
        for name, dtype in columns:
            comment = COLUMN_COMMENTS.get((table, name), "")
            if (table, name) in enums:
                values = _enum_values(con, table, name)
                if values:
                    listed = ", ".join(f"'{v}'" for v in values)
                    comment = f"{comment} One of: {listed}.".strip()
            line = f"  {name} {dtype}"
            rendered.append(f"{line},  -- {comment}" if comment else f"{line},")
        rendered[-1] = (
            rendered[-1].replace(",  --", "  --", 1)
            if "  --" in rendered[-1]
            else (rendered[-1][:-1] if rendered[-1].endswith(",") else rendered[-1])
        )
        out.extend(rendered)
        out.append(");")
        out.append("")
    return "\n".join(out).strip()


def render_fewshot(
    qids: tuple[str, ...],
    rows_by_qid: dict[str, dict[str, Any]],
    *,
    roles: dict[str, Any],
) -> str:
    """Question plus correct answer, for each fixed example.

    Two decisions worth stating, because both make the baseline stronger and
    neither is forced by §25.4:

    **The reference SQL keeps its header comments.** They name the glossary
    section each rule comes from and say why the obvious reading is wrong -- the
    difference between showing the model an answer and showing it the reasoning.
    Everything in those comments is already in the glossary the baseline is
    given in full, so this hands over no information it did not have; it hands
    over the *use* of it.

    **Each example states the role it was asked under.** The examples span three
    roles, and a scoped example shown to an unscoped role would otherwise teach a
    filter that does not apply -- worse, the out-of-scope refusal would teach a
    global analyst to refuse Dubai, which they are entitled to see. Stating the
    scope turns three role-specific examples into ten role-independent ones.

    English only. A worked example in three languages triples the prompt for no
    extra signal about SQL, and the questions are asked in all three anyway.
    """
    blocks: list[str] = []
    for qid in qids:
        row = rows_by_qid.get(qid)
        if row is None:
            raise BaselineError(f"few-shot {qid} is not in the dev set")
        question = (row.get("variants") or {}).get("en", "")
        asked_as = _asked_as(str(row.get("role", "")), roles=roles)
        refusal = FEWSHOT_REFUSALS.get(qid)
        if refusal is not None:
            answer = refusal
        else:
            path = REFERENCE_SQL / f"{qid}.sql"
            if not path.exists():
                raise BaselineError(f"few-shot {qid} has no reference SQL at {path}")
            answer = path.read_text(encoding="utf-8").strip()
        fence = "" if refusal is not None else "sql"
        blocks.append(
            f"### {qid} — asked by {asked_as}\n\nQ: {question}\n\nA:\n```{fence}\n{answer}\n```"
        )
    return "\n\n".join(blocks)


def _asked_as(role: str, *, roles: dict[str, Any]) -> str:
    """A one-line description of the scope an example was asked under."""
    spec = roles.get(role) or {}
    regions = spec.get("regions")
    countries = spec.get("countries")
    currency = spec.get("reporting_currency", "USD")
    if regions:
        where = f"regions {', '.join(regions)}"
    elif countries and countries != "ALL":
        where = f"countries {', '.join(countries)}"
    else:
        where = "every country"
    return f"a role scoped to {where}, reporting in {currency}"


def render_prompt(
    template: str,
    *,
    con: duckdb.DuckDBPyConnection,
    scope: Scope,
    allowlist: frozenset[str],
    as_of: str,
    yesterday: str,
    rows_by_qid: dict[str, dict[str, Any]],
    glossary: str,
    roles: dict[str, Any],
) -> str:
    """Fill the placeholders. Every one must be consumed (see `test_no_placeholder_survives`)."""
    filled = template
    replacements = {
        "{{AS_OF}}": as_of,
        "{{YESTERDAY}}": yesterday,
        "{{ROLE_SCOPE}}": scope.words,
        "{{DDL}}": render_ddl(con, allowlist),
        "{{GLOSSARY}}": glossary,
        "{{FEWSHOT_QIDS}}": ", ".join(FEWSHOT_QIDS),
        "{{FEWSHOT}}": render_fewshot(FEWSHOT_QIDS, rows_by_qid, roles=roles),
        "{{CURRENCY}}": scope.reporting_currency,
    }
    for token, value in replacements.items():
        filled = filled.replace(token, value)
    return filled


# --------------------------------------------------------------------------- #
# Reading what came back.
# --------------------------------------------------------------------------- #

SQL_FENCE = re.compile(r"```(?:sql)?\s*(.+?)```", re.S | re.I)


def extract_sql(text: str) -> str:
    """The SQL out of whatever the model actually sent.

    The contract asks for bare SQL. Models fence it anyway, and refusing a fenced
    query would measure markdown habits rather than SQL ability.
    """
    stripped = text.strip()
    fenced = SQL_FENCE.search(stripped)
    if fenced:
        return fenced.group(1).strip()
    return stripped


def _to_decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        # Through the string form: Decimal(0.1) is not Decimal("0.1"), and a
        # money value that arrives as a float has already lost what D1 protects.
        return Decimal(repr(value))
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None


def extract(columns: list[str], rows: list[tuple[Any, ...]]) -> Extraction:
    """The documented heuristic (§25.4).

    Contract first: columns named `key` and `value`. Otherwise, first text column
    as key and **last numeric column** as value -- last, not first, because a
    grouped query almost always projects an id or a count before the measure it
    was actually asked for. Neither available: `unparseable`, which is Wrong and
    is counted separately, because a baseline that returns something unreadable
    has not answered and should not be filed next to one that answered wrongly.
    """
    if not columns:
        return Extraction(mode="unparseable", detail="no columns")
    folded = [c.casefold() for c in columns]

    if "value" in folded:
        value_at = folded.index("value")
        key_at = folded.index("key") if "key" in folded else None
        pairs: list[tuple[str | None, Decimal]] = []
        for row in rows:
            number = _to_decimal(row[value_at])
            if number is None:
                return Extraction(
                    mode="unparseable", detail=f"non-numeric value column: {row[value_at]!r}"
                )
            key = None if key_at is None or row[key_at] is None else str(row[key_at])
            pairs.append((key, number))
        return Extraction(rows=tuple(pairs), mode="contract")

    numeric_at: int | None = None
    text_at: int | None = None
    probe = rows[0] if rows else None
    if probe is None:
        # No rows and no contract. An empty result is a legitimate answer to some
        # questions, but with no `value` column there is nothing to call the
        # answer, so this is unparseable rather than an empty contract result.
        return Extraction(mode="unparseable", detail="no rows and no value column")
    for index, cell in enumerate(probe):
        if _to_decimal(cell) is not None and not isinstance(cell, str):
            numeric_at = index
        elif text_at is None and isinstance(cell, str):
            text_at = index
    if numeric_at is None:
        return Extraction(mode="unparseable", detail=f"no numeric column in {columns}")

    pairs = []
    for row in rows:
        number = _to_decimal(row[numeric_at])
        if number is None:
            return Extraction(mode="unparseable", detail="numeric column is not numeric throughout")
        key = None if text_at is None or row[text_at] is None else str(row[text_at])
        pairs.append((key, number))
    return Extraction(
        rows=tuple(pairs),
        mode="heuristic",
        detail=f"key={columns[text_at] if text_at is not None else 'NULL'}, "
        f"value={columns[numeric_at]}",
    )


# --------------------------------------------------------------------------- #
# The system itself.
# --------------------------------------------------------------------------- #


@dataclass
class Baseline:
    """B0 as a harness `System`: `(trial, reference) -> ScorableAnswer`.

    Holds the connection and the model. One instance per run, so the prompt is
    rendered once per role rather than once per trial -- which also makes the
    recording key stable across trials that share a role.
    """

    llm: LLM
    con: duckdb.DuckDBPyConnection
    template: str
    as_of: str
    yesterday: str
    rows_by_qid: dict[str, dict[str, Any]]
    glossary: str
    roles: dict[str, Any]
    tables: frozenset[str]
    max_tokens: int = 4096
    row_limit: int = 500
    attempts: list[Attempt] = field(default_factory=list)
    _prompts: dict[str, str] = field(default_factory=dict)

    def system_prompt(self, role: str) -> str:
        if role not in self._prompts:
            scope = scope_for(role, roles=self.roles)
            self._prompts[role] = render_prompt(
                self.template,
                con=self.con,
                scope=scope,
                allowlist=allowlist_for(role, self.tables, roles=self.roles),
                as_of=self.as_of,
                yesterday=self.yesterday,
                rows_by_qid=self.rows_by_qid,
                glossary=self.glossary,
                roles=self.roles,
            )
        return self._prompts[role]

    def __call__(self, trial: Trial, reference: Any = None) -> ScorableAnswer:
        # One trial is one question, and the budget is per question (SDD §16).
        # Duck-typed: the baseline is handed whatever LLM the run configured, and
        # a plain client with no budget is a legitimate thing to be handed.
        new_question = getattr(self.llm, "new_question", None)
        if callable(new_question):
            new_question()
        allowlist = allowlist_for(trial.role, self.tables, roles=self.roles)
        scope = scope_for(trial.role, roles=self.roles)
        messages = [
            Msg(role="system", content=self.system_prompt(trial.role)),
            Msg(role="user", content=trial.text),
        ]

        first = self._ask(messages, allowlist)
        self.attempts.append(first)
        answer = self._answer(first, scope)
        if answer is not None:
            return answer

        # The one retry (§25.4), carrying back whatever went wrong -- a database
        # error or the guard's typed reason. A retry the model cannot learn from
        # is not a retry.
        complaint = (
            first.db_error or f"the query was refused by the SQL guard: {first.guard_reason}"
        )
        retry_messages = [
            *messages,
            Msg(role="assistant", content=first.text),
            Msg(
                role="user",
                content=(
                    f"That query failed:\n\n{complaint}\n\n"
                    "Write one corrected SQL statement. Same output contract: "
                    "exactly two columns named key and value."
                ),
            ),
        ]
        second = self._ask(retry_messages, allowlist)
        self.attempts.append(second)
        answer = self._answer(second, scope)
        if answer is not None:
            return answer
        reason = second.db_error or second.guard_reason or "no result"
        return ScorableAnswer(
            status="ERROR", reason=f"after retry: {reason}"[:300], text=second.text
        )

    def _ask(self, messages: list[Msg], allowlist: frozenset[str]) -> Attempt:
        result = self.llm.text(prompt_id=PROMPT_ID, messages=messages, max_tokens=self.max_tokens)
        text = result.text.strip()
        if text.startswith(CLARIFY_PREFIX) or text.startswith(CANNOT_PREFIX):
            return Attempt(text=text)

        sql = extract_sql(text)
        checked = guard(sql, "duckdb", allowlist, row_limit=self.row_limit)
        if not checked.ok:
            return Attempt(sql=sql, text=text, guard_reason=f"{checked.reason}: {checked.detail}")
        try:
            cursor = self.con.execute(checked.sql)
            columns = [d[0] for d in (cursor.description or [])]
            rows = cursor.fetchall()
        except Exception as exc:
            return Attempt(
                sql=checked.sql, text=text, db_error=f"{type(exc).__name__}: {exc}"[:400]
            )
        return Attempt(sql=checked.sql, text=text, extraction=extract(columns, rows))

    def _answer(self, attempt: Attempt, scope: Scope) -> ScorableAnswer | None:
        """A scorable answer, or None when this attempt earned the retry."""
        text = attempt.text
        if text.startswith(CLARIFY_PREFIX):
            return ScorableAnswer(
                status="CLARIFY",
                clarify=True,
                reason=text[len(CLARIFY_PREFIX) :].strip()[:300],
                text=text,
            )
        if text.startswith(CANNOT_PREFIX):
            return ScorableAnswer(
                status="ABSTAIN", reason=text[len(CANNOT_PREFIX) :].strip()[:300], text=text
            )
        extraction = attempt.extraction
        if extraction is None:
            return None
        if extraction.mode == "unparseable":
            # Wrong, not an error, and counted separately (§25.4). The model
            # answered; what it returned could not be read as an answer.
            return ScorableAnswer(
                status="UNVERIFIED",
                reason=f"unparseable: {extraction.detail}"[:300],
                sql_hash=attempt.sql[:0] or None,
                text=text,
            )
        return ScorableAnswer(
            status="UNVERIFIED",
            rows=extraction.rows,
            currency=scope.reporting_currency,
            reason=f"extraction={extraction.mode}",
            text=text,
        )


def load_template(path: Path | None = None) -> str:
    from ..llm import prompts as prompt_mod

    if path is not None:
        return path.read_text(encoding="utf-8")
    return prompt_mod.load(PROMPT_ID).text


def build(
    llm: LLM,
    con: duckdb.DuckDBPyConnection,
    *,
    set_name: str = "dev",
    as_of: str | None = None,
    max_tokens: int = 4096,
    row_limit: int = 500,
) -> Baseline:
    """Assemble B0 from the repo's own artifacts."""
    from . import questions as questions_mod

    rows = questions_mod.load(set_name)
    rows_by_qid = questions_mod.by_qid(rows)
    # `str()` rather than a round trip: PyYAML parses an unquoted ISO date into
    # a `datetime.date`, and D2 wants the injected date as text, not a date
    # object that something downstream could do arithmetic on against a clock.
    resolved_as_of = as_of or str(_settings().get("as_of"))
    tables = frozenset(
        r[0]
        for r in con.execute(
            "select table_name from information_schema.tables where table_schema='main'"
        ).fetchall()
    )
    return Baseline(
        llm=llm,
        con=con,
        template=load_template(),
        as_of=resolved_as_of,
        yesterday=_previous_day(resolved_as_of),
        rows_by_qid=rows_by_qid,
        glossary=GLOSSARY.read_text(encoding="utf-8"),
        roles=load_roles(),
        tables=tables,
        max_tokens=max_tokens,
        row_limit=row_limit,
    )


def _previous_day(iso: str) -> str:
    """Yesterday, arithmetically. D2: derived from the injected date, not a clock."""
    from datetime import date, timedelta

    year, month, day = (int(p) for p in iso.split("-"))
    return str(date(year, month, day) - timedelta(days=1))


def _settings() -> dict[str, Any]:
    import yaml

    return yaml.safe_load((REPO / "config" / "settings.yaml").read_text(encoding="utf-8")) or {}
