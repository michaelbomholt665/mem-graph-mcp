from __future__ import annotations

import asyncio
import json
from time import perf_counter

import pytest
from starlette.requests import Request

from mem_graph.evals import build_suite_registry
from mem_graph.evals.evaluator import Evaluator, main, write_json_report
from mem_graph.evals.scorers import exact_match_score
from mem_graph.models.evals import EvalCase, EvalSuite, SuiteBinding


def _request(path: str = "/", query: str = "") -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "query_string": query.encode(),
            "headers": [],
        }
    )


@pytest.mark.asyncio
@pytest.mark.evals
async def test_fixture_eval_registry_runs_all_suites() -> None:
    registry = build_suite_registry(mode="fixture")
    report = await Evaluator().run_report(registry, mode="fixture")

    assert report.total_suites == 18
    assert report.passed_suites == 18
    assert {suite.suite_name for suite in report.suite_results} == {
        "audit",
        "chat",
        "document",
        "fix",
        "map",
        "orchestrator",
        "router",
        "rule_injector",
        "sentry",
        "skill_go_quality",
        "skill_python_quality",
        "skill_security",
        "skill_typescript_quality",
        "triage",
        "validate",
        "workflow_autopilot",
        "workflow_feature_implementation",
        "workflow_package_audit",
    }
    assert all(
        case.passed for suite in report.suite_results for case in suite.case_results
    )


@pytest.mark.asyncio
@pytest.mark.evals
async def test_fixture_eval_registry_supports_subset_and_run_override() -> None:
    registry = build_suite_registry(mode="fixture")
    report = await Evaluator().run_report(
        registry,
        mode="fixture",
        selected_suites=["audit"],
        runs_override=1,
    )

    assert report.total_suites == 1
    suite = report.suite_results[0]
    assert suite.suite_name == "audit"
    assert suite.run_count == len(suite.case_results)


@pytest.mark.evals
def test_eval_cli_fixture_mode(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["--mode", "fixture", "audit", "--runs", "1"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Mode: fixture" in captured.out
    assert "- audit: PASS" in captured.out


@pytest.mark.asyncio
@pytest.mark.evals
async def test_eval_report_can_be_written_and_persisted(db, tmp_path) -> None:
    from mem_graph.tools.work.projects import project_create

    registry = build_suite_registry(mode="fixture")
    evaluator = Evaluator()
    report = await evaluator.run_report(registry, mode="fixture", runs_override=1)

    output_path = write_json_report(report, tmp_path / "reports" / "fixture.json")
    payload = json.loads(
        (tmp_path / "reports" / "fixture.json").read_text(encoding="utf-8")
    )
    assert payload["total_suites"] == 18
    assert output_path.endswith("fixture.json")

    project = await project_create(name="Eval Project", description="Tracks eval runs")
    eval_run_id = evaluator.persist_report_summary(
        report,
        conn=db,
        project_id=project["project_id"],
        trigger="pytest",
        report_path=output_path,
        label="fixture-ci",
    )

    result = db.execute(
        """
        MATCH (p:Project {id: $project_id})-[:HAS_EVAL_RUN]->(e:EvalRun {id: $eval_run_id})
        RETURN e.mode, e.total_suites, e.passed_suites, e.report_path, e.label, e.trigger, e.logfire_run_id
        """,
        {"project_id": project["project_id"], "eval_run_id": eval_run_id},
    )
    rows = result.get_all()
    assert rows == [["fixture", 18, 18, output_path, "fixture-ci", "pytest", None]]

    from mem_graph import server as server_mod

    response = server_mod._dashboard_evals(
        _request("/dashboard/api/evals", f"project_id={project['project_id']}")
    )

    assert response.status_code == 200
    evals = json.loads(bytes(response.body).decode())["evals"]
    assert evals[0]["id"] == eval_run_id
    assert evals[0]["logfire_run_id"] is None


@pytest.mark.asyncio
@pytest.mark.evals
async def test_tier_comparison_assertions_can_use_stable_bindings() -> None:
    suite = EvalSuite(
        suite_name="tier-comparison",
        agent_name="fixture",
        description="Stable fixture-only comparison coverage.",
        default_scorer="exact",
        pass_threshold=1.0,
        default_runs=1,
        cases=[
            EvalCase(
                case_id="tier-case",
                description="Simple exact-match tier comparison.",
                prompt="Respond with approved.",
                expected_output="approved",
                scorer="exact",
                runs=1,
                passing_score=1.0,
            )
        ],
    )

    async def quick_runner(case: EvalCase) -> str:
        await asyncio.sleep(0)
        return "rejected"

    async def expert_runner(case: EvalCase) -> str:
        await asyncio.sleep(0)
        return "approved"

    evaluator = Evaluator()
    quick_report = await evaluator.run_report(
        {"tier-comparison": SuiteBinding(suite=suite, runner=quick_runner)},
        mode="fixture",
    )
    expert_report = await evaluator.run_report(
        {"tier-comparison": SuiteBinding(suite=suite, runner=expert_runner)},
        mode="fixture",
    )

    assert quick_report.suite_pass_rate < expert_report.suite_pass_rate


@pytest.mark.asyncio
@pytest.mark.evals
async def test_evaluator_respects_case_timeout_override() -> None:
    suite = EvalSuite(
        suite_name="timeout",
        agent_name="fixture",
        description="Timeout handling",
        default_scorer="exact",
        default_runs=1,
        cases=[
            EvalCase(
                case_id="timeout-case",
                description="Runner should time out.",
                prompt="wait",
                expected_output="done",
                scorer="exact",
                timeout_s=0.01,
            )
        ],
    )

    async def slow_runner(case: EvalCase) -> str:
        del case
        await asyncio.sleep(0.05)
        return "done"

    report = await Evaluator().run_report(
        {"timeout": SuiteBinding(suite=suite, runner=slow_runner)},
        mode="fixture",
    )

    failure = report.suite_results[0].case_results[0].failure_details[0]
    assert "0.01s" in failure.reason


@pytest.mark.asyncio
@pytest.mark.evals
async def test_evaluator_runs_cases_in_parallel() -> None:
    suite = EvalSuite(
        suite_name="parallel",
        agent_name="fixture",
        description="Parallel execution coverage.",
        default_scorer="exact",
        default_runs=1,
        max_case_concurrency=4,
        cases=[
            EvalCase(
                case_id=f"case-{index}",
                description="Parallel case.",
                prompt="approved",
                expected_output="approved",
                scorer="exact",
            )
            for index in range(4)
        ],
    )

    async def slow_runner(case: EvalCase) -> str:
        del case
        await asyncio.sleep(0.1)
        return "approved"

    started = perf_counter()
    report = await Evaluator().run_report(
        {"parallel": SuiteBinding(suite=suite, runner=slow_runner)},
        mode="fixture",
    )
    elapsed = perf_counter() - started

    assert report.passed_suites == 1
    assert elapsed < 0.25


def test_text_normalization_handles_unicode_equivalents() -> None:
    assert exact_match_score("Cafe\u0301", "Café") == pytest.approx(1.0)


@pytest.mark.asyncio
@pytest.mark.evals
async def test_invalid_regex_suite_fails_fast() -> None:
    suite = EvalSuite(
        suite_name="invalid-regex",
        agent_name="fixture",
        description="Regex validation",
        default_scorer="regex",
        default_runs=1,
        cases=[
            EvalCase(
                case_id="regex-case",
                description="Bad regex.",
                prompt="test",
                expected_pattern="[unterminated",
                scorer="regex",
            )
        ],
    )

    async def quick_runner(case: EvalCase) -> str:
        del case
        await asyncio.sleep(0)
        return "test"

    with pytest.raises(ValueError, match="Invalid regex"):
        await Evaluator().run_report(
            {"invalid-regex": SuiteBinding(suite=suite, runner=quick_runner)},
            mode="fixture",
        )
