"""Rule injector eval suite."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from pydantic_evals import Case, Dataset

from ...agents.audit.rule_injector_agent import _rule_injector_get_default_rules
from ...models.evals import EvalCase, EvalMode, EvalSuite, SuiteBinding
from ..fixtures import fixture_output_for
from ..scorers import HostedTextScorer
from .common import HostedTextMeta, HostedTextOutput, build_text_meta, expected_text


@dataclass
class RuleInjectorInput:
    prompt: str
    language: str


_FIXTURE_OUTPUTS = {
    "rule-injector-python-selection": "selected=CWE-252,security:sql-injection,python:bare-except excluded=go:ignored-error",
    "rule-injector-go-exclusion": "selected=CWE-252,security:sql-injection,go:ignored-error excluded=python:bare-except",
}


RULE_INJECTOR_EVAL_SUITE = EvalSuite(
    suite_name="rule_injector",
    agent_name="rule_injector",
    description="Rule injector coverage for language-specific rule selection and exclusion.",
    default_scorer="keywords",
    pass_threshold=0.67,
    default_runs=1,
    max_case_concurrency=2,
    cases=[
        EvalCase(
            case_id="rule-injector-python-selection",
            description="Python audit scopes should include Python-specific and cross-language security rules.",
            prompt="Assemble rules for a Python code audit.",
            expected_keywords=["python:bare-except", "security:sql-injection"],
            tags=["rules", "python"],
            metadata={"language": "python"},
        ),
        EvalCase(
            case_id="rule-injector-go-exclusion",
            description="Go audit scopes should include Go rules and exclude Python-only rules.",
            prompt="Assemble rules for a Go code audit.",
            expected_keywords=["go:ignored-error", "excluded=python:bare-except"],
            tags=["rules", "go"],
            metadata={"language": "go"},
        ),
    ],
)


def _render_rule_selection(language: str) -> str:
    selected = [rule.rule_id for rule in _rule_injector_get_default_rules(language)]
    excluded = "python:bare-except" if language == "go" else "go:ignored-error"
    return f"selected={','.join(selected)} excluded={excluded}"


async def _run_fixture(case: EvalCase) -> str:
    await asyncio.sleep(0)
    return fixture_output_for(
        _FIXTURE_OUTPUTS,
        case.case_id,
        suite_name="rule_injector",
    )


async def _run_live(case: EvalCase) -> str:
    await asyncio.sleep(0)
    return _render_rule_selection(str(case.metadata.get("language", "python")))


def build_rule_injector_binding(mode: EvalMode) -> SuiteBinding:
    return SuiteBinding(
        suite=RULE_INJECTOR_EVAL_SUITE,
        runner=_run_fixture if mode == "fixture" else _run_live,
    )


def build_rule_injector_dataset() -> Dataset[
    RuleInjectorInput,
    HostedTextOutput,
    HostedTextMeta,
]:
    cases: list[Case[RuleInjectorInput, HostedTextOutput, HostedTextMeta]] = []
    for case in RULE_INJECTOR_EVAL_SUITE.cases:
        cases.append(
            Case(
                name=case.case_id,
                inputs=RuleInjectorInput(
                    prompt=case.prompt,
                    language=str(case.metadata.get("language", "python")),
                ),
                expected_output=HostedTextOutput(text=expected_text(case)),
                metadata=build_text_meta(case, RULE_INJECTOR_EVAL_SUITE.default_scorer),
                evaluators=(HostedTextScorer(),),
            )
        )
    return Dataset[RuleInjectorInput, HostedTextOutput, HostedTextMeta](
        name="rule-injector-golden-set",
        cases=cases,
    )


def push_rule_injector_dataset() -> dict[str, object]:
    from ..logfire_client import get_client

    with get_client() as client:
        result = client.push_dataset(
            build_rule_injector_dataset(),
            description=RULE_INJECTOR_EVAL_SUITE.description,
        )
        print(f"Pushed: {result['name']} - {result['id']}")
        return result


async def run_rule_injector_eval() -> None:
    from ..evaluator import run_eval_from_hosted

    async def rule_task(inputs: RuleInjectorInput) -> HostedTextOutput:
        await asyncio.sleep(0)
        return HostedTextOutput(text=_render_rule_selection(inputs.language))

    await run_eval_from_hosted(
        "rule-injector-golden-set",
        rule_task,
        RuleInjectorInput,
        HostedTextOutput,
        HostedTextMeta,
    )


__all__ = [
    "RULE_INJECTOR_EVAL_SUITE",
    "build_rule_injector_binding",
    "build_rule_injector_dataset",
    "push_rule_injector_dataset",
    "run_rule_injector_eval",
]
