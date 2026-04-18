from __future__ import annotations

import pytest

from mem_graph.evals.document_evals import DOCUMENT_EVAL_SUITE, build_document_binding


@pytest.mark.asyncio
@pytest.mark.evals
async def test_document_fixture_binding_returns_expected_outputs() -> None:
    binding = build_document_binding("fixture")
    outputs = {case.case_id: await binding.runner(case) for case in binding.suite.cases}

    assert binding.suite is DOCUMENT_EVAL_SUITE
    assert set(outputs) == {
        "document-task-plan",
        "document-decision-review",
    }
    assert "planning" in outputs["document-task-plan"].lower()
    assert "honoured" in outputs["document-decision-review"].lower()
