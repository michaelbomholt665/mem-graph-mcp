from __future__ import annotations

import pytest

from mem_graph.evals.fix_evals import FIX_EVAL_SUITE, build_fix_binding


@pytest.mark.asyncio
@pytest.mark.evals
async def test_fix_fixture_binding_returns_expected_outputs() -> None:
    binding = build_fix_binding("fixture")
    outputs = {case.case_id: await binding.runner(case) for case in binding.suite.cases}

    assert binding.suite is FIX_EVAL_SUITE
    assert set(outputs) == {"fix-bare-except", "fix-hardcoded-secret"}
    assert "except Exception" in outputs["fix-bare-except"]
    assert "os.getenv" in outputs["fix-hardcoded-secret"]
