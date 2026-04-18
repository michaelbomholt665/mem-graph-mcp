"""Fixture-backed eval suite for the validation agent."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from pydantic_evals import Case, Dataset

from ..agents.validate.validation_agent import ValidationDependencies, validation_agent
from ..models.evals import EvalCase, EvalMode, EvalSuite, ScorerName, SuiteBinding
from .fixtures import load_code_fixtures, load_violation_fixtures
from .scorers import HostedTextScorer


@dataclass
class ValidateInput:
    prompt: str
    original_file_content: str
    proposed_file_content: str
    file_path: str
    case_id: str
    language: str = "python"


@dataclass
class ValidateOutput:
    text: str


@dataclass
class ValidateMeta:
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
    "validate-approved": "approved",
    "validate-scope-drift": "rejected",
}


VALIDATE_EVAL_SUITE = EvalSuite(
    suite_name="validate",
    agent_name="validate",
    description="Validation agent baseline suite for safe approval and scope-drift rejection.",
    default_scorer="exact",
    pass_threshold=0.67,
    default_runs=3,
    cases=[
        EvalCase(
            case_id="validate-approved",
            description="The validation agent should approve a focused fix that resolves the original issue.",
            prompt="Validate the provided patch set and return a ValidationReport.",
            expected_output="approved",
            scorer="exact",
            tags=["approval"],
            metadata={
                "file_path": "fixtures/fetch_user.py",
                "original_key": "FIX_BARE_EXCEPT_ORIGINAL",
                "proposed_key": "VALIDATION_APPROVED_PATCH",
            },
        ),
        EvalCase(
            case_id="validate-scope-drift",
            description="The validation agent should reject patches that fix the bug but change unrelated scope.",
            prompt="Validate the provided patch set and return a ValidationReport.",
            expected_output="rejected",
            scorer="exact",
            tags=["scope"],
            metadata={
                "file_path": "fixtures/fetch_user.py",
                "original_key": "FIX_BARE_EXCEPT_ORIGINAL",
                "proposed_key": "VALIDATION_SCOPE_DRIFT_PATCH",
            },
        ),
    ],
)


async def _run_fixture(case: EvalCase) -> str:
    await asyncio.sleep(0)
    return _FIXTURE_OUTPUTS[case.case_id]


async def _run_live(case: EvalCase) -> str:
    file_path = case.metadata.get("file_path", "fixtures/eval_validation.py")
    deps = ValidationDependencies(
        language="python",
        original_violations=list(_VIOLATION_FIXTURES["validate"][case.case_id]),
        proposed_patches={file_path: _CODE_FIXTURES[case.metadata["proposed_key"]]},
        original_file_contents={file_path: _CODE_FIXTURES[case.metadata["original_key"]]},
    )
    result = await validation_agent.run(case.prompt, deps=deps)
    return result.output.status.value


def build_validate_binding(mode: EvalMode) -> SuiteBinding:
    return SuiteBinding(
        suite=VALIDATE_EVAL_SUITE,
        runner=_run_fixture if mode == "fixture" else _run_live,
    )


def build_validate_dataset() -> Dataset[ValidateInput, ValidateOutput, ValidateMeta]:
    cases: list[Case[ValidateInput, ValidateOutput, ValidateMeta]] = []
    for case in VALIDATE_EVAL_SUITE.cases:
        file_path = case.metadata.get("file_path", "fixtures/eval_validation.py")
        scorer = case.scorer or VALIDATE_EVAL_SUITE.default_scorer
        cases.append(
            Case(
                name=case.case_id,
                inputs=ValidateInput(
                    prompt=case.prompt,
                    original_file_content=_CODE_FIXTURES[case.metadata["original_key"]],
                    proposed_file_content=_CODE_FIXTURES[case.metadata["proposed_key"]],
                    file_path=file_path,
                    case_id=case.case_id,
                ),
                expected_output=ValidateOutput(text=case.expected_output),
                metadata=ValidateMeta(
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

    return Dataset[ValidateInput, ValidateOutput, ValidateMeta](
        name="validate-golden-set",
        cases=cases,
    )


def push_validate_dataset() -> dict[str, object]:
    from .logfire_client import get_client

    with get_client() as client:
        result = client.push_dataset(
            build_validate_dataset(),
            description=VALIDATE_EVAL_SUITE.description,
        )
        print(f"Pushed: {result['name']} - {result['id']}")
        return result


async def run_validate_eval() -> None:
    """Fetch the hosted validation dataset and evaluate it against the live agent."""
    from .evaluator import run_eval_from_hosted

    async def validate_task(inputs: ValidateInput) -> ValidateOutput:
        deps = ValidationDependencies(
            language=inputs.language,
            original_violations=list(_VIOLATION_FIXTURES["validate"][inputs.case_id]),
            proposed_patches={inputs.file_path: inputs.proposed_file_content},
            original_file_contents={inputs.file_path: inputs.original_file_content},
        )
        result = await validation_agent.run(inputs.prompt, deps=deps)
        return ValidateOutput(text=result.output.status.value)

    await run_eval_from_hosted(
        "validate-golden-set",
        validate_task,
        ValidateInput,
        ValidateOutput,
        ValidateMeta,
    )
