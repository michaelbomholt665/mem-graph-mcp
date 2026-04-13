"""Fixture-backed eval suite for the fixer agent."""

from __future__ import annotations

import asyncio

from ..agents.fix.fixer_agent import FixerDependencies, FixerReport, fixer_agent
from ..config import ModelTier
from ..models.evals import EvalCase, EvalMode, EvalSuite, SuiteBinding
from .fixtures import load_code_fixtures, load_violation_fixtures

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
    return _FIXTURE_OUTPUTS[case.case_id]


async def _run_live(case: EvalCase) -> str:
    file_path = case.metadata.get("file_path", "fixtures/eval_fix.py")
    violations = list(_VIOLATION_FIXTURES["fix"][case.case_id])
    deps = FixerDependencies(
        violations=violations,
        file_contents={file_path: _CODE_FIXTURES[case.metadata["fixture_key"]]},
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