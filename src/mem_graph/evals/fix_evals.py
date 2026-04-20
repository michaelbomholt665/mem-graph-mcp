"""Fixture-backed eval suite for the fixer agent."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from pydantic_evals import Case, Dataset

from ..agents.fix.fixer_agent import FixerDependencies, FixerReport, fixer_agent
from ..config import ModelTier
from ..models.evals import EvalCase, EvalMode, EvalSuite, ScorerName, SuiteBinding
from .fixtures import (
    fixture_output_for,
    load_code_fixtures,
    load_violation_fixtures,
    metadata_string,
)
from .scorers import HostedTextScorer


@dataclass
class FixInput:
    prompt: str
    file_content: str
    file_path: str
    violation_count: int
    language: str = "python"


@dataclass
class FixOutput:
    text: str


@dataclass
class FixMeta:
    case_id: str
    description: str
    scorer: ScorerName
    expected_keywords: list[str]
    expected_pattern: str | None
    tags: list[str]
    source: str = "synthetic"


_CODE_FIXTURES = load_code_fixtures()
_VIOLATION_FIXTURES = load_violation_fixtures()

_FIXTURE_OUTPUTS = {
    "fix-bare-except": "except Exception as exc:\n    raise RuntimeError(f'failed to fetch {user_id}') from exc",
    "fix-hardcoded-secret": "token = os.getenv('PAYMENTS_API_KEY', '')\nif not token:\n    raise RuntimeError('missing payments api key')",
}


FIX_EVAL_SUITE = EvalSuite(
    suite_name="fix",
    agent_name="fix",
    description="Fixer agent baseline suite for minimal safe code transformations.",
    default_scorer="keywords",
    pass_threshold=0.67,
    default_runs=3,
    cases=[
        EvalCase(
            case_id="fix-bare-except",
            description="The fixer should replace a bare except with explicit exception handling.",
            prompt="Fix the listed bare-except violation in the provided file context. Return a FixerReport.",
            expected_pattern=r"except\s+Exception",
            scorer="regex",
            tags=["safety", "python"],
            metadata={
                "fixture_key": "FIX_BARE_EXCEPT_ORIGINAL",
                "file_path": "fixtures/fetch_user.py",
            },
        ),
        EvalCase(
            case_id="fix-hardcoded-secret",
            description="The fixer should move hardcoded secrets into environment configuration.",
            prompt="Fix the listed secret-management violation in the provided file context. Return a FixerReport.",
            expected_keywords=["os.getenv", "payments_api_key", "missing"],
            scorer="keywords",
            tags=["security"],
            metadata={
                "fixture_key": "FIX_SECRET_ORIGINAL",
                "file_path": "fixtures/payments.py",
            },
        ),
    ],
)


def _render_fix_report(report: FixerReport) -> str:
    patches = "\n".join(patch.proposed_snippet for patch in report.patches)
    unresolved = "\n".join(report.unresolved_violations)
    parts = [report.summary, patches, unresolved]
    return "\n".join(part for part in parts if part).strip()


async def _run_fixture(case: EvalCase) -> str:
    await asyncio.sleep(0)
    return fixture_output_for(_FIXTURE_OUTPUTS, case.case_id, suite_name="fix")


async def _run_live(case: EvalCase) -> str:
    file_path = metadata_string(
        case.metadata,
        "file_path",
        suite_name="fix",
        case_id=case.case_id,
        default="fixtures/eval_fix.py",
    )
    fixture_key = metadata_string(
        case.metadata,
        "fixture_key",
        suite_name="fix",
        case_id=case.case_id,
    )
    violations = list(_VIOLATION_FIXTURES["fix"][case.case_id])
    deps = FixerDependencies(
        violations=violations,
        file_contents={file_path: _CODE_FIXTURES[fixture_key]},
        tier=ModelTier.STANDARD.value,
        project_id="eval-fixture",
    )
    result = await fixer_agent.run(case.prompt, deps=deps)
    return _render_fix_report(result.output)


def build_fix_binding(mode: EvalMode) -> SuiteBinding:
    return SuiteBinding(
        suite=FIX_EVAL_SUITE,
        runner=_run_fixture if mode == "fixture" else _run_live,
    )


def build_fix_dataset() -> Dataset[FixInput, FixOutput, FixMeta]:
    cases: list[Case[FixInput, FixOutput, FixMeta]] = []
    for case in FIX_EVAL_SUITE.cases:
        fixture_key = metadata_string(
            case.metadata,
            "fixture_key",
            suite_name="fix",
            case_id=case.case_id,
        )
        file_path = metadata_string(
            case.metadata,
            "file_path",
            suite_name="fix",
            case_id=case.case_id,
            default="fixtures/eval_fix.py",
        )
        scorer = case.scorer or FIX_EVAL_SUITE.default_scorer
        cases.append(
            Case(
                name=case.case_id,
                inputs=FixInput(
                    prompt=case.prompt,
                    file_content=_CODE_FIXTURES[fixture_key],
                    file_path=file_path,
                    violation_count=len(_VIOLATION_FIXTURES["fix"][case.case_id]),
                ),
                expected_output=FixOutput(
                    text=case.expected_output
                    or " ".join(case.expected_keywords)
                    or (case.expected_pattern or "")
                ),
                metadata=FixMeta(
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

    return Dataset[FixInput, FixOutput, FixMeta](
        name="fix-golden-set",
        cases=cases,
    )


def push_fix_dataset() -> dict[str, object]:
    from .logfire_client import get_client

    with get_client() as client:
        result = client.push_dataset(
            build_fix_dataset(),
            description=FIX_EVAL_SUITE.description,
        )
        print(f"Pushed: {result['name']} - {result['id']}")
        return result


async def run_fix_eval() -> None:
    """Fetch the hosted fixer dataset and evaluate it against the live agent."""
    from .evaluator import run_eval_from_hosted

    async def fix_task(inputs: FixInput) -> FixOutput:
        case_id = inputs.file_path.split("/")[-1].removesuffix(".py")
        violations = list(_VIOLATION_FIXTURES["fix"].get(case_id, []))
        if not violations:
            case_id = (
                "fix-hardcoded-secret" if "payment" in case_id else "fix-bare-except"
            )
            violations = list(_VIOLATION_FIXTURES["fix"][case_id])
        deps = FixerDependencies(
            violations=violations,
            file_contents={inputs.file_path: inputs.file_content},
            tier=ModelTier.STANDARD.value,
            project_id="eval-fixture",
        )
        result = await fixer_agent.run(inputs.prompt, deps=deps)
        return FixOutput(text=_render_fix_report(result.output))

    await run_eval_from_hosted(
        "fix-golden-set",
        fix_task,
        FixInput,
        FixOutput,
        FixMeta,
    )
