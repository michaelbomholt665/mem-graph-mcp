from __future__ import annotations

import pytest

from mem_graph.evals.map_evals import MAP_EVAL_SUITE, build_map_binding


@pytest.mark.asyncio
@pytest.mark.evals
async def test_map_fixture_binding_returns_expected_outputs() -> None:
    binding = build_map_binding("fixture")
    outputs = {case.case_id: await binding.runner(case) for case in binding.suite.cases}

    assert binding.suite is MAP_EVAL_SUITE
    assert set(outputs) == {
        "map-observability-footprint",
        "map-memory-surface",
    }
    assert "observability" in outputs["map-observability-footprint"].lower()
    assert "src/mem_graph/tools/memory/memory.py" in outputs["map-memory-surface"]
