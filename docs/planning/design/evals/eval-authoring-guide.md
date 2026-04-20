# Eval Authoring Guide

This repository uses a two-layer eval pattern.

- Core eval infrastructure lives in `src/mem_graph/evals/`.
- Additional agent, workflow, and skill suites live in `src/mem_graph/evals/suites/`.

Every new suite should be deterministic in fixture mode, runnable in hosted mode, and easy to register in `src/mem_graph/evals/__init__.py`.

## Anatomy of a Suite

Each suite follows the same shape.

1. Define an `EvalSuite` with stable `case_id` values, descriptions, scorer defaults, thresholds, and concurrency.
2. Implement a fixture runner for CI-safe deterministic outputs.
3. Implement a live runner for real agent or workflow execution.
4. Expose a `SuiteBinding` builder.
5. Build a hosted `Dataset[...]` using typed input, output, and metadata models.
6. Expose `push_*_dataset()` and `run_*_eval()` helpers.

Minimal pattern:

```python
MY_SUITE = EvalSuite(
    suite_name="my_suite",
    agent_name="my_agent",
    description="What this suite proves.",
    default_scorer="keywords",
    pass_threshold=0.67,
    default_runs=1,
    cases=[
        EvalCase(
            case_id="my-case",
            description="Single falsifiable claim.",
            prompt="Run the workflow.",
            expected_keywords=["approved", "notes=1"],
            tags=["workflow"],
        )
    ],
)


async def _run_fixture(case: EvalCase) -> str:
    return fixture_output_for(_FIXTURE_OUTPUTS, case.case_id, suite_name="my_suite")


async def _run_live(case: EvalCase) -> str:
    ...


def build_my_binding(mode: EvalMode) -> SuiteBinding:
    return SuiteBinding(
        suite=MY_SUITE,
        runner=_run_fixture if mode == "fixture" else _run_live,
    )
```

## Scorer Selection

Supported scorers are defined in `src/mem_graph/evals/scorers.py`.

- `exact`: strict normalized equality.
- `keywords`: proportion of expected keywords found in normalized output.
- `regex`: compiled, validated regex match.
- `semantic`: embedding-based similarity with token-overlap fallback.

Use the weakest scorer that still proves the claim. `exact` is best for finite state outputs such as `approved` or `rejected`. `keywords` works well for structured summary strings. `regex` is useful for code-shape assertions. `semantic` is the fallback for narrative outputs.

## Metadata Rules

`EvalCase.metadata` is JSON-safe and intentionally wide. If a suite requires string metadata values, use `metadata_string(...)` from `src/mem_graph/evals/fixtures.py` instead of indexing the dict directly. That keeps hosted datasets type-safe and produces better error messages when metadata is malformed.

## Infrastructure Guarantees

The evaluator already provides the following behavior. New suites should rely on it instead of reimplementing it.

- Per-case timeout enforcement with `asyncio.wait_for`.
- In-suite parallel execution via `anyio.create_task_group`.
- Suite-level regex validation before parallel execution begins.
- Unicode normalization in text scoring.
- Suite default run-count inheritance unless a case explicitly overrides `runs`.

## Writing Good Cases

Each case should make one claim only.

Good:

```python
EvalCase(
    case_id="router-workflow-mode",
    description="Explicit workflow requests should select subagent_workflow mode.",
    prompt="Plan this feature using the full workflow.",
    expected_keywords=["subagent_workflow"],
)
```

Too broad:

```python
EvalCase(
    case_id="router-does-everything",
    description="Router should be generally correct.",
    prompt="Handle the request.",
    expected_keywords=["correct"],
)
```

## Workflow and Span Validation

For workflow suites, include machine-readable state in the returned output string. The repository already uses this pattern in `workflow_autopilot_evals.py` by returning fields such as `success=...`, `retry_count=...`, `notes=...`, and `spans=...`.

When validating reasoning-path instrumentation, capture span names from the workflow under test and serialize them into the deterministic output. Then assert them with `keywords` or `regex`. This keeps the fixture and hosted paths compatible while still exercising real tracing hooks in live mode.

## Hosted Dataset Pattern

Use typed dataclasses for dataset I/O.

```python
@dataclass
class MyInput:
    prompt: str
    case_id: str


@dataclass
class MyOutput:
    text: str
```

Prefer the shared `HostedTextScorer` when the hosted evaluator only needs the output text plus metadata.

## Registration Checklist

When adding a new suite, update all of the following.

1. Export the suite from `src/mem_graph/evals/suites/__init__.py`.
2. Register the binding, hosted pusher, and hosted runner in `src/mem_graph/evals/__init__.py`.
3. Add or extend tests for fixture binding, dataset construction, and evaluator behavior.
4. If the suite uses new metadata conventions, add helper validation rather than raw dict access.

## Verification Commands

Use the narrowest relevant checks first.

```bash
python -m pytest tests/test_evals.py -q
python -m pytest tests/test_additional_agent_evals.py tests/test_workflow_evals.py tests/test_skill_evals.py -q
python -m ruff check src tests
python -m mypy .
```

For broader regression coverage across the shared schema and workflow surface, the implementation handoff for Tasks 035 and 036 also ran a combined slice covering agent, workflow, and eval regressions.
