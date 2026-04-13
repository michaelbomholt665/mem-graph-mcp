from __future__ import annotations

import pytest

from mem_graph.evals import build_suite_registry
from mem_graph.evals.evaluator import Evaluator, main


@pytest.mark.asyncio
@pytest.mark.evals
async def test_fixture_eval_registry_runs_all_suites() -> None:
    registry = build_suite_registry(mode="fixture")
    report = await Evaluator().run_report(registry, mode="fixture")

    assert report.total_suites == 3
    assert report.passed_suites == 3
    assert {suite.suite_name for suite in report.suite_results} == {"audit", "fix", "validate"}
    assert all(case.passed for suite in report.suite_results for case in suite.case_results)


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