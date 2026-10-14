# 1. Retrieval refuses a tie rather than picking a default

**Status:** accepted · **Date:** 2026-10-14

## Context

Synonym matching scores every metric against a question's tokens. Two metrics can score
identically - "revenue" vs "sales" might both partially match a loosely-worded question
that mentions neither phrase cleanly. Something has to happen when two candidates are
equally good.

## Options

**Pick the first match alphabetically, or by insertion order in the YAML.** Always
returns an answer. But the choice is arbitrary and looks identical to a correct
resolution - nothing in the output signals that the match was a coin flip. Someone
building a dashboard on top of this gets a number that is right half the time by luck.

**Pick the metric with more total registry usage, or most recently queried.** Still
arbitrary, just arbitrary with a popularity bias instead of an alphabetical one. Same
failure mode: wrong answers that look identical to right ones.

**Raise and refuse.** Chosen. `resolve()` raises `ResolutionError` listing the tied
candidates when the top score has more than one holder. The caller - a human reading an
error, or an LLM re-ranker sitting in front of this layer in a fuller build - gets a
signal to ask a more specific question instead of a number to trust by accident.

## Consequence

A genuinely ambiguous question now returns nothing instead of something wrong. That is
worse user experience in isolation and better in aggregate: every number this layer does
return has exactly one registry entry behind it, with no silent default to audit for.
The same principle governs `compile.py`'s unknown-join and blocked-column refusals - the
set of things this layer won't do is explicit and readable, not an emergent property of
whatever path happened not to throw.
