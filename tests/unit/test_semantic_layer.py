"""The semantic layer: it implements the glossary, and the loader fails precisely.

Two families here, and they defend different things.

**Coverage, both ways** (`test_every_glossary_term_has_metric`). The layer is an
implementation of `GLOSSARY.md` (SDD §7.1), so a glossary section with no metric
is a definition the system cannot honour, and a metric with no glossary section
is a definition somebody invented. Both are failures and the test checks both
directions, because checking one is how a layer drifts.

**Precise failures.** The layer is meant to be edited by an admin who is not
reading the code (PDD J8), so "could not load the semantic layer" is a bug in the
error message. Every malformed-input test asserts on the *content* of the
message, not just that something was raised.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from receipts.semantic import lint as lint_mod
from receipts.semantic import loader as loader_mod
from receipts.semantic.catalog import Catalog, UnknownDimension, UnknownMetric

REPO = Path(__file__).resolve().parents[2]
GLOSSARY = REPO / "docs" / "GLOSSARY.md"
SEMANTIC = REPO / "semantic"


@pytest.fixture(scope="module")
def catalog() -> Catalog:
    return loader_mod.load(SEMANTIC, with_values=False)


# --------------------------------------------------------------------------- #
# The layer implements the glossary. Both directions (SDD §7.1).
# --------------------------------------------------------------------------- #


def glossary_metric_sections() -> dict[str, str]:
    """`§2.x` headings, which are the glossary's metric definitions.

    Section 2 only. §1 is conventions, §4 is traps, §5 is vocabulary -- none of
    those is a metric, and a coverage test that counted them would demand metrics
    for "partial refunds" and "what people actually say".
    """
    text = GLOSSARY.read_text(encoding="utf-8")
    out: dict[str, str] = {}
    for match in re.finditer(r"^### (2\.\d+[a-z]?) (.+)$", text, re.M):
        number, title = match.group(1), match.group(2).strip()
        out[number] = title
    return out


def anchor_for(number: str, title: str) -> str:
    """The GitHub-style anchor a `glossary_ref` points at."""
    slug = f"{number} {title}".casefold()
    slug = re.sub(r"[^\w\s-]", "", slug).strip().replace(" ", "-")
    return f"GLOSSARY.md#{slug}"


def test_every_glossary_term_has_metric(catalog: Catalog) -> None:
    """Direction one: no §2 definition is left unimplemented."""
    sections = glossary_metric_sections()
    refs = {m.glossary_ref for m in catalog.metrics}
    missing = []
    for number, title in sorted(sections.items()):
        expected = anchor_for(number, title)
        if expected not in refs:
            missing.append(f"§{number} {title} -> expected {expected}")
    print(f"\n{len(sections)} glossary metric sections, {len(catalog.metrics)} metrics")
    for line in missing:
        print(f"  unimplemented: {line}")
    assert not missing, f"glossary definitions with no metric: {missing}"


def test_every_metric_has_a_glossary_term(catalog: Catalog) -> None:
    """Direction two: no metric was invented.

    This is the direction that catches a layer fitted to the questions rather
    than to the definitions, which is the specific failure SDD §7.1 exists to
    prevent.
    """
    sections = glossary_metric_sections()
    valid = {anchor_for(number, title) for number, title in sections.items()}
    invented = sorted(
        f"{m.name} -> {m.glossary_ref}" for m in catalog.metrics if m.glossary_ref not in valid
    )
    for line in invented:
        print(f"  no such glossary section: {line}")
    assert not invented, f"metrics pointing at no glossary section: {invented}"


def test_the_sdd_v1_metric_list_is_present(catalog: Catalog) -> None:
    """SDD §7.4 names the fifteen. Named here so a rename cannot go unnoticed."""
    required = {
        "orders_count",
        "units_sold",
        "gmv_captured",
        "refunded_amount",
        "net_revenue",
        "avg_order_value",
        "refund_rate",
        "payment_success_rate_order",
        "payment_success_rate_attempt",
        "failure_rate_by_reason",
        "emi_share",
        "accessory_attach_rate",
        "settlement_lag_days",
        "unsettled_amount",
        "duplicate_capture_count",
    }
    missing = sorted(required - set(catalog.metric_names))
    assert not missing, f"SDD §7.4 names these and the layer has none: {missing}"


def test_the_real_layer_lints_clean(catalog: Catalog) -> None:
    findings = lint_mod.lint(catalog)
    for finding in findings[:10]:
        print(f"  {finding}")
    assert not findings, f"{len(findings)} lint finding(s) on the real layer"


def test_every_lint_rule_runs(catalog: Catalog) -> None:
    """Reachability: a rule that is never called proves nothing.

    Each rule is invoked by name and must return a list. A rule dropped from
    `RULES` while its function survives would otherwise look like a passing rule.
    """
    assert len(lint_mod.RULES) >= 8, "a lint rule has been dropped from RULES"
    for rule in lint_mod.RULES:
        assert isinstance(rule(catalog), list), f"{rule.__name__} did not return findings"
    print(f"\n{len(lint_mod.RULES)} rules, all reachable")


# --------------------------------------------------------------------------- #
# The loader fails precisely (M7 TEST 1).
# --------------------------------------------------------------------------- #


@pytest.fixture
def layer(tmp_path: Path) -> Path:
    """A copy of the real layer, editable."""
    import shutil

    target = tmp_path / "semantic"
    shutil.copytree(SEMANTIC, target)
    return target


def test_malformed_yaml_names_the_file(layer: Path) -> None:
    (layer / "dimensions.yaml").write_text("dimensions: [ unclosed\n", encoding="utf-8")
    with pytest.raises(loader_mod.LoaderError) as caught:
        loader_mod.load(layer, with_values=False)
    message = str(caught.value)
    print(f"\n{message}")
    assert "dimensions.yaml" in message and "not valid YAML" in message


def test_an_unknown_entity_on_a_dimension_is_named_with_the_known_ones(layer: Path) -> None:
    data = yaml.safe_load((layer / "dimensions.yaml").read_text(encoding="utf-8"))
    data["dimensions"][0]["entity"] = "storerooms"
    (layer / "dimensions.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(loader_mod.LoaderError) as caught:
        loader_mod.load(layer, with_values=False)
    message = str(caught.value)
    print(f"\n{message[:160]}")
    assert "storerooms" in message and "entities.yaml" in message
    assert "showrooms" in message, "the message does not say what the valid entities are"


def test_an_unparseable_where_clause_fails_the_load_not_the_query(layer: Path) -> None:
    """A broken predicate found at query time is a wrong number given to somebody."""
    path = layer / "metrics" / "gmv_captured.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["aggregate"]["where"] = "status = = 'captured'"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(loader_mod.LoaderError) as caught:
        loader_mod.load(layer, with_values=False)
    message = str(caught.value)
    print(f"\n{message[:160]}")
    assert "gmv_captured.yaml" in message and "does not parse" in message


def test_an_unresolved_named_predicate_is_refused(layer: Path) -> None:
    path = layer / "metrics" / "gmv_captured.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["aggregate"]["where"] = "payment_attempts.status = 'captured' AND IS_FIRST_CAPTURE"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    entities = yaml.safe_load((layer / "entities.yaml").read_text(encoding="utf-8"))
    del entities["named_predicates"]["IS_FIRST_CAPTURE"]
    (layer / "entities.yaml").write_text(yaml.safe_dump(entities), encoding="utf-8")
    with pytest.raises(loader_mod.LoaderError) as caught:
        loader_mod.load(layer, with_values=False)
    assert "IS_FIRST_CAPTURE" in str(caught.value)


def test_a_customers_column_exposed_as_a_dimension_is_refused(layer: Path) -> None:
    """SDD §5.2: never in the semantic layer, for anyone, at any depth."""
    data = yaml.safe_load((layer / "dimensions.yaml").read_text(encoding="utf-8"))
    data["dimensions"].append(
        {
            "name": "customer_phone",
            "entity": "orders",
            "expr": "customers.phone_masked",
            "join_via": ["customers.customer_id = orders.customer_id"],
            "type": "string",
            "label": {"en": "Phone", "ta": "தொலைபேசி", "hi": "फ़ोन"},
            "synonyms": {},
        }
    )
    (layer / "dimensions.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(loader_mod.LoaderError) as caught:
        loader_mod.load(layer, with_values=False)
    message = str(caught.value)
    print(f"\n{message[:140]}")
    assert "customers" in message


def test_a_customers_entity_cannot_be_declared_at_all(layer: Path) -> None:
    """Guard off for the dimension check: the entity itself is refused too."""
    data = yaml.safe_load((layer / "entities.yaml").read_text(encoding="utf-8"))
    data["entities"].append(
        {"name": "customers", "sources": ["postgres"], "primary_key": "customer_id"}
    )
    (layer / "entities.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(loader_mod.LoaderError) as caught:
        loader_mod.load(layer, with_values=False)
    assert "customers" in str(caught.value)


def test_a_metric_whose_name_disagrees_with_its_file_is_refused(layer: Path) -> None:
    path = layer / "metrics" / "orders_count.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["name"] = "order_count"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(loader_mod.LoaderError) as caught:
        loader_mod.load(layer, with_values=False)
    assert "order_count" in str(caught.value)


# --------------------------------------------------------------------------- #
# Each lint rule has a failing fixture (M7 TEST 2).
# --------------------------------------------------------------------------- #


def load_layer(path: Path) -> Catalog:
    return loader_mod.load(path, with_values=False)


def edit_metric(layer: Path, name: str, **changes: object) -> None:
    path = layer / "metrics" / f"{name}.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data.update(changes)
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")


def test_lint_catches_a_missing_owner(layer: Path) -> None:
    edit_metric(layer, "orders_count", owner="")
    findings = lint_mod.lint(load_layer(layer))
    assert any(f.rule == "completeness" and "owner" in f.detail for f in findings)


def test_lint_catches_a_missing_dev_question(layer: Path) -> None:
    edit_metric(layer, "orders_count", dev_questions=[])
    findings = lint_mod.lint(load_layer(layer))
    assert any(f.rule == "dev_question" for f in findings)


def test_lint_catches_a_missing_label(layer: Path) -> None:
    edit_metric(layer, "orders_count", label={"en": "Orders count"})
    findings = lint_mod.lint(load_layer(layer))
    assert any(f.rule == "completeness" and "label" in f.detail for f in findings)


def test_lint_catches_an_unknown_dimension_and_suggests_one(layer: Path) -> None:
    edit_metric(layer, "orders_count", allowed_dimensions=["showrooms"])
    findings = lint_mod.lint(load_layer(layer))
    match = [f for f in findings if f.rule == "dimension_exists"]
    assert match, "an unknown dimension passed the lint"
    print(f"\n{match[0]}")
    assert "showroom" in match[0].detail, "no suggestion offered for an obvious typo"


def test_lint_catches_a_dimension_that_cannot_be_joined(layer: Path) -> None:
    """`fx_rates` is reference data, so it must NOT be the fixture here.

    Reference entities are reachable from everywhere by construction. The fixture
    has to be a dimension on a *scoped* entity with no path, which is what an
    admin would actually create by mistake.
    """
    data = yaml.safe_load((layer / "dimensions.yaml").read_text(encoding="utf-8"))
    data["dimensions"].append(
        {
            "name": "orphan",
            "entity": "settlements",
            "expr": "settlements.acquiring_bank",
            "join_via": [],
            "type": "string",
            "label": {"en": "Orphan", "ta": "அனாதை", "hi": "अनाथ"},
            "synonyms": {},
        }
    )
    (layer / "dimensions.yaml").write_text(
        yaml.safe_dump(data, allow_unicode=True), encoding="utf-8"
    )
    entities = yaml.safe_load((layer / "entities.yaml").read_text(encoding="utf-8"))
    for entity in entities["entities"]:
        if entity["name"] in ("settlements", "settlement_items"):
            entity["scope_path"] = []
    (layer / "entities.yaml").write_text(
        yaml.safe_dump(entities, allow_unicode=True), encoding="utf-8"
    )
    edit_metric(layer, "orders_count", allowed_dimensions=["orphan"])
    findings = lint_mod.lint(load_layer(layer))
    assert any(f.rule == "dimension_joinable" for f in findings), [str(f) for f in findings[:5]]


def test_lint_catches_an_ungated_metric_offering_a_finance_dimension(layer: Path) -> None:
    """Joinability is not permission.

    `settlements` IS joinable from `orders`, through the attempts it settles, so
    the reachability rule allows this. Only the capability rule refuses it, which
    is the whole reason that rule exists.
    """
    data = yaml.safe_load((layer / "dimensions.yaml").read_text(encoding="utf-8"))
    data["dimensions"].append(
        {
            "name": "payout_bank",
            "entity": "settlements",
            "expr": "settlements.acquiring_bank",
            "join_via": [],
            "type": "string",
            "label": {"en": "Payout bank", "ta": "வங்கி", "hi": "बैंक"},
            "synonyms": {},
        }
    )
    (layer / "dimensions.yaml").write_text(
        yaml.safe_dump(data, allow_unicode=True), encoding="utf-8"
    )
    edit_metric(
        layer,
        "orders_count",
        allowed_dimensions=["country", "payout_bank"],
        required_capability=None,
    )
    catalog = load_layer(layer)
    joinable = lint_mod.rule_dimensions_exist_and_join(catalog)
    capability = lint_mod.rule_dimension_capability_matches(catalog)
    print(f"\njoinable findings: {len(joinable)}; capability findings: {len(capability)}")
    assert not any(f.rule == "dimension_joinable" for f in joinable), (
        "reachability refused it, so this fixture does not prove the capability rule"
    )
    assert capability, "an ungated metric offered a finance dimension and nothing objected"


def test_lint_catches_two_metrics_claiming_one_phrase(layer: Path) -> None:
    edit_metric(layer, "orders_count", default_for={"en": ["captured gmv"]})
    findings = lint_mod.lint(load_layer(layer))
    match = [f for f in findings if f.rule == "phrase_collision"]
    assert match, "two metrics claimed the same phrase and nothing objected"
    print(f"\n{match[0]}")


def test_lint_catches_a_money_metric_with_no_currency_column(layer: Path) -> None:
    edit_metric(layer, "gmv_captured", currency_column=None)
    findings = lint_mod.lint(load_layer(layer))
    assert any(f.rule == "money" for f in findings)


def test_lint_catches_a_ratio_with_only_one_side(layer: Path) -> None:
    path = layer / "metrics" / "refund_rate.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    del data["denominator"]
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    findings = lint_mod.lint(load_layer(layer))
    assert any(f.rule == "shape" for f in findings)


def test_lint_catches_a_dangling_sibling(layer: Path) -> None:
    edit_metric(layer, "orders_count", siblings=["gmv_capturd"])
    findings = lint_mod.lint(load_layer(layer))
    assert any(f.rule == "siblings" for f in findings)


# --------------------------------------------------------------------------- #
# catalog_version (M7 TEST 3).
# --------------------------------------------------------------------------- #


def test_catalog_version_is_stable_across_two_loads() -> None:
    first = loader_mod.load(SEMANTIC, with_values=False).catalog_version
    second = loader_mod.load(SEMANTIC, with_values=False).catalog_version
    print(f"\ncatalog_version {first[:16]}")
    assert first == second


def test_catalog_version_changes_when_one_label_changes(layer: Path) -> None:
    """A label is what the asker reads.

    A layer that answers the same question with different words is not the same
    layer, and a receipt naming its catalog version has to say so.
    """
    before = load_layer(layer).catalog_version
    edit_metric(
        layer,
        "orders_count",
        label={"en": "Order count", "ta": "ஆர்டர்கள் எண்ணிக்கை", "hi": "ऑर्डर की संख्या"},
    )
    after = load_layer(layer).catalog_version
    print(f"\n{before[:16]} -> {after[:16]}")
    assert before != after, "one label changed and catalog_version did not"


def test_catalog_version_ignores_the_dimension_value_index() -> None:
    """A new city opening is not a change to the definitions.

    The index is derived from the data artifact. Folding it into the version would
    make every receipt's catalog version a statement about the rows, when it is
    meant to be a statement about the definitions.
    """
    from receipts.semantic.catalog import Catalog as C

    base = loader_mod.load(SEMANTIC, with_values=False)
    with_values = C(
        entities=base.entities,
        dimensions=base.dimensions,
        metrics=base.metrics,
        calendar=base.calendar,
        named_predicates=base.named_predicates,
        dimension_values={"city": ("Chennai", "Madurai")},
    )
    assert base.catalog_version == with_values.catalog_version


# --------------------------------------------------------------------------- #
# Lookups, capability gating, and the planner slice.
# --------------------------------------------------------------------------- #


def test_unknown_lookups_raise_and_say_what_exists(catalog: Catalog) -> None:
    with pytest.raises(UnknownMetric) as caught:
        catalog.metric("gmv")
    assert "gmv_captured" in str(caught.value), "the error does not list the real names"
    with pytest.raises(UnknownDimension):
        catalog.dimension("nope")


def test_a_role_without_finance_cannot_see_the_settlement_metrics(catalog: Catalog) -> None:
    """Unrepresentable, not refused (SDD §11.3).

    The planner's enum is built from this list. A metric that is visible and then
    rejected tells the asker that settlement data exists and they may not see it.
    """
    ungated = {m.name for m in catalog.visible_metrics(())}
    gated = {m.name for m in catalog.visible_metrics(("finance",))}
    assert "settlement_lag_days" not in ungated
    assert "unsettled_amount" not in ungated
    assert {"settlement_lag_days", "unsettled_amount"} <= gated
    print(f"\nwithout finance: {len(ungated)} metrics; with: {len(gated)}")


def test_the_planner_slice_offers_only_reachable_names(catalog: Catalog) -> None:
    """What M9's schema-from-slice enum is built out of."""
    slice_ = catalog.slice_for(())
    assert "unsettled_amount" not in slice_["metrics"]
    assert set(slice_["dimensions"]) <= set(catalog.dimension_names)
    print(f"\nslice: {len(slice_['metrics'])} metrics, {len(slice_['dimensions'])} dimensions")


def test_every_dimension_carries_a_code_mixed_synonym(catalog: Catalog) -> None:
    """M2_NOTES: Tamil and Hindi synonyms must carry the code-mixed form.

    People writing Tamil in a business context say "showroom" and "bank" in
    English inside a Tamil sentence far more often than the dictionary word. A
    synonym list holding only the formal form matches the questions nobody asks.
    """
    latin = re.compile(r"[A-Za-z]")
    missing = []
    for dimension in catalog.dimensions:
        for language in ("ta", "hi"):
            forms = dimension.synonyms.get(language, ())
            if not forms:
                missing.append(f"{dimension.name}/{language}: no synonyms at all")
            elif not any(latin.search(form) for form in forms):
                missing.append(f"{dimension.name}/{language}: only the formal form {forms}")
    for line in missing:
        print(f"  {line}")
    assert not missing, f"dimensions with no code-mixed synonym: {len(missing)}"
