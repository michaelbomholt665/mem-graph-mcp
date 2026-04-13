"""Shared data models for stochastic agent evals."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

EvalMode = Literal["fixture", "live"]
ScorerName = Literal["exact", "keywords", "regex", "semantic"]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class EvalCase(BaseModel):
    """One stochastic eval case for an agent workflow."""

    case_id: str = Field(description="Stable case identifier.")
    description: str = Field(description="Why the case exists and what it measures.")
    prompt: str = Field(description="Prompt text passed to the eval runner.")
    expected_output: str = Field(
        default="",
        description="Expected normalized output used by exact and semantic scorers.",
    )
    expected_keywords: list[str] = Field(
        default_factory=list,
        description="Keywords that should appear in the normalized output.",
    )
    expected_pattern: str | None = Field(
        default=None,
        description="Regex pattern the normalized output should match.",
    )
    scorer: ScorerName | None = Field(
        default=None,
        description="Optional per-case scorer override.",
    )
    tags: list[str] = Field(default_factory=list)
    runs: int = Field(default=3, ge=1, le=10)
    passing_score: float = Field(default=0.7, ge=0.0, le=1.0)
    metadata: dict[str, str] = Field(default_factory=dict)


class EvalFailureDetail(BaseModel):
    """Condensed information about a failing eval run."""

    run_index: int = Field(ge=1)
    reason: str
    score: float = Field(ge=0.0, le=1.0)
    output_excerpt: str = Field(default="")
    error: str | None = Field(default=None)


class EvalRunResult(BaseModel):
    """Result of a single stochastic run for an eval case."""

    run_index: int = Field(ge=1)
    score: float = Field(ge=0.0, le=1.0)
    passed: bool
    duration_ms: float = Field(ge=0.0)
    output: str = Field(default="")
    error: str | None = Field(default=None)
    started_at: datetime = Field(default_factory=_utc_now)
    completed_at: datetime = Field(default_factory=_utc_now)


class EvalCaseResult(BaseModel):
    """Aggregated outcome for a case after multiple runs."""

    case_id: str
    description: str
    scorer: ScorerName
    run_count: int = Field(ge=0)
    pass_count: int = Field(ge=0)
    pass_rate: float = Field(ge=0.0, le=1.0)
    average_score: float = Field(ge=0.0, le=1.0)
    average_duration_ms: float = Field(ge=0.0)
    passed: bool
    runs: list[EvalRunResult] = Field(default_factory=list)
    failure_details: list[EvalFailureDetail] = Field(default_factory=list)


class EvalSuite(BaseModel):
    """A maintained suite of eval cases for one agent family."""

    suite_name: str
    agent_name: str
    description: str
    cases: list[EvalCase] = Field(default_factory=list)
    default_scorer: ScorerName = Field(default="semantic")
    pass_threshold: float = Field(default=0.67, ge=0.0, le=1.0)
    default_runs: int = Field(default=3, ge=1, le=10)


class EvalSuiteResult(BaseModel):
    """Aggregated result for one suite."""

    suite_name: str
    agent_name: str
    case_count: int = Field(ge=0)
    passed_case_count: int = Field(ge=0)
    case_pass_rate: float = Field(ge=0.0, le=1.0)
    run_count: int = Field(ge=0)
    passed: bool
    total_duration_ms: float = Field(ge=0.0)
    started_at: datetime = Field(default_factory=_utc_now)
    completed_at: datetime = Field(default_factory=_utc_now)
    case_results: list[EvalCaseResult] = Field(default_factory=list)


class EvalReport(BaseModel):
    """Top-level eval run report across one or more suites."""

    mode: EvalMode
    total_suites: int = Field(ge=0)
    passed_suites: int = Field(ge=0)
    suite_pass_rate: float = Field(ge=0.0, le=1.0)
    total_duration_ms: float = Field(ge=0.0)
    started_at: datetime = Field(default_factory=_utc_now)
    completed_at: datetime = Field(default_factory=_utc_now)
    suite_results: list[EvalSuiteResult] = Field(default_factory=list)


EvalRunner = Callable[[EvalCase], Awaitable[str]]


@dataclass(slots=True)
class SuiteBinding:
    """Pair a suite with the runner that executes its cases."""

    suite: EvalSuite
    runner: EvalRunner