"""Shared data models for stochastic agent evals."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from .agent_outputs import JSONValue

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
    tags: list[str] = Field(
        default_factory=list,
        description="Free-form tags used to group, filter, or analyze related eval cases.",
    )
    runs: int = Field(
        default=3,
        ge=1,
        le=10,
        description="How many stochastic repetitions to execute for this case before aggregating the result.",
    )
    passing_score: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Minimum per-run score required for a single run to count as passing.",
    )
    timeout_s: float | None = Field(
        default=None,
        ge=0.01,
        le=600.0,
        description="Optional per-case timeout override in seconds. Falls back to the evaluator default when omitted.",
    )
    metadata: dict[str, JSONValue] = Field(
        default_factory=dict,
        description="JSON-safe case metadata used by suite-specific runners and hosted dataset builders.",
    )


class EvalFailureDetail(BaseModel):
    """Condensed information about a failing eval run."""

    run_index: int = Field(
        ge=1,
        description="1-indexed run number that produced this failure detail.",
    )
    reason: str = Field(
        description="Short explanation of why the run failed, such as a timeout, exception, or low score.",
    )
    score: float = Field(
        ge=0.0,
        le=1.0,
        description="Score assigned to the failing run before aggregation.",
    )
    output_excerpt: str = Field(
        default="",
        description="Compact excerpt of the runner output to aid triage without storing the full payload in summaries.",
    )
    error: str | None = Field(
        default=None,
        description="Captured exception or timeout message when the run failed before scoring completed.",
    )


class EvalRunResult(BaseModel):
    """Result of a single stochastic run for an eval case."""

    run_index: int = Field(ge=1, description="1-indexed run number within the case.")
    score: float = Field(
        ge=0.0,
        le=1.0,
        description="Final score produced by the configured scorer for this run.",
    )
    passed: bool = Field(
        description="True when this individual run met or exceeded the case passing threshold and did not raise an error."
    )
    duration_ms: float = Field(
        ge=0.0,
        description="Wall-clock duration for the run in milliseconds, including timeout handling.",
    )
    output: str = Field(
        default="",
        description="Normalized runner output captured for scoring and later debugging.",
    )
    error: str | None = Field(
        default=None,
        description="Exception or timeout message captured when the runner did not complete successfully.",
    )
    started_at: datetime = Field(
        default_factory=_utc_now,
        description="UTC timestamp when the run started.",
    )
    completed_at: datetime = Field(
        default_factory=_utc_now,
        description="UTC timestamp when the run finished.",
    )


class EvalCaseResult(BaseModel):
    """Aggregated outcome for a case after multiple runs."""

    case_id: str = Field(description="Stable identifier for the evaluated case.")
    description: str = Field(
        description="Human-readable description of what the case was intended to measure."
    )
    scorer: ScorerName = Field(
        description="Scorer actually used for the final aggregated result."
    )
    run_count: int = Field(
        ge=0, description="Number of stochastic runs executed for this case."
    )
    pass_count: int = Field(
        ge=0, description="Number of runs that individually passed."
    )
    pass_rate: float = Field(
        ge=0.0,
        le=1.0,
        description="Fraction of runs that passed for this case.",
    )
    average_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Arithmetic mean score across all runs for this case.",
    )
    average_duration_ms: float = Field(
        ge=0.0,
        description="Arithmetic mean duration across all runs for this case.",
    )
    passed: bool = Field(
        description="True when the aggregated pass rate met the suite threshold for this case.",
    )
    runs: list[EvalRunResult] = Field(
        default_factory=list,
        description="Per-run results retained for debugging and aggregate calculations.",
    )
    failure_details: list[EvalFailureDetail] = Field(
        default_factory=list,
        description="Condensed failure records for runs that timed out, errored, or scored below the passing threshold.",
    )


class EvalSuite(BaseModel):
    """A maintained suite of eval cases for one agent family."""

    suite_name: str = Field(
        description="Stable suite identifier used in CLI selection, reports, and dataset names."
    )
    agent_name: str = Field(
        description="Primary agent, workflow, or subsystem this suite evaluates."
    )
    description: str = Field(
        description="Human-readable summary of the suite's behavioral claims."
    )
    cases: list[EvalCase] = Field(
        default_factory=list,
        description="Ordered eval cases that make up this suite.",
    )
    default_scorer: ScorerName = Field(
        default="semantic",
        description="Scorer used when a case does not provide an explicit override.",
    )
    pass_threshold: float = Field(
        default=0.67,
        ge=0.0,
        le=1.0,
        description="Minimum case pass rate required for the suite to count a case as passing.",
    )
    default_runs: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Default stochastic repetition count for cases that do not override runs.",
    )
    max_case_concurrency: int | None = Field(
        default=None,
        ge=1,
        le=32,
        description="Optional limit for how many cases may execute concurrently inside this suite.",
    )


class EvalSuiteResult(BaseModel):
    """Aggregated result for one suite."""

    suite_name: str = Field(description="Stable suite identifier for this result.")
    agent_name: str = Field(
        description="Primary agent or subsystem evaluated by this suite."
    )
    case_count: int = Field(ge=0, description="Number of cases executed in the suite.")
    passed_case_count: int = Field(
        ge=0,
        description="Number of cases whose aggregated result passed the suite threshold.",
    )
    case_pass_rate: float = Field(
        ge=0.0,
        le=1.0,
        description="Fraction of cases that passed in the suite.",
    )
    run_count: int = Field(
        ge=0,
        description="Total number of individual stochastic runs executed across all cases in the suite.",
    )
    passed: bool = Field(
        description="True when the suite-level case pass rate met the configured suite threshold."
    )
    total_duration_ms: float = Field(
        ge=0.0,
        description="Wall-clock duration for the full suite in milliseconds.",
    )
    started_at: datetime = Field(
        default_factory=_utc_now,
        description="UTC timestamp when suite execution started.",
    )
    completed_at: datetime = Field(
        default_factory=_utc_now,
        description="UTC timestamp when suite execution completed.",
    )
    case_results: list[EvalCaseResult] = Field(
        default_factory=list,
        description="Aggregated results for each case executed in the suite.",
    )


class EvalReport(BaseModel):
    """Top-level eval run report across one or more suites."""

    mode: EvalMode = Field(
        description="Whether the report came from fixture-backed or live-agent execution."
    )
    total_suites: int = Field(
        ge=0, description="Number of suites included in this report."
    )
    passed_suites: int = Field(
        ge=0, description="Number of suites that passed their configured thresholds."
    )
    suite_pass_rate: float = Field(
        ge=0.0,
        le=1.0,
        description="Fraction of suites that passed in this report.",
    )
    total_duration_ms: float = Field(
        ge=0.0,
        description="Wall-clock duration for the full report in milliseconds.",
    )
    started_at: datetime = Field(
        default_factory=_utc_now,
        description="UTC timestamp when report execution started.",
    )
    completed_at: datetime = Field(
        default_factory=_utc_now,
        description="UTC timestamp when report execution completed.",
    )
    suite_results: list[EvalSuiteResult] = Field(
        default_factory=list,
        description="Per-suite results included in the final eval report.",
    )


EvalRunner = Callable[[EvalCase], Awaitable[str]]


@dataclass(slots=True)
class SuiteBinding:
    """Pair a suite with the runner that executes its cases."""

    suite: EvalSuite
    runner: EvalRunner
