"""Resolves a free-text question to a metric + dimension + filters, by
synonym matching against the registry.

This is deliberately not an LLM call: it is the retrieval step the
production semantic layer feeds an LLM (or a human) for grounding - the
glossary that stops "revenue" meaning something different in two people's
heads. A keyword/synonym matcher is honest about what it can do and has no
hallucination surface to reason about; swapping in an embedding or an LLM
re-ranker over the same registry is additive, not a rewrite.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from semantic_layer.registry import Registry

_WORD = re.compile(r"[a-z0-9]+")

_REGION_TOKENS = {"emea", "apac", "amer"}
_CATEGORY_TOKENS = {"electronics", "home", "apparel", "grocery", "beauty"}

_TIME_WINDOWS = {
    "this month": 30,
    "last month": 60,
    "this quarter": 90,
    "last 30 days": 30,
    "last 90 days": 90,
    "year to date": 365,
    "ytd": 365,
}


class ResolutionError(Exception):
    """Raised when a question cannot be resolved with confidence. A refusal
    is correct behaviour here, not a bug: answering with the wrong metric is
    worse than answering with nothing."""


@dataclass(frozen=True)
class QuerySpec:
    metric: str
    group_by: list[str] = field(default_factory=list)
    filters: dict[str, str] = field(default_factory=dict)
    window_days: int | None = None


def _tokenize(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


def _best_synonym_match(
    tokens: set[str], candidates: dict[str, list[str]]
) -> tuple[str, int] | None:
    """Scores each candidate by the number of its synonym-phrase words found
    in the question. Ties are refused rather than guessed at."""
    scores: dict[str, int] = {}
    for name, synonyms in candidates.items():
        phrases = [name.replace("_", " "), *synonyms]
        best_for_name = 0
        for phrase in phrases:
            phrase_tokens = _tokenize(phrase)
            if phrase_tokens and phrase_tokens.issubset(tokens):
                best_for_name = max(best_for_name, len(phrase_tokens))
        if best_for_name:
            scores[name] = best_for_name

    if not scores:
        return None
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    top_score = ranked[0][1]
    tied = [name for name, score in ranked if score == top_score]
    if len(tied) > 1:
        raise ResolutionError(
            f"ambiguous: {tied} all match equally well - ask a more specific question"
        )
    return ranked[0]


def resolve(question: str, registry: Registry) -> QuerySpec:
    tokens = _tokenize(question)

    metric_candidates = {name: m.synonyms for name, m in registry.metrics.items()}
    metric_match = _best_synonym_match(tokens, metric_candidates)
    if metric_match is None:
        raise ResolutionError(
            f"no metric in the registry matches this question: {question!r}. "
            f"Known metrics: {sorted(registry.metrics)}"
        )
    metric_name, _ = metric_match

    group_by: list[str] = []
    for dim_name, dim in registry.dimensions.items():
        if dim.temporal:
            continue
        phrases = [dim_name.replace("_", " "), *dim.synonyms]
        if any(_tokenize(p).issubset(tokens) for p in phrases if _tokenize(p)):
            if re.search(rf"\bby {re.escape(dim_name)}\b", question.lower()) or (
                f"by {dim_name}" in question.lower()
            ):
                group_by.append(dim_name)
            elif any(f"by {s}" in question.lower() for s in dim.synonyms):
                group_by.append(dim_name)

    filters: dict[str, str] = {}
    lowered = question.lower()
    for region in _REGION_TOKENS:
        if region in lowered.split() or f" {region} " in f" {lowered} ":
            filters["region"] = region.upper()
    for category in _CATEGORY_TOKENS:
        if category in lowered:
            filters["category"] = category

    window_days = None
    for phrase, days in _TIME_WINDOWS.items():
        if phrase in lowered:
            window_days = days
            break

    return QuerySpec(
        metric=metric_name, group_by=group_by, filters=filters, window_days=window_days
    )
