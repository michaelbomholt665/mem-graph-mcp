from __future__ import annotations

import asyncio
import json

import pytest
from starlette.requests import Request

from mem_graph.evals import build_suite_registry
from mem_graph.evals.evaluator import Evaluator, main, write_json_report


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

    assert report.total_suites == 5
    assert report.passed_suites == 5
    assert {suite.suite_name for suite in report.suite_results} == {
        "audit",
        "document",
        "fix",
        "map",
        "validate",
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
    assert payload["total_suites"] == 5
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
    assert rows == [["fixture", 5, 5, output_path, "fixture-ci", "pytest", None]]

    from mem_graph import server as server_mod

    response = await server_mod._dashboard_evals(
        _request("/dashboard/api/evals", f"project_id={project['project_id']}")
    )

    assert response.status_code == 200
    evals = json.loads(bytes(response.body).decode())["evals"]
    assert evals[0]["id"] == eval_run_id
    assert evals[0]["logfire_run_id"] is None


@pytest.mark.asyncio
@pytest.mark.evals
async def test_tier_comparison_assertions_can_use_stable_bindings() -> None:
    from mem_graph.models.evals import EvalCase, EvalSuite, SuiteBinding

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
