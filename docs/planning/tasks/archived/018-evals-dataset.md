Based on what I can see in your existing files, here's the exact task list:

---

# Task List: Wire Up Hosted Datasets & Eval Runners

## 1. validate_evals.py — fix `ValidateInput` first
- [x] Add `case_id: str` field to `ValidateInput` dataclass
- [x] In `build_validate_dataset()`, pass `case_id=case.case_id` into each `ValidateInput`

## 2. Add `run_*_eval()` to each eval file
- [x] Add `run_audit_eval()` to `audit_evals.py`
- [x] Add `run_fix_eval()` to `fix_evals.py`
- [x] Add `run_map_eval()` to `map_evals.py`
- [x] Add `run_document_eval()` to `document_evals.py`
- [x] Add `run_validate_eval()` to `validate_evals.py`

The exact code for each is in the guide from the previous message.

## 3. Update evaluator.py
- [x] Add imports for all five `push_*_dataset` functions
- [x] Add imports for all five `run_*_eval` functions
- [x] Add `push_all_datasets()` function
- [x] Add `run_all_evals()` async function with `logfire.configure()` and `logfire.instrument_pydantic_ai()` at the top
- [x] Add `if __name__ == "__main__"` block with `--push` flag handling

## 4. Verify env var
- [x] Confirm `LOGFIRE_DATASETS_API_KEY`, `LOGFIRE_DATASETS_TOKEN`, `LOGFIRE_API_KEY`, or `LOGFIRE_TOKEN` is set in your `.env` — `logfire_client.py` already handles all four fallbacks so any one of them works

## 5. Push and verify
- [x] Run `python -m mem_graph.evals.evaluator --push`
- [x] Confirm all five datasets appear in Logfire UI under **Evals**
- [x] Run `python -m mem_graph.evals.evaluator` to trigger a live eval run
- [x] Confirm experiment results appear in each dataset's **Experiments** tab

## CONTEXT

Your evals are already extremely well structured — you've actually already built most of the dataset pattern yourself. The `build_*_dataset()` and `push_*_dataset()` functions are already in every eval file. What's missing is just the eval runner that fetches them back from Logfire and runs them, plus a single entry point to push/run everything. Here's the guide:

---

# Dataset Guide for mem_graph Evals

## What you already have (don't touch)

Every `*_evals.py` already has:
- `build_*_dataset()` — builds the local `pydantic_evals.Dataset`
- `push_*_dataset()` — pushes it to Logfire hosted storage
- `HostedTextScorer` attached to every `Case`
- `logfire_client.py` with `get_client()` / `get_async_client()`

The pattern is consistent across all five eval files. Nothing there needs changing.

---

## What's missing — the eval runner

Add a runner function to each `*_evals.py` that fetches the hosted dataset back and runs it against the live agent. The pattern is identical across all files, just with different types and task functions.

### audit_evals.py — add this

```python
async def run_audit_eval() -> None:
    from .logfire_client import get_client

    async def audit_task(inputs: AuditInput) -> AuditOutput:
        deps = AuditDependencies(
            package_path="eval-fixture",
            file_extension=".py",
            extra_file_context=_fixture_context(inputs.file_path, inputs.file_content),
        )
        result = await audit_agent.run(inputs.prompt, deps=deps)
        return AuditOutput(text=_render_audit_report(result.output))

    with get_client() as client:
        dataset: Dataset[AuditInput, AuditOutput, AuditMeta] = client.get_dataset(
            "audit-golden-set",
            input_type=AuditInput,
            output_type=AuditOutput,
            metadata_type=AuditMeta,
        )
    report = await dataset.evaluate(audit_task)
    report.print()
```

### fix_evals.py — add this

```python
async def run_fix_eval() -> None:
    from .logfire_client import get_client

    async def fix_task(inputs: FixInput) -> FixOutput:
        violations = list(_VIOLATION_FIXTURES["fix"][inputs.file_path.split("/")[-1].replace(".py", "")])
        deps = FixerDependencies(
            violations=violations,
            file_contents={inputs.file_path: inputs.file_content},
            tier=ModelTier.STANDARD.value,
            project_id="eval-fixture",
        )
        result = await fixer_agent.run(inputs.prompt, deps=deps)
        return FixOutput(text=_render_fix_report(result.output))

    with get_client() as client:
        dataset: Dataset[FixInput, FixOutput, FixMeta] = client.get_dataset(
            "fix-golden-set",
            input_type=FixInput,
            output_type=FixOutput,
            metadata_type=FixMeta,
        )
    report = await dataset.evaluate(fix_task)
    report.print()
```

### map_evals.py — add this

```python
async def run_map_eval() -> None:
    from .logfire_client import get_client

    async def map_task(inputs: MapInput) -> MapOutput:
        deps = MapDependencies(
            package_path="eval-fixture",
            known_features=inputs.known_features,
            extra_file_context=format_preloaded_files(inputs.files),
        )
        result = await map_agent.run(inputs.prompt, deps=deps)
        return MapOutput(text=_render_map_report(result.output))

    with get_client() as client:
        dataset: Dataset[MapInput, MapOutput, MapMeta] = client.get_dataset(
            "map-golden-set",
            input_type=MapInput,
            output_type=MapOutput,
            metadata_type=MapMeta,
        )
    report = await dataset.evaluate(map_task)
    report.print()
```

### document_evals.py — add this

```python
async def run_document_eval() -> None:
    from .logfire_client import get_client

    async def document_task(inputs: DocumentInput) -> DocumentOutput:
        if inputs.workflow == "task":
            deps = TaskDependencies(
                feature_description=_GRAPH_FIXTURES["feature_description"],
                project_id=inputs.project_id,
                codebase_map=inputs.files,
                open_violations=list(_GRAPH_FIXTURES["open_violations"]),
                prior_decisions=inputs.decisions,
            )
            result = await task_agent.run(inputs.prompt, deps=deps)
            return DocumentOutput(text=_render_task_report(result.output))

        deps = DecisionDependencies(
            project_id=inputs.project_id,
            package_path="eval-fixture",
            decisions=inputs.decisions,
            extra_file_context=format_preloaded_files(inputs.files),
        )
        result = await decision_agent.run(inputs.prompt, deps=deps)
        return DocumentOutput(text=_render_decision_report(result.output))

    with get_client() as client:
        dataset: Dataset[DocumentInput, DocumentOutput, DocumentMeta] = client.get_dataset(
            "document-golden-set",
            input_type=DocumentInput,
            output_type=DocumentOutput,
            metadata_type=DocumentMeta,
        )
    report = await dataset.evaluate(document_task)
    report.print()
```

### validate_evals.py — add this

```python
async def run_validate_eval() -> None:
    from .logfire_client import get_client

    async def validate_task(inputs: ValidateInput) -> ValidateOutput:
        deps = ValidationDependencies(
            language=inputs.language,
            original_violations=list(
                _VIOLATION_FIXTURES["validate"][inputs.file_path.split("/")[-1].replace(".py", "")]
            ),
            proposed_patches={inputs.file_path: inputs.proposed_file_content},
            original_file_contents={inputs.file_path: inputs.original_file_content},
        )
        result = await validation_agent.run(inputs.prompt, deps=deps)
        return ValidateOutput(text=result.output.status.value)

    with get_client() as client:
        dataset: Dataset[ValidateInput, ValidateOutput, ValidateMeta] = client.get_dataset(
            "validate-golden-set",
            input_type=ValidateInput,
            output_type=ValidateOutput,
            metadata_type=ValidateMeta,
        )
    report = await dataset.evaluate(validate_task)
    report.print()
```

---

## Wire up evaluator.py

Your `evaluator.py` should get two new entry points — one to push all datasets, one to run all evals:

```python
# add to evaluator.py
import asyncio
import logfire

from .audit_evals import push_audit_dataset, run_audit_eval
from .fix_evals import push_fix_dataset, run_fix_eval
from .map_evals import push_map_dataset, run_map_eval
from .document_evals import push_document_dataset, run_document_eval
from .validate_evals import push_validate_dataset, run_validate_eval


def push_all_datasets() -> None:
    """Push all golden sets to Logfire hosted storage. Safe to re-run."""
    push_audit_dataset()
    push_fix_dataset()
    push_map_dataset()
    push_document_dataset()
    push_validate_dataset()


async def run_all_evals() -> None:
    """Fetch all hosted datasets and run evals against live agents."""
    logfire.configure()
    logfire.instrument_pydantic_ai()

    await run_audit_eval()
    await run_fix_eval()
    await run_map_eval()
    await run_document_eval()
    await run_validate_eval()


if __name__ == "__main__":
    import sys
    if "--push" in sys.argv:
        push_all_datasets()
    else:
        asyncio.run(run_all_evals())
```

Then from the terminal:

```bash
# first time, or when cases change
python -m mem_graph.evals.evaluator --push

# run evals against live agents
python -m mem_graph.evals.evaluator
```

---

## One important note on `validate_evals.py`

The violation lookup in `run_validate_eval` uses the file path to key into `_VIOLATION_FIXTURES`. That's fragile since `inputs.file_path` is `fixtures/fetch_user.py` and the fixture key is `validate-approved`. You may want to add `case_id` to `ValidateInput` so the task function can look up violations by case ID directly, the same way `AuditMeta.case_id` already exists on the metadata side:

```python
@dataclass
class ValidateInput:
    prompt: str
    original_file_content: str
    proposed_file_content: str
    file_path: str
    case_id: str        # ← add this
    language: str = "python"
```

Then in `build_validate_dataset()` pass `case_id=case.case_id` and use `inputs.case_id` in the task function for the violation lookup.
