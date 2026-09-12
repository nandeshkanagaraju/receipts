"""receipts.agent.retrieve — [P] pure: which metrics this question might mean.

BM25 over the catalogue, no embeddings (ADR-004). Deterministic, offline,
assertable in a test — which is what a component whose whole job is to be boring
should be.

Three decisions worth stating.

**Ties break by name, always.** BM25 scores collide constantly on a catalogue
this small: two metrics matching one query word score identically, and Python's
sort is stable, so the winner would be whichever metric the loader read first —
which is alphabetical by filename today and something else the moment a file is
renamed. A retrieval that changes when a file is renamed is not deterministic
(D4), so the sort key is `(-score, name)` and the name is doing real work.

**Siblings are always added, after the cut.** `payment_success_rate_order` and
`payment_success_rate_attempt` are the pair the whole glossary warns about
(§2.9): if the question retrieves one, the model must be able to see the other,
because the choice between them *is* the question. Added after the top-k cut, so
a sibling never displaces a directly-matched metric.

**The document is the metric's identity, not its documentation.** Name, labels in
three languages, and `default_for` phrases. Not the definition: it is a
paragraph, it repeats the same twenty business words in every metric, and letting
it into the index means the longest definition wins every vague query. What is
indexed is what a person might *say*, which is exactly what `default_for` is.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field

from ..semantic.catalog import Catalog, Dimension, Metric

# Okapi BM25. Standard values; k1 controls saturation, b length normalisation.
K1 = 1.5
B = 0.75

DEFAULT_K = 8

# Unicode-aware, and the Indic ranges are named explicitly because `\w` is not
# enough. Tamil vowel signs and the virama are combining marks (categories Mc and
# Mn), which Python's `\w` excludes, so `[^\W\d_]+` split "நேற்று" into
# ['ந', 'ற', 'ற'] -- three fragments where there is one word. Retrieval still
# scored, on syllable debris, which is why the hit rate looked fine and the
# tokeniser was wrong anyway. The same applies to Devanagari's matras.
TOKEN = re.compile(r"(?:[^\W\d_]|[\u0900-\u097F\u0B80-\u0BFF])+", re.UNICODE)

# Words carried by nearly every business question. They are not stopwords in
# English generally -- "rate" and "total" mean something -- but here they appear
# in so many metric documents that they separate nothing, and BM25's IDF already
# discounts them. Listed so the behaviour is visible rather than emergent.
LOW_SIGNAL = frozenset({"the", "a", "an", "of", "in", "our", "we", "us", "by", "for", "and"})


def tokenize(text: str) -> list[str]:
    """Case-folded word tokens, low-signal words dropped, order preserved."""
    return [
        token
        for token in (m.group(0).casefold() for m in TOKEN.finditer(text))
        if token not in LOW_SIGNAL
    ]


@dataclass(frozen=True, slots=True)
class Scored:
    name: str
    score: float
    matched: tuple[str, ...]
    reason: str = "bm25"


@dataclass(frozen=True)
class CatalogSlice:
    """What the planner is allowed to choose from, and why it was offered.

    `metrics` is the enum the planner's schema is generated from, so this object
    is the boundary of what the model can express. A metric absent here is not
    rejected later — it is unrepresentable.
    """

    metrics: tuple[Metric, ...]
    dimensions: tuple[Dimension, ...]
    scored: tuple[Scored, ...] = field(default_factory=tuple)
    query_tokens: tuple[str, ...] = field(default_factory=tuple)

    @property
    def metric_names(self) -> tuple[str, ...]:
        return tuple(m.name for m in self.metrics)

    @property
    def dimension_names(self) -> tuple[str, ...]:
        return tuple(d.name for d in self.dimensions)

    def dimensions_for(self, metric_name: str) -> tuple[str, ...]:
        for metric in self.metrics:
            if metric.name == metric_name:
                return metric.allowed_dimensions
        return ()


def metric_document(metric: Metric) -> list[str]:
    """The tokens a metric is findable by: what a person might say for it."""
    parts: list[str] = [metric.name.replace("_", " ")]
    parts.extend(str(label) for label in metric.label.values())
    for phrases in metric.default_for.values():
        parts.extend(phrases)
    tokens: list[str] = []
    for part in parts:
        tokens.extend(tokenize(part))
    return tokens


def dimension_document(dimension: Dimension) -> list[str]:
    parts: list[str] = [dimension.name.replace("_", " ")]
    parts.extend(str(label) for label in dimension.label.values())
    for synonyms in dimension.synonyms.values():
        parts.extend(synonyms)
    tokens: list[str] = []
    for part in parts:
        tokens.extend(tokenize(part))
    return tokens


@dataclass(frozen=True)
class Bm25Index:
    """Built once per catalogue. Pure data: no clock, no file, no model."""

    names: tuple[str, ...]
    documents: tuple[tuple[str, ...], ...]
    lengths: tuple[int, ...]
    average_length: float
    document_frequency: dict[str, int]
    total: int

    @classmethod
    def build(cls, documents: dict[str, list[str]]) -> Bm25Index:
        names = tuple(sorted(documents))
        docs = tuple(tuple(documents[name]) for name in names)
        lengths = tuple(len(d) for d in docs)
        frequency: Counter[str] = Counter()
        for doc in docs:
            frequency.update(set(doc))
        total = len(docs)
        average = sum(lengths) / total if total else 0.0
        return cls(names, docs, lengths, average, dict(frequency), total)

    def score(self, query: list[str]) -> dict[str, tuple[float, tuple[str, ...]]]:
        out: dict[str, tuple[float, tuple[str, ...]]] = {}
        for index, name in enumerate(self.names):
            doc = self.documents[index]
            counts = Counter(doc)
            length = self.lengths[index] or 1
            score = 0.0
            matched: list[str] = []
            for term in dict.fromkeys(query):
                frequency = counts.get(term, 0)
                if not frequency:
                    continue
                matched.append(term)
                df = self.document_frequency.get(term, 0)
                idf = math.log(1 + (self.total - df + 0.5) / (df + 0.5))
                denominator = frequency + K1 * (1 - B + B * length / (self.average_length or 1))
                score += idf * (frequency * (K1 + 1)) / denominator
            out[name] = (score, tuple(matched))
        return out


def build_index(catalog: Catalog, capabilities: tuple[str, ...] = ()) -> Bm25Index:
    """One index over the metrics this role can see.

    Capability-gated metrics are absent from the index, not filtered from its
    results. A role without `finance` must never have `unsettled_amount` scored,
    offered, or mentioned in a trace: the planner's enum comes from here, and
    "unrepresentable" has to start at the index (SDD §11.3).
    """
    visible = catalog.visible_metrics(capabilities)
    return Bm25Index.build({metric.name: metric_document(metric) for metric in visible})


def retrieve(
    question: str,
    catalog: Catalog,
    k: int = DEFAULT_K,
    *,
    capabilities: tuple[str, ...] = (),
    previous_metric: str | None = None,
) -> CatalogSlice:
    """Top-k metrics for a question, plus siblings, plus the follow-up's metric.

    `previous_metric` is how a follow-up works (SDD §17): "now split by city"
    contains nothing that retrieves the metric it is about, so the previous
    plan's metric is added explicitly rather than hoped for.
    """
    visible = {metric.name: metric for metric in catalog.visible_metrics(capabilities)}
    index = build_index(catalog, capabilities)
    tokens = tokenize(question)
    scores = index.score(tokens)

    # (-score, name): the name is the tie-break and it is doing real work. Scores
    # collide constantly on a catalogue of sixteen.
    ordered = sorted(scores.items(), key=lambda item: (-item[1][0], item[0]))
    chosen: list[Scored] = [
        Scored(name=name, score=round(score, 6), matched=matched)
        for name, (score, matched) in ordered[:k]
        if score > 0
    ]
    picked = {s.name for s in chosen}

    # The follow-up's metric first, then siblings: both are additions *after* the
    # cut, so neither can displace something the question actually matched.
    if previous_metric and previous_metric in visible and previous_metric not in picked:
        chosen.append(Scored(name=previous_metric, score=0.0, matched=(), reason="follow-up"))
        picked.add(previous_metric)

    # `sorted(picked)`, never `picked`. Iterating a set of strings orders by
    # hash, and Python randomises string hashing per process, so the siblings
    # were appended in a different order in every run. That changed the order
    # metrics are listed in the planner prompt, which changed the system
    # message, which changed the recording key (SDD §16) -- so a planner call
    # recorded in one process could not be replayed in the next. The recordings
    # were all on disk and all unfindable, and the symptom was a replay that
    # worked for some questions and not others depending on which way the hash
    # fell. D4 says explicit sort keys; this is why.
    for name in sorted(picked):
        for sibling in visible[name].siblings if name in visible else ():
            if sibling in visible and sibling not in picked:
                chosen.append(
                    Scored(name=sibling, score=0.0, matched=(), reason=f"sibling of {name}")
                )
                picked.add(sibling)

    metrics = tuple(visible[s.name] for s in chosen)
    allowed = {d for metric in metrics for d in metric.allowed_dimensions}
    dimensions = tuple(d for d in catalog.dimensions if d.name in allowed)
    return CatalogSlice(
        metrics=metrics,
        dimensions=dimensions,
        scored=tuple(chosen),
        query_tokens=tuple(tokens),
    )
