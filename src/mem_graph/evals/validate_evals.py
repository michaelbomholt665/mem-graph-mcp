"""Fixture-backed eval suite for the validation agent."""

from __future__ import annotations

import asyncio

from ..agents.validate.validation_agent import ValidationDependencies, validation_agent
from ..models.evals import EvalCase, EvalMode, EvalSuite, SuiteBinding
from .fixtures import load_code_fixtures, load_violation_fixtures

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