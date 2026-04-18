from __future__ import annotations

import pytest

from mem_graph.evals.validate_evals import VALIDATE_EVAL_SUITE, build_validate_binding


@pytest.mark.asyncio
@pytest.mark.evals
async def test_validate_fixture_binding_returns_expected_outputs() -> None:
    binding = build_validate_binding("fixture")
    outputs = {case.case_id: await binding.runner(case) for case in binding.suite.cases}

    assert binding.suite is VALIDATE_EVAL_SUITE
    assert outputs == {
        "validate-approved": "approved",
        "validate-scope-drift": "rejected",
    }
