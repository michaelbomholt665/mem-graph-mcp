"""Evaluation runner and CLI helpers for mem-graph agent suites."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Protocol, Sequence, TypeVar

import anyio

from ..ids import id_generate_v7
from ..models.evals import (
    EvalCase,
    EvalCaseResult,
    EvalFailureDetail,
    EvalMode,
    EvalReport,
    EvalRunResult,
    EvalSuite,
    EvalSuiteResult,
    ScorerName,
    SuiteBinding,
)
from .audit_evals import push_audit_dataset, run_audit_eval
from .document_evals import push_document_dataset, run_document_eval
from .fix_evals import push_fix_dataset, run_fix_eval
from .map_evals import push_map_dataset, run_map_eval
from .scorers import score_case_output, validate_suite_configuration
from .suites import (
    push_chat_dataset,
    push_go_quality_skill_dataset,
    push_orchestrator_dataset,
    push_python_quality_skill_dataset,
    push_router_dataset,
    push_rule_injector_dataset,
    push_security_skill_dataset,
    push_sentry_dataset,
    push_triage_dataset,
    push_typescript_quality_skill_dataset,
    push_workflow_autopilot_dataset,
    push_workflow_feature_implementation_dataset,
    push_workflow_package_audit_dataset,
    run_chat_eval,
    run_go_quality_skill_eval,
    run_orchestrator_eval,
    run_python_quality_skill_eval,
    run_router_eval,
    run_rule_injector_eval,
    run_security_skill_eval,
    run_sentry_eval,
    run_triage_eval,
    run_typescript_quality_skill_eval,
    run_workflow_autopilot_eval,
    run_workflow_feature_implementation_eval,
    run_workflow_package_audit_eval,
)
from .validate_evals import push_validate_dataset, run_validate_eval

InputsT = TypeVar("InputsT")
OutputT = TypeVar("OutputT")
MetadataT = TypeVar("MetadataT")

# Default eval parameters — document why these values were chosen so they are
# not silently cargo-culted in individual suite definitions.
DEFAULT_PASS_THRESHOLD = 0.67  # Allows one miss in three runs for stochastic tolerance
DEFAULT_RUNS = 3  # Minimum for meaningful stochastic variance measurement
DEFAULT_CASE_TIMEOUT_S = 120  # Per-case timeout in seconds for live agent runs


class GraphConnection(Protocol):
    """Minimal database connection protocol required for eval summary persistence."""

    def execute(
        self,
        query: str,
        params: dict[str, object] | None = None,
    ) -> Any: ...


_HOSTED_PUSHERS = {
    "audit": push_audit_dataset,
    "chat": push_chat_dataset,
    "document": push_document_dataset,
    "fix": push_fix_dataset,
    "map": push_map_dataset,
    "orchestrator": push_orchestrator_dataset,
    "router": push_router_dataset,
    "rule_injector": push_rule_injector_dataset,
    "sentry": push_sentry_dataset,
    "skill_go_quality": push_go_quality_skill_dataset,
    "skill_python_quality": push_python_quality_skill_dataset,
    "skill_security": push_security_skill_dataset,
    "skill_typescript_quality": push_typescript_quality_skill_dataset,
    "triage": push_triage_dataset,
    "validate": push_validate_dataset,
    "workflow_autopilot": push_workflow_autopilot_dataset,
    "workflow_feature_implementation": push_workflow_feature_implementation_dataset,
    "workflow_package_audit": push_workflow_package_audit_dataset,
}

_HOSTED_RUNNERS = {
    "audit": run_audit_eval,
    "chat": run_chat_eval,
    "document": run_document_eval,
    "fix": run_fix_eval,
    "map": run_map_eval,
    "orchestrator": run_orchestrator_eval,
    "router": run_router_eval,
    "rule_injector": run_rule_injector_eval,
    "sentry": run_sentry_eval,
    "skill_go_quality": run_go_quality_skill_eval,
    "skill_python_quality": run_python_quality_skill_eval,
    "skill_security": run_security_skill_eval,
    "skill_typescript_quality": run_typescript_quality_skill_eval,
    "triage": run_triage_eval,
    "validate": run_validate_eval,
    "workflow_autopilot": run_workflow_autopilot_eval,
    "workflow_feature_implementation": run_workflow_feature_implementation_eval,
    "workflow_package_audit": run_workflow_package_audit_eval,
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _excerpt(value: str, *, limit: int = 200) -> str:
    compact = " ".join(value.split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 3]}..."


def _resolve_mode(value: object) -> EvalMode:
    return "live" if str(value) == "live" else "fixture"


class Evaluator:
    """Run one or more eval suites and aggregate stochastic results."""

    async def _execute_case_run(
        self,
        case: EvalCase,
        runner,
        run_index: int,
        default_scorer: ScorerName,
    ) -> tuple[EvalRunResult, EvalFailureDetail | None, ScorerName]:
        started_at = _utc_now()
        start = perf_counter()
        output = ""
        error: str | None = None
        scorer_name: ScorerName = case.scorer or default_scorer
        timeout_s = case.timeout_s or DEFAULT_CASE_TIMEOUT_S

        try:
            output = await asyncio.wait_for(runner(case), timeout=timeout_s)
            scorer_name, score = score_case_output(
                case,
                output,
                default_scorer=default_scorer,
            )
        except asyncio.TimeoutError:
            score = 0.0
            error = f"Eval case timed out after {timeout_s}s"
        except Exception as exc:  # noqa: BLE001
            score = 0.0
            error = str(exc)

        duration_ms = (perf_counter() - start) * 1000
        completed_at = _utc_now()
        passed = error is None and score >= case.passing_score

        run_result = EvalRunResult(
            run_index=run_index,
            score=score,
            passed=passed,
            duration_ms=duration_ms,
            output=output,
            error=error,
            started_at=started_at,
            completed_at=completed_at,
        )

        failure_detail = None
        if not passed:
            reason = (
                error
                if error is not None
                else f"score {score:.2f} below threshold {case.passing_score:.2f}"
            )
            failure_detail = EvalFailureDetail(
                run_index=run_index,
                reason=reason,
                score=score,
                output_excerpt=_excerpt(output),
                error=error,
            )

        return run_result, failure_detail, scorer_name

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
        run_count = _resolve_case_run_count(
            case,
            suite_default_runs=suite.default_runs,
            runs_override=runs_override,
        )
        scorer_name = case.scorer or suite.default_scorer

        for run_index in range(1, run_count + 1):
            run_result, failure_detail, last_scorer = await self._execute_case_run(
                case, runner, run_index, suite.default_scorer
            )
            scorer_name = last_scorer
            run_results.append(run_result)
            if failure_detail:
                failure_details.append(failure_detail)

            total_score += run_result.score
            total_duration_ms += run_result.duration_ms

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
        threshold = (
            suite_pass_threshold
            if suite_pass_threshold is not None
            else suite.pass_threshold
        )
        validate_suite_configuration(suite)
        started_at = _utc_now()
        start = perf_counter()

        case_results: list[EvalCaseResult | None] = [None] * len(suite.cases)
        concurrency = suite.max_case_concurrency or max(1, len(suite.cases))
        semaphore = asyncio.Semaphore(concurrency)

        async def execute_case(index: int, case: EvalCase) -> None:
            async with semaphore:
                case_results[index] = await self.run_case(
                    suite,
                    case,
                    binding.runner,
                    suite_pass_threshold=threshold,
                    runs_override=runs_override,
                )

        async with anyio.create_task_group() as task_group:
            for index, case in enumerate(suite.cases):
                task_group.start_soon(execute_case, index, case)

        resolved_case_results = [
            result for result in case_results if result is not None
        ]

        total_duration_ms = (perf_counter() - start) * 1000
        passed_case_count = sum(1 for result in resolved_case_results if result.passed)
        case_count = len(resolved_case_results)
        case_pass_rate = passed_case_count / case_count if case_count else 0.0

        return EvalSuiteResult(
            suite_name=suite.suite_name,
            agent_name=suite.agent_name,
            case_count=case_count,
            passed_case_count=passed_case_count,
            case_pass_rate=case_pass_rate,
            run_count=sum(result.run_count for result in resolved_case_results),
            passed=case_pass_rate >= threshold,
            total_duration_ms=total_duration_ms,
            started_at=started_at,
            completed_at=_utc_now(),
            case_results=resolved_case_results,
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

        for suite_name in suite_names:
            validate_suite_configuration(registry[suite_name].suite)

        started_at = _utc_now()
        start = perf_counter()
        suite_results: list[EvalSuiteResult | None] = [None] * len(suite_names)

        async def execute_suite(index: int, suite_name: str) -> None:
            suite_results[index] = await self.run_suite(
                registry[suite_name],
                suite_pass_threshold=suite_pass_threshold,
                runs_override=runs_override,
            )

        async with anyio.create_task_group() as task_group:
            for index, suite_name in enumerate(suite_names):
                task_group.start_soon(execute_suite, index, suite_name)

        resolved_suite_results = [
            result for result in suite_results if result is not None
        ]
        total_suites = len(resolved_suite_results)
        passed_suites = sum(1 for result in resolved_suite_results if result.passed)
        suite_pass_rate = passed_suites / total_suites if total_suites else 0.0

        return EvalReport(
            mode=mode,
            total_suites=total_suites,
            passed_suites=passed_suites,
            suite_pass_rate=suite_pass_rate,
            total_duration_ms=(perf_counter() - start) * 1000,
            started_at=started_at,
            completed_at=_utc_now(),
            suite_results=resolved_suite_results,
        )

    def persist_report_summary(
        self,
        report: EvalReport,
        *,
        conn: GraphConnection,
        project_id: str,
        trigger: str = "manual",
        report_path: str | None = None,
        label: str | None = None,
        logfire_run_id: str | None = None,
    ) -> str:
        """Persist a compact eval summary to the graph for trend tracking."""
        eval_run_id = id_generate_v7()
        suite_names = [suite.suite_name for suite in report.suite_results]
        passed_suite_names = [
            suite.suite_name for suite in report.suite_results if suite.passed
        ]
        summary = render_eval_report(report)

        conn.execute(
            """
            CREATE (e:EvalRun {
                id: $id,
                mode: $mode,
                label: $label,
                trigger: $trigger,
                logfire_run_id: $logfire_run_id,
                total_suites: $total_suites,
                passed_suites: $passed_suites,
                suite_pass_rate: $suite_pass_rate,
                total_duration_ms: $total_duration_ms,
                suite_names: $suite_names,
                passed_suite_names: $passed_suite_names,
                summary: $summary,
                report_path: $report_path,
                started_at: $started_at,
                completed_at: $completed_at,
                persisted_at: current_timestamp()
            })
            """,
            {
                "id": eval_run_id,
                "mode": report.mode,
                "label": label,
                "trigger": trigger,
                "logfire_run_id": logfire_run_id,
                "total_suites": report.total_suites,
                "passed_suites": report.passed_suites,
                "suite_pass_rate": report.suite_pass_rate,
                "total_duration_ms": report.total_duration_ms,
                "suite_names": suite_names,
                "passed_suite_names": passed_suite_names,
                "summary": summary,
                "report_path": report_path,
                "started_at": report.started_at,
                "completed_at": report.completed_at,
            },
        )
        conn.execute(
            """
            MATCH (p:Project {id: $project_id}), (e:EvalRun {id: $eval_run_id})
            CREATE (p)-[:HAS_EVAL_RUN]->(e)
            """,
            {"project_id": project_id, "eval_run_id": eval_run_id},
        )
        return eval_run_id


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
                f"cases {suite.passed_case_count}/{suite.case_count} "
                f"({suite.case_pass_rate:.0%}) | runs {suite.run_count}"
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


def _resolve_case_run_count(
    case: EvalCase,
    *,
    suite_default_runs: int,
    runs_override: int | None,
) -> int:
    if runs_override is not None:
        return runs_override
    if "runs" in case.model_fields_set:
        return case.runs
    return suite_default_runs


def write_json_report(report: EvalReport, output_path: str | Path) -> str:
    """Write the full eval report to disk as machine-readable JSON."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2),
        encoding="utf-8",
    )
    return str(path)


def _resolve_hosted_suites(selected_suites: Sequence[str] | None) -> list[str]:
    suite_names = list(selected_suites or _HOSTED_RUNNERS)
    missing = [name for name in suite_names if name not in _HOSTED_RUNNERS]
    if missing:
        raise ValueError(
            f"Unknown eval suite(s): {', '.join(sorted(missing))}. "
            f"Available: {', '.join(sorted(_HOSTED_RUNNERS))}"
        )
    return suite_names


def push_all_datasets(
    selected_suites: Sequence[str] | None = None,
) -> dict[str, object]:
    """Push all golden sets to Logfire hosted storage. Safe to re-run."""
    suite_names = _resolve_hosted_suites(selected_suites)
    return {name: _HOSTED_PUSHERS[name]() for name in suite_names}


async def run_all_evals(selected_suites: Sequence[str] | None = None) -> None:
    """Fetch hosted datasets and run evals against live agents."""
    from .. import __version__
    from ..observability import setup_logfire

    setup_logfire(service_name="mem-graph-evals", service_version=__version__)
    for suite_name in _resolve_hosted_suites(selected_suites):
        await _HOSTED_RUNNERS[suite_name]()


async def run_eval_from_hosted(
    dataset_name: str,
    task,
    input_type: type[InputsT],
    output_type: type[OutputT],
    metadata_type: type[MetadataT] | None = None,
    *,
    name: str | None = None,
    repeat: int = 1,
    max_concurrency: int | None = None,
    progress: bool = True,
):
    """Load a Logfire hosted dataset and evaluate it with pydantic-evals."""
    from .logfire_client import get_client
    from .scorers import HostedTextScorer

    with get_client() as client:
        dataset = client.get_dataset(
            dataset_name,
            input_type=input_type,
            output_type=output_type,
            metadata_type=metadata_type,
            custom_evaluator_types=(HostedTextScorer,),
        )

    report = await dataset.evaluate(
        task,
        name=name,
        repeat=repeat,
        max_concurrency=max_concurrency,
        progress=progress,
    )
    report.print()
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run mem-graph eval suites.")
    parser.add_argument(
        "suites", nargs="*", help="Optional subset of suite names to run."
    )
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
    parser.add_argument(
        "--output",
        help="Optional path to write the full JSON report to disk.",
    )
    parser.add_argument(
        "--persist-project-id",
        help="Persist a compact eval summary to the graph for the given project ID.",
    )
    parser.add_argument(
        "--persist-trigger",
        default="manual",
        help="Label describing what triggered the persisted eval run.",
    )
    parser.add_argument(
        "--persist-label",
        default=None,
        help="Optional label for the persisted eval run, such as ci or release.",
    )
    parser.add_argument(
        "--push-hosted-datasets",
        action="store_true",
        help="Push local eval suites to Logfire hosted datasets and exit.",
    )
    parser.add_argument(
        "--push",
        action="store_true",
        help="Alias for --push-hosted-datasets.",
    )
    parser.add_argument(
        "--hosted",
        action="store_true",
        help="Run Logfire hosted datasets against live agents instead of local suites.",
    )
    return parser


async def main_async(argv: Sequence[str] | None = None) -> int:
    from .. import __version__
    from ..observability import (
        setup_logfire,
        setup_observability,
        shutdown_logfire,
        shutdown_observability,
    )
    from . import build_suite_registry

    # Initialize observability for the eval process.
    setup_logfire(service_name="mem-graph-evals", service_version=__version__)
    setup_observability(service_name="mem-graph-evals", service_version=__version__)

    try:
        parser = _build_parser()
        args = parser.parse_args(argv)
        if args.push_hosted_datasets or args.push:
            push_all_datasets(args.suites or None)
            return 0
        if args.hosted:
            await run_all_evals(args.suites or None)
            return 0

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

        output_path: str | None = None
        if args.output:
            output_path = write_json_report(report, args.output)

        if args.persist_project_id:
            from ..db import db_close_engine, db_get_connection, db_init_engine

            db_init_engine()
            try:
                evaluator.persist_report_summary(
                    report,
                    conn=db_get_connection(),
                    project_id=args.persist_project_id,
                    trigger=args.persist_trigger,
                    report_path=output_path,
                    label=args.persist_label,
                )
            finally:
                db_close_engine()

        if args.json:
            print(json.dumps(report.model_dump(mode="json"), indent=2))
        else:
            print(render_eval_report(report))

        return 0 if report.passed_suites == report.total_suites else 1
    finally:
        shutdown_observability()
        shutdown_logfire()


def main(argv: Sequence[str] | None = None) -> int:
    try:
        return asyncio.run(main_async(argv))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
