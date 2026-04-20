"""Fixture-backed eval suite for the map agent."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from pydantic_evals import Case, Dataset

from ..agents.map.map_agent import MapDependencies, MapReport, map_agent
from ..models.evals import EvalCase, EvalMode, EvalSuite, ScorerName, SuiteBinding
from .fixtures import fixture_output_for, format_preloaded_files, load_graph_fixtures
from .scorers import HostedTextScorer


@dataclass
class MapInput:
    prompt: str
    files: list[dict[str, str]]
    known_features: list[str]


@dataclass
class MapOutput:
    text: str


@dataclass
class MapMeta:
    case_id: str
    description: str
    scorer: ScorerName
    expected_keywords: list[str]
    expected_pattern: str | None
    tags: list[str]
    source: str = "synthetic"


_GRAPH_FIXTURES = load_graph_fixtures()["map"]

_FIXTURE_OUTPUTS = {
    "map-observability-footprint": (
        "Observability lives in src/mem_graph/observability/otel_setup.py and is "
        "triggered from src/mem_graph/server.py."
    ),
    "map-memory-surface": (
        "Memory behavior is centered in src/mem_graph/tools/memory/memory.py and "
        "is reachable from src/mem_graph/server.py."
    ),
}


MAP_EVAL_SUITE = EvalSuite(
    suite_name="map",
    agent_name="map",
    description="Map agent baseline coverage for feature ownership and file relationships.",
    default_scorer="keywords",
    pass_threshold=0.67,
    default_runs=3,
    cases=[
        EvalCase(
            case_id="map-observability-footprint",
            description="The map agent should identify where observability bootstrapping lives.",
            prompt="Map the supplied files and identify the primary observability feature location. Return a MapReport.",
            expected_keywords=[
                "observability",
                "src/mem_graph/observability/otel_setup.py",
                "src/mem_graph/server.py",
            ],
            tags=["mapping", "observability"],
        ),
        EvalCase(
            case_id="map-memory-surface",
            description="The map agent should connect the memory tool surface back to the server entry point.",
            prompt="Map the supplied files and describe the memory feature ownership and any upstream consumer. Return a MapReport.",
            expected_keywords=[
                "memory",
                "src/mem_graph/tools/memory/memory.py",
                "src/mem_graph/server.py",
            ],
            tags=["mapping", "memory"],
        ),
    ],
)


def _render_map_report(report: MapReport) -> str:
    feature_lines = [
        f"{feature.feature_name}: {feature.primary_file}" for feature in report.features
    ]
    relationship_lines = [
        f"{relationship.source_file} {relationship.relationship_kind} {relationship.target_file}"
        for relationship in report.relationships
    ]
    entry_points = ", ".join(report.entry_points) if report.entry_points else "none"
    parts = [
        report.summary,
        *feature_lines,
        *relationship_lines,
        f"entry_points: {entry_points}",
    ]
    return "\n".join(part for part in parts if part).strip()


async def _run_fixture(case: EvalCase) -> str:
    await asyncio.sleep(0)
    return fixture_output_for(_FIXTURE_OUTPUTS, case.case_id, suite_name="map")


async def _run_live(case: EvalCase) -> str:
    deps = MapDependencies(
        package_path="eval-fixture",
        known_features=list(_GRAPH_FIXTURES["known_features"]),
        skills_content="Prefer redacted observability metadata.",
        extra_file_context=format_preloaded_files(_GRAPH_FIXTURES["files"]),
    )
    result = await map_agent.run(case.prompt, deps=deps)
    return _render_map_report(result.output)


def build_map_binding(mode: EvalMode) -> SuiteBinding:
    return SuiteBinding(
        suite=MAP_EVAL_SUITE,
        runner=_run_fixture if mode == "fixture" else _run_live,
    )


def build_map_dataset() -> Dataset[MapInput, MapOutput, MapMeta]:
    cases: list[Case[MapInput, MapOutput, MapMeta]] = []
    for case in MAP_EVAL_SUITE.cases:
        scorer = case.scorer or MAP_EVAL_SUITE.default_scorer
        cases.append(
            Case(
                name=case.case_id,
                inputs=MapInput(
                    prompt=case.prompt,
                    files=list(_GRAPH_FIXTURES["files"]),
                    known_features=list(_GRAPH_FIXTURES["known_features"]),
                ),
                expected_output=MapOutput(
                    text=case.expected_output or " ".join(case.expected_keywords)
                ),
                metadata=MapMeta(
                    case_id=case.case_id,
                    description=case.description,
                    scorer=scorer,
                    expected_keywords=list(case.expected_keywords),
                    expected_pattern=case.expected_pattern,
                    tags=list(case.tags),
                ),
                evaluators=(HostedTextScorer(),),
            )
        )

    return Dataset[MapInput, MapOutput, MapMeta](
        name="map-golden-set",
        cases=cases,
    )


def push_map_dataset() -> dict[str, object]:
    from .logfire_client import get_client

    with get_client() as client:
        result = client.push_dataset(
            build_map_dataset(),
            description=MAP_EVAL_SUITE.description,
        )
        print(f"Pushed: {result['name']} - {result['id']}")
        return result


async def run_map_eval() -> None:
    """Fetch the hosted map dataset and evaluate it against the live agent."""
    from .evaluator import run_eval_from_hosted

    async def map_task(inputs: MapInput) -> MapOutput:
        deps = MapDependencies(
            package_path="eval-fixture",
            known_features=inputs.known_features,
            extra_file_context=format_preloaded_files(inputs.files),
        )
        result = await map_agent.run(inputs.prompt, deps=deps)
        return MapOutput(text=_render_map_report(result.output))

    await run_eval_from_hosted(
        "map-golden-set",
        map_task,
        MapInput,
        MapOutput,
        MapMeta,
    )
