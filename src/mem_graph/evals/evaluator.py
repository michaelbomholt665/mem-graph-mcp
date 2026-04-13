"""Evaluation runner and CLI helpers for mem-graph agent suites."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from time import perf_counter
from typing import Sequence

from ..models.evals import (
    EvalCase,
    EvalCaseResult,
    EvalFailureDetail,
    EvalMode,
    EvalReport,
    EvalRunResult,
    EvalSuite,
    EvalSuiteResult,
    SuiteBinding,
)
from .scorers import score_case_output


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _excerpt(value: str, *, limit: int = 200) -> str:
    compact = " ".join(value.split())
    if len(compact) <= limit:
        return compact
    return f"{compact[:limit - 3]}..."


def _resolve_mode(value: object) -> EvalMode:
    return "live" if str(value) == "live" else "fixture"


class Evaluator:
    """Run one or more eval suites and aggregate stochastic results."""

    async def run_case(
        self,
        suite: EvalSuite,
        case: EvalCase,
        runner,
        *,
        suite_pass_threshold: float,
        runs_override: int | None = None,
    ) -> EvalCaseResult:
        run_results: list[EvalRunResult] = []
        failure_details: list[EvalFailureDetail] = []
        total_score = 0.0
        total_duration_ms = 0.0
        run_count = runs_override or case.runs or suite.default_runs
        scorer_name = case.scorer or suite.default_scorer

        for run_index in range(1, run_count + 1):
            started_at = _utc_now()
            start = perf_counter()
            output = ""
            error: str | None = None

            try:
                output = await runner(case)
                scorer_name, score = score_case_output(
                    case,
                    output,
                    default_scorer=suite.default_scorer,
                )
            except Exception as exc:  # noqa: BLE001
                score = 0.0
                error = str(exc)

            duration_ms = (perf_counter() - start) * 1000
            completed_at = _utc_now()
            passed = error is None and score >= case.passing_score

            run_results.append(
                EvalRunResult(
                    run_index=run_index,
                    score=score,
                    passed=passed,
                    duration_ms=duration_ms,
                    output=output,
                    error=error,
                    started_at=started_at,
                    completed_at=completed_at,
                )
            )

            if not passed:
                reason = (
                    error
                    if error is not None
                    else f"score {score:.2f} below threshold {case.passing_score:.2f}"
                )
                failure_details.append(
                    EvalFailureDetail(
                        run_index=run_index,
                        reason=reason,
                        score=score,
                        output_excerpt=_excerpt(output),
                        error=error,
                    )
                )

            total_score += score
            total_duration_ms += duration_ms

        pass_count = sum(1 for run in run_results if run.passed)
        pass_rate = pass_count / run_count if run_count else 0.0

        return EvalCaseResult(
            case_id=case.case_id,
            description=case.description,
            scorer=scorer_name,
            run_count=run_count,
            pass_count=pass_count,
            pass_rate=pass_rate,
            average_score=(total_score / run_count) if run_count else 0.0,
            average_duration_ms=(total_duration_ms / run_count) if run_count else 0.0,
            passed=pass_rate >= suite_pass_threshold,
            runs=run_results,
            failure_details=failure_details,
        )

    async def run_suite(
        self,
        binding: SuiteBinding,
        *,
        suite_pass_threshold: float | None = None,
        runs_override: int | None = None,
    ) -> EvalSuiteResult:
        suite = binding.suite
        threshold = suite_pass_threshold if suite_pass_threshold is not None else suite.pass_threshold
        started_at = _utc_now()
        start = perf_counter()

        case_results: list[EvalCaseResult] = []
        for case in suite.cases:
            case_results.append(
                await self.run_case(
                    suite,
                    case,
                    binding.runner,
                    suite_pass_threshold=threshold,
                    runs_override=runs_override,
                )
            )

        total_duration_ms = (perf_counter() - start) * 1000
        passed_case_count = sum(1 for result in case_results if result.passed)
        case_count = len(case_results)
        case_pass_rate = passed_case_count / case_count if case_count else 0.0

        return EvalSuiteResult(
            suite_name=suite.suite_name,
            agent_name=suite.agent_name,
            case_count=case_count,
            passed_case_count=passed_case_count,
            case_pass_rate=case_pass_rate,
            run_count=sum(result.run_count for result in case_results),
            passed=case_pass_rate >= threshold,
            total_duration_ms=total_duration_ms,
            started_at=started_at,
            completed_at=_utc_now(),
            case_results=case_results,
        )

    async def run_report(
        self,
        registry: dict[str, SuiteBinding],
        *,
        mode: EvalMode,
        selected_suites: Sequence[str] | None = None,
        suite_pass_threshold: float | None = None,
        runs_override: int | None = None,
    ) -> EvalReport:
        if selected_suites:
            missing = [name for name in selected_suites if name not in registry]
            if missing:
                raise ValueError(
                    f"Unknown eval suite(s): {', '.join(sorted(missing))}. "
                    f"Available: {', '.join(sorted(registry))}"
                )
            suite_names = list(selected_suites)
        else:
            suite_names = list(registry)

        started_at = _utc_now()
        start = perf_counter()
        suite_results = [
            await self.run_suite(
                registry[name],
                suite_pass_threshold=suite_pass_threshold,
                runs_override=runs_override,
            )
            for name in suite_names
        ]
        total_suites = len(suite_results)
        passed_suites = sum(1 for result in suite_results if result.passed)
        suite_pass_rate = passed_suites / total_suites if total_suites else 0.0

        return EvalReport(
            mode=mode,
            total_suites=total_suites,
            passed_suites=passed_suites,
            suite_pass_rate=suite_pass_rate,
            total_duration_ms=(perf_counter() - start) * 1000,
            started_at=started_at,
            completed_at=_utc_now(),
            suite_results=suite_results,
        )


def render_eval_report(report: EvalReport) -> str:
    """Format an eval report for terminal output."""
    lines = [
        f"Mode: {report.mode}",
        (
            f"Suites: {report.passed_suites}/{report.total_suites} passed "
            f"({report.suite_pass_rate:.0%}) in {report.total_duration_ms:.1f}ms"
        ),
    ]
    for suite in report.suite_results:
        lines.append(
            (
                f"- {suite.suite_name}: {'PASS' if suite.passed else 'FAIL'} | "
                f"cases {suite.passed_case_count}/{suite.case_count} ({suite.case_pass_rate:.0%}) | "
                f"runs {suite.run_count}"
            )
        )
        for case in suite.case_results:
            lines.append(
                (
                    f"  * {case.case_id}: {'PASS' if case.passed else 'FAIL'} | "
                    f"pass_rate {case.pass_rate:.0%} | avg_score {case.average_score:.2f}"
                )
            )
            if case.failure_details:
                lines.append(f"    last_failure: {case.failure_details[-1].reason}")
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run mem-graph eval suites.")
    parser.add_argument("suites", nargs="*", help="Optional subset of suite names to run.")
    parser.add_argument(
        "--mode",
        choices=("fixture", "live"),
        default="fixture",
        help="Use deterministic fixture outputs or run live agents.",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=None,
        help="Override the per-case run count.",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=None,
        help="Override the suite pass-rate threshold.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the full report as JSON instead of a text summary.",
    )
    return parser


async def main_async(argv: Sequence[str] | None = None) -> int:
    from . import build_suite_registry

    parser = _build_parser()
    args = parser.parse_args(argv)
    mode = _resolve_mode(args.mode)

    evaluator = Evaluator()
    registry = build_suite_registry(mode=mode)
    report = await evaluator.run_report(
        registry,
        mode=mode,
        selected_suites=args.suites or None,
        suite_pass_threshold=args.threshold,
        runs_override=args.runs,
    )

    if args.json:
        print(json.dumps(report.model_dump(mode="json"), indent=2))
    else:
        print(render_eval_report(report))

    return 0 if report.passed_suites == report.total_suites else 1


def main(argv: Sequence[str] | None = None) -> int:
    try:
        return asyncio.run(main_async(argv))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2