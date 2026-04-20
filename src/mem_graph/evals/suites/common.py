"""Shared helpers for hosted text-based eval suites."""

from __future__ import annotations

from dataclasses import dataclass

from ...models.evals import EvalCase, ScorerName


@dataclass
class HostedTextOutput:
    text: str


@dataclass
class HostedTextMeta:
    case_id: str
    description: str
    scorer: ScorerName
    expected_keywords: list[str]
    expected_pattern: str | None
    tags: list[str]
    source: str = "synthetic"


def build_text_meta(case: EvalCase, default_scorer: ScorerName) -> HostedTextMeta:
    scorer = case.scorer or default_scorer
    return HostedTextMeta(
        case_id=case.case_id,
        description=case.description,
        scorer=scorer,
        expected_keywords=list(case.expected_keywords),
        expected_pattern=case.expected_pattern,
        tags=list(case.tags),
    )


def expected_text(case: EvalCase) -> str:
    return (
        case.expected_output
        or " ".join(case.expected_keywords)
        or (case.expected_pattern or "")
    )


__all__ = [
    "HostedTextMeta",
    "HostedTextOutput",
    "build_text_meta",
    "expected_text",
]
