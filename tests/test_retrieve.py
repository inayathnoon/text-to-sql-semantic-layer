from __future__ import annotations

import pytest

from semantic_layer.retrieve import ResolutionError, resolve


def test_resolves_canonical_metric_name(registry):
    assert resolve("what is revenue", registry).metric == "revenue"


def test_resolves_via_synonym(registry):
    assert resolve("what was the average order value", registry).metric == "aov"
    assert resolve("show me basket size", registry).metric == "aov"
    assert resolve("gross margin rate", registry).metric == "margin_rate"


def test_group_by_detected(registry):
    spec = resolve("revenue by region", registry)
    assert spec.metric == "revenue"
    assert "region" in spec.group_by


def test_filter_on_region_detected(registry):
    spec = resolve("revenue in apac", registry)
    assert spec.filters.get("region") == "APAC"


def test_filter_on_category_detected(registry):
    spec = resolve("units sold for electronics", registry)
    assert spec.filters.get("category") == "electronics"


def test_time_window_detected(registry):
    spec = resolve("revenue last 90 days", registry)
    assert spec.window_days == 90


def test_no_time_window_when_not_mentioned(registry):
    spec = resolve("revenue by region", registry)
    assert spec.window_days is None


def test_unresolvable_question_refuses(registry):
    with pytest.raises(ResolutionError):
        resolve("what is the weather today", registry)


def test_resolve_never_guesses_silently_on_nonsense(registry):
    # A nonsense string shares no tokens with any synonym list - the
    # correct behaviour is a refusal, not an arbitrary first metric.
    with pytest.raises(ResolutionError):
        resolve("zzzz qqqq", registry)
