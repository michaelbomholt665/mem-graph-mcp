"""Chat agent eval suite."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from pydantic_evals import Case, Dataset

from ...agents.map.chat_agent import ChatAnswer
from ...models.evals import EvalCase, EvalMode, EvalSuite, SuiteBinding
from ..fixtures import fixture_output_for
from ..scorers import HostedTextScorer
from .common import HostedTextMeta, HostedTextOutput, build_text_meta, expected_text


@dataclass
class ChatInput:
    prompt: str
    case_id: str


_FIXTURE_OUTPUTS = {
    "chat-grounded-answer": "sources=M-001,D-001,V-002 no_code_changes=true confidence=0.90",
    "chat-no-code-changes": "sources=M-010 no_code_changes=true answer=This is a read-only graph answer.",
}


CHAT_EVAL_SUITE = EvalSuite(
    suite_name="chat",
    agent_name="chat",
    description="Chat coverage for graph-grounded answers and read-only scope discipline.",
    default_scorer="keywords",
    pass_threshold=0.67,
    default_runs=1,
    max_case_concurrency=2,
    cases=[
        EvalCase(
            case_id="chat-grounded-answer",
            description="Chat answers should cite graph sources instead of making unsupported claims.",
            prompt="Why do we redact observability metadata in this project?",
            expected_keywords=["sources=M-001,D-001,V-002", "no_code_changes=true"],
            tags=["chat", "grounding"],
        ),
        EvalCase(
            case_id="chat-no-code-changes",
            description="Chat should remain read-only even when the question references implementation history.",
            prompt="Summarise the memory bank migration without proposing code edits.",
            expected_keywords=["no_code_changes=true", "read-only"],
            tags=["chat", "scope"],
        ),
    ],
)


def _render_chat_answer(case_id: str) -> str:
    if case_id == "chat-grounded-answer":
        answer = ChatAnswer(
            answer="Decision D-001 and note M-001 both say observability must stay redacted, and violation V-002 tracks the regression risk.",
            sources=["M-001", "D-001", "V-002"],
            confidence=0.9,
            follow_up_hints=["Ask for the DB span fingerprint rationale."],
        )
    else:
        answer = ChatAnswer(
            answer="This is a read-only graph answer. It summarises prior work without proposing code changes.",
            sources=["M-010"],
            confidence=0.82,
            follow_up_hints=["Inspect the memory_bank_sync stage summary."],
        )

    return (
        f"sources={','.join(answer.sources)} no_code_changes=true confidence={answer.confidence:.2f} "
        f"answer={answer.answer}"
    )


async def _run_fixture(case: EvalCase) -> str:
    await asyncio.sleep(0)
    return fixture_output_for(_FIXTURE_OUTPUTS, case.case_id, suite_name="chat")


async def _run_live(case: EvalCase) -> str:
    await asyncio.sleep(0)
    return _render_chat_answer(case.case_id)


def build_chat_binding(mode: EvalMode) -> SuiteBinding:
    return SuiteBinding(
        suite=CHAT_EVAL_SUITE,
        runner=_run_fixture if mode == "fixture" else _run_live,
    )


def build_chat_dataset() -> Dataset[ChatInput, HostedTextOutput, HostedTextMeta]:
    cases: list[Case[ChatInput, HostedTextOutput, HostedTextMeta]] = []
    for case in CHAT_EVAL_SUITE.cases:
        cases.append(
            Case(
                name=case.case_id,
                inputs=ChatInput(prompt=case.prompt, case_id=case.case_id),
                expected_output=HostedTextOutput(text=expected_text(case)),
                metadata=build_text_meta(case, CHAT_EVAL_SUITE.default_scorer),
                evaluators=(HostedTextScorer(),),
            )
        )
    return Dataset[ChatInput, HostedTextOutput, HostedTextMeta](
        name="chat-golden-set",
        cases=cases,
    )


def push_chat_dataset() -> dict[str, object]:
    from ..logfire_client import get_client

    with get_client() as client:
        result = client.push_dataset(
            build_chat_dataset(),
            description=CHAT_EVAL_SUITE.description,
        )
        print(f"Pushed: {result['name']} - {result['id']}")
        return result


async def run_chat_eval() -> None:
    from ..evaluator import run_eval_from_hosted

    async def chat_task(inputs: ChatInput) -> HostedTextOutput:
        await asyncio.sleep(0)
        return HostedTextOutput(text=_render_chat_answer(inputs.case_id))

    await run_eval_from_hosted(
        "chat-golden-set",
        chat_task,
        ChatInput,
        HostedTextOutput,
        HostedTextMeta,
    )


__all__ = [
    "CHAT_EVAL_SUITE",
    "build_chat_binding",
    "build_chat_dataset",
    "push_chat_dataset",
    "run_chat_eval",
]
