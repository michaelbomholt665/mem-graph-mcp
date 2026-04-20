"""Skill-level eval suites for internal audit bundles."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from pydantic_evals import Case, Dataset

from ...models.evals import EvalCase, EvalMode, EvalSuite, SuiteBinding
from ...providers.skills import load_skill
from ..fixtures import fixture_output_for
from ..scorers import HostedTextScorer
from .common import HostedTextMeta, HostedTextOutput, build_text_meta, expected_text


@dataclass
class SkillInput:
    prompt: str
    case_id: str
    skill_name: str
    code_snippet: str


_NO_FINDINGS = "detected=none"


_FIXTURE_OUTPUTS = {
    "skill-python-bare-except": "skill=python_quality detected=python:bare-except rule_count=2",
    "skill-python-clean": f"skill=python_quality {_NO_FINDINGS} rule_count=2",
    "skill-security-hardcoded-secret": "skill=security detected=security:hardcoded-secret rule_count=3",
    "skill-security-clean": f"skill=security {_NO_FINDINGS} rule_count=3",
    "skill-go-ignored-error": "skill=go_quality detected=go:ignored-error rule_count=4",
    "skill-go-clean": f"skill=go_quality {_NO_FINDINGS} rule_count=4",
    "skill-ts-any": "skill=typescript_quality detected=typescript:any rule_count=0",
    "skill-ts-clean": f"skill=typescript_quality {_NO_FINDINGS} rule_count=0",
}


PYTHON_QUALITY_SKILL_EVAL_SUITE = EvalSuite(
    suite_name="skill_python_quality",
    agent_name="skill_python_quality",
    description="Skill evals for Python quality patterns.",
    default_scorer="keywords",
    pass_threshold=1.0,
    default_runs=1,
    cases=[
        EvalCase(
            case_id="skill-python-bare-except",
            description="Python quality skill should detect a bare except.",
            prompt="Evaluate the Python quality skill on a bare except snippet.",
            expected_keywords=["python:bare-except"],
            tags=["skill", "python"],
            metadata={
                "skill_name": "python_quality",
                "code_snippet": "def fetch():\n    try:\n        work()\n    except:\n        pass\n",
            },
        ),
        EvalCase(
            case_id="skill-python-clean",
            description="Python quality skill should not flag a clean typed helper.",
            prompt="Evaluate the Python quality skill on a clean snippet.",
            expected_keywords=[_NO_FINDINGS],
            tags=["skill", "python"],
            metadata={
                "skill_name": "python_quality",
                "code_snippet": "def add(a: int, b: int) -> int:\n    return a + b\n",
            },
        ),
    ],
)

SECURITY_SKILL_EVAL_SUITE = EvalSuite(
    suite_name="skill_security",
    agent_name="skill_security",
    description="Skill evals for cross-language security patterns.",
    default_scorer="keywords",
    pass_threshold=1.0,
    default_runs=1,
    cases=[
        EvalCase(
            case_id="skill-security-hardcoded-secret",
            description="Security skill should detect hardcoded credentials.",
            prompt="Evaluate the security skill on a hardcoded secret snippet.",
            expected_keywords=["security:hardcoded-secret"],
            tags=["skill", "security"],
            metadata={
                "skill_name": "security",
                "code_snippet": 'API_KEY = "sk-live-demo-token"\n',
            },
        ),
        EvalCase(
            case_id="skill-security-clean",
            description="Security skill should not flag a parameterized query helper.",
            prompt="Evaluate the security skill on a clean snippet.",
            expected_keywords=[_NO_FINDINGS],
            tags=["skill", "security"],
            metadata={
                "skill_name": "security",
                "code_snippet": 'cursor.execute("SELECT * FROM users WHERE id = %s", [user_id])\n',
            },
        ),
    ],
)

GO_QUALITY_SKILL_EVAL_SUITE = EvalSuite(
    suite_name="skill_go_quality",
    agent_name="skill_go_quality",
    description="Skill evals for Go quality patterns.",
    default_scorer="keywords",
    pass_threshold=1.0,
    default_runs=1,
    cases=[
        EvalCase(
            case_id="skill-go-ignored-error",
            description="Go quality skill should detect ignored errors.",
            prompt="Evaluate the Go quality skill on an ignored-error snippet.",
            expected_keywords=["go:ignored-error"],
            tags=["skill", "go"],
            metadata={
                "skill_name": "go_quality",
                "code_snippet": "f, _ := os.Open(path)\n",
            },
        ),
        EvalCase(
            case_id="skill-go-clean",
            description="Go quality skill should not flag explicit error handling.",
            prompt="Evaluate the Go quality skill on a clean snippet.",
            expected_keywords=[_NO_FINDINGS],
            tags=["skill", "go"],
            metadata={
                "skill_name": "go_quality",
                "code_snippet": "f, err := os.Open(path)\nif err != nil { return err }\n",
            },
        ),
    ],
)

TYPESCRIPT_QUALITY_SKILL_EVAL_SUITE = EvalSuite(
    suite_name="skill_typescript_quality",
    agent_name="skill_typescript_quality",
    description="Skill evals for TypeScript quality patterns.",
    default_scorer="keywords",
    pass_threshold=1.0,
    default_runs=1,
    cases=[
        EvalCase(
            case_id="skill-ts-any",
            description="TypeScript quality skill should flag use of any.",
            prompt="Evaluate the TypeScript quality skill on a snippet using any.",
            expected_keywords=["typescript:any"],
            tags=["skill", "typescript"],
            metadata={
                "skill_name": "typescript_quality",
                "code_snippet": "function parse(value: any): string { return value }\n",
            },
        ),
        EvalCase(
            case_id="skill-ts-clean",
            description="TypeScript quality skill should not flag a strictly typed function.",
            prompt="Evaluate the TypeScript quality skill on a clean snippet.",
            expected_keywords=[_NO_FINDINGS],
            tags=["skill", "typescript"],
            metadata={
                "skill_name": "typescript_quality",
                "code_snippet": "function parse(value: string): string { return value.trim() }\n",
            },
        ),
    ],
)


def _detect_skill_findings(skill_name: str, code_snippet: str) -> list[str]:
    text = code_snippet.lower()
    detector = _SKILL_FINDING_DETECTORS.get(skill_name, _typescript_findings)
    return detector(text)


def _python_quality_findings(text: str) -> list[str]:
    if "except:" in text:
        return ["python:bare-except"]
    if "cache=[]" in text or "cache = []" in text:
        return ["python:mutable-default"]
    return []


def _security_findings(text: str) -> list[str]:
    if "sk-live" in text or "api_key" in text or "password" in text:
        return ["security:hardcoded-secret"]
    if "select" in text and "+" in text:
        return ["security:sql-injection"]
    return []


def _go_quality_findings(text: str) -> list[str]:
    if ", _ :=" in text or "_ :=" in text:
        return ["go:ignored-error"]
    if "go func()" in text and "for {" in text:
        return ["go:goroutine-leak"]
    return []


def _typescript_findings(text: str) -> list[str]:
    if ": any" in text:
        return ["typescript:any"]
    return []


_SKILL_FINDING_DETECTORS = {
    "python_quality": _python_quality_findings,
    "security": _security_findings,
    "go_quality": _go_quality_findings,
    "typescript_quality": _typescript_findings,
}


def _render_skill_result(skill_name: str, code_snippet: str) -> str:
    skill = load_skill(skill_name)
    detected = _detect_skill_findings(skill_name, code_snippet)
    return (
        f"skill={skill.name} detected={','.join(detected) or 'none'} "
        f"rule_count={len(skill.audit_rules)}"
    )


def _suite_by_name(name: str) -> EvalSuite:
    suites = {
        PYTHON_QUALITY_SKILL_EVAL_SUITE.suite_name: PYTHON_QUALITY_SKILL_EVAL_SUITE,
        SECURITY_SKILL_EVAL_SUITE.suite_name: SECURITY_SKILL_EVAL_SUITE,
        GO_QUALITY_SKILL_EVAL_SUITE.suite_name: GO_QUALITY_SKILL_EVAL_SUITE,
        TYPESCRIPT_QUALITY_SKILL_EVAL_SUITE.suite_name: TYPESCRIPT_QUALITY_SKILL_EVAL_SUITE,
    }
    return suites[name]


async def _run_skill_fixture(case: EvalCase, *, suite_name: str) -> str:
    await asyncio.sleep(0)
    return fixture_output_for(_FIXTURE_OUTPUTS, case.case_id, suite_name=suite_name)


async def _run_skill_live(case: EvalCase) -> str:
    await asyncio.sleep(0)
    return _render_skill_result(
        str(case.metadata.get("skill_name", "python_quality")),
        str(case.metadata.get("code_snippet", "")),
    )


def _build_skill_binding(suite: EvalSuite, mode: EvalMode) -> SuiteBinding:
    async def runner(case: EvalCase) -> str:
        if mode == "fixture":
            return await _run_skill_fixture(case, suite_name=suite.suite_name)
        return await _run_skill_live(case)

    return SuiteBinding(suite=suite, runner=runner)


def build_python_quality_skill_binding(mode: EvalMode) -> SuiteBinding:
    return _build_skill_binding(PYTHON_QUALITY_SKILL_EVAL_SUITE, mode)


def build_security_skill_binding(mode: EvalMode) -> SuiteBinding:
    return _build_skill_binding(SECURITY_SKILL_EVAL_SUITE, mode)


def build_go_quality_skill_binding(mode: EvalMode) -> SuiteBinding:
    return _build_skill_binding(GO_QUALITY_SKILL_EVAL_SUITE, mode)


def build_typescript_quality_skill_binding(mode: EvalMode) -> SuiteBinding:
    return _build_skill_binding(TYPESCRIPT_QUALITY_SKILL_EVAL_SUITE, mode)


def _build_skill_dataset(
    suite: EvalSuite,
    dataset_name: str,
) -> Dataset[SkillInput, HostedTextOutput, HostedTextMeta]:
    cases: list[Case[SkillInput, HostedTextOutput, HostedTextMeta]] = []
    for case in suite.cases:
        cases.append(
            Case(
                name=case.case_id,
                inputs=SkillInput(
                    prompt=case.prompt,
                    case_id=case.case_id,
                    skill_name=str(case.metadata.get("skill_name", "python_quality")),
                    code_snippet=str(case.metadata.get("code_snippet", "")),
                ),
                expected_output=HostedTextOutput(text=expected_text(case)),
                metadata=build_text_meta(case, suite.default_scorer),
                evaluators=(HostedTextScorer(),),
            )
        )
    return Dataset[SkillInput, HostedTextOutput, HostedTextMeta](
        name=dataset_name,
        cases=cases,
    )


def build_python_quality_skill_dataset() -> Dataset[
    SkillInput, HostedTextOutput, HostedTextMeta
]:
    return _build_skill_dataset(
        PYTHON_QUALITY_SKILL_EVAL_SUITE, "skill-python-quality-golden-set"
    )


def build_security_skill_dataset() -> Dataset[
    SkillInput, HostedTextOutput, HostedTextMeta
]:
    return _build_skill_dataset(SECURITY_SKILL_EVAL_SUITE, "skill-security-golden-set")


def build_go_quality_skill_dataset() -> Dataset[
    SkillInput, HostedTextOutput, HostedTextMeta
]:
    return _build_skill_dataset(
        GO_QUALITY_SKILL_EVAL_SUITE, "skill-go-quality-golden-set"
    )


def build_typescript_quality_skill_dataset() -> Dataset[
    SkillInput, HostedTextOutput, HostedTextMeta
]:
    return _build_skill_dataset(
        TYPESCRIPT_QUALITY_SKILL_EVAL_SUITE, "skill-typescript-quality-golden-set"
    )


def _push_skill_dataset(dataset_builder, suite: EvalSuite) -> dict[str, object]:
    from ..logfire_client import get_client

    with get_client() as client:
        result = client.push_dataset(dataset_builder(), description=suite.description)
        print(f"Pushed: {result['name']} - {result['id']}")
        return result


def push_python_quality_skill_dataset() -> dict[str, object]:
    return _push_skill_dataset(
        build_python_quality_skill_dataset, PYTHON_QUALITY_SKILL_EVAL_SUITE
    )


def push_security_skill_dataset() -> dict[str, object]:
    return _push_skill_dataset(build_security_skill_dataset, SECURITY_SKILL_EVAL_SUITE)


def push_go_quality_skill_dataset() -> dict[str, object]:
    return _push_skill_dataset(
        build_go_quality_skill_dataset, GO_QUALITY_SKILL_EVAL_SUITE
    )


def push_typescript_quality_skill_dataset() -> dict[str, object]:
    return _push_skill_dataset(
        build_typescript_quality_skill_dataset, TYPESCRIPT_QUALITY_SKILL_EVAL_SUITE
    )


async def _run_skill_eval_from_hosted(dataset_name: str) -> None:
    from ..evaluator import run_eval_from_hosted

    async def skill_task(inputs: SkillInput) -> HostedTextOutput:
        await asyncio.sleep(0)
        return HostedTextOutput(
            text=_render_skill_result(inputs.skill_name, inputs.code_snippet)
        )

    await run_eval_from_hosted(
        dataset_name,
        skill_task,
        SkillInput,
        HostedTextOutput,
        HostedTextMeta,
    )


async def run_python_quality_skill_eval() -> None:
    await _run_skill_eval_from_hosted("skill-python-quality-golden-set")


async def run_security_skill_eval() -> None:
    await _run_skill_eval_from_hosted("skill-security-golden-set")


async def run_go_quality_skill_eval() -> None:
    await _run_skill_eval_from_hosted("skill-go-quality-golden-set")


async def run_typescript_quality_skill_eval() -> None:
    await _run_skill_eval_from_hosted("skill-typescript-quality-golden-set")


__all__ = [
    "GO_QUALITY_SKILL_EVAL_SUITE",
    "PYTHON_QUALITY_SKILL_EVAL_SUITE",
    "SECURITY_SKILL_EVAL_SUITE",
    "TYPESCRIPT_QUALITY_SKILL_EVAL_SUITE",
    "build_go_quality_skill_binding",
    "build_go_quality_skill_dataset",
    "build_python_quality_skill_binding",
    "build_python_quality_skill_dataset",
    "build_security_skill_binding",
    "build_security_skill_dataset",
    "build_typescript_quality_skill_binding",
    "build_typescript_quality_skill_dataset",
    "push_go_quality_skill_dataset",
    "push_python_quality_skill_dataset",
    "push_security_skill_dataset",
    "push_typescript_quality_skill_dataset",
    "run_go_quality_skill_eval",
    "run_python_quality_skill_eval",
    "run_security_skill_eval",
    "run_typescript_quality_skill_eval",
]
