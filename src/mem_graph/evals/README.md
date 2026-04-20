# Evals README

## Current Structure

| File | Lines | Role | Key Dependencies |
|------|-------|------|------------------|
| `evaluator.py` | 695 | Eval runner, CLI, hosted dataset orchestration | models/evals, all suite modules, scorers, fixtures, logfire_client |
| `scorers.py` | 184 | Scoring functions (exact, keywords, regex, semantic) + HostedTextScorer | pydantic_evals, models/evals |
| `fixtures.py` | 106 | Fixture loading helpers (repo root, code/graph/violation fixtures) | None |
| `logfire_client.py` | 93 | Logfire hosted dataset API client | logfire, dotenv, fixtures |
| `audit_evals.py` | 227 | Audit agent eval suite + runner | audit_agent, models/evals, fixtures, scorers |
| `validate_evals.py` | 220 | Validation agent eval suite + runner | validation_agent, models/evals, fixtures, scorers |
| `document_evals.py` | 264 | Document agent eval suite + runner | decision_agent, task_agent, models/evals, fixtures, scorers |
| `fix_evals.py` | 224 | Fixer agent eval suite + runner | fixer_agent, models/evals, fixtures, scorers |
| `map_evals.py` | 192 | Map agent eval suite + runner | map_agent, models/evals, fixtures, scorers |
| `suites/chat_evals.py` | 147 | Chat agent eval suite | chat_agent, models/evals, fixtures, scorers, common |
| `suites/orchestrator_evals.py` | 253 | Orchestrator eval suite | orchestrator_agent, models/audit, models/evals, fixtures, scorers, common |
| `suites/router_evals.py` | 248 | Router agent eval suite | router_agent, models/evals, fixtures, scorers, common |
| `suites/rule_injector_evals.py` | 144 | Rule injector eval suite | rule_injector_agent, models/evals, fixtures, scorers, common |
| `suites/sentry_evals.py` | 175 | Sentry agent eval suite | sentry_agent, models/evals, fixtures, scorers, common |
| `suites/skill_evals.py` | 416 | Skill eval suites (python_quality, go_quality, security, typescript_quality) | providers/skills, models/evals, fixtures, scorers, common |
| `suites/triage_evals.py` | 174 | Triage agent eval suite | triage_agent, models/evals, fixtures, scorers, common |
| `suites/workflow_autopilot_evals.py` | 328 | Autopilot workflow eval suite | orchestrator_graph, models/agent_outputs, models/evals, fixtures, scorers, common |
| `suites/workflow_feature_implementation_evals.py` | 167 | Feature implementation workflow eval suite | workflow_graph, models/evals, fixtures, scorers, common |
| `suites/workflow_package_audit_evals.py` | 251 | Package audit workflow eval suite | workflows/runtime, models/evals, fixtures, scorers, common |
| `suites/common.py` | 51 | Shared hosted-text helpers (HostedTextOutput, HostedTextMeta, build_text_meta) | models/evals |

## Structural Problems

### 1. Inconsistent suite location
Five agent suites live at the top level (`audit_evals.py`, `validate_evals.py`, `document_evals.py`, `fix_evals.py`, `map_evals.py`) while ten others live in `suites/`. This makes it unclear where new suites should go and forces `evaluator.py` to import from two different locations.

### 2. evaluator.py does too much (695 lines)
`evaluator.py` combines three distinct responsibilities:
- **Eval runner logic**: `Evaluator` class, `run_case`, `run_suite`, `run_report`
- **CLI entry point**: `main()`, `main_async()`, `_build_parser()`, argument handling
- **Hosted dataset orchestration**: `push_all_datasets`, `run_all_evals`, `run_eval_from_hosted`, `_HOSTED_PUSHERS`, `_HOSTED_RUNNERS`

### 3. No category grouping for suites
All 15 suites sit in a flat list. There are clear categories by agent family:
- **Agent suites**: audit, fix, validate, map, document, chat, router, rule_injector, sentry, triage, orchestrator
- **Skill suites**: python_quality, go_quality, security, typescript_quality
- **Workflow suites**: autopilot, feature_implementation, package_audit

### 4. skill_evals.py is over-stuffed (416 lines)
One file defines four separate EvalSuite instances (python_quality, go_quality, security, typescript_quality) plus their runners and dataset builders. Each skill suite should be its own file.

## Refactor Suggestion

### Primary: Flatten suites/ into evals/ and create category sub-directories

Move all suite files out of `suites/` and into `evals/` category sub-directories. This eliminates the inconsistent split and organizes suites by the kind of system they evaluate:

- **agents/**: Suites that evaluate a single agent's behavior
  - `audit_evals.py` (from top level)
  - `fix_evals.py` (from top level)
  - `validate_evals.py` (from top level)
  - `map_evals.py` (from top level)
  - `document_evals.py` (from top level)
  - `chat_evals.py` (from suites/)
  - `router_evals.py` (from suites/)
  - `rule_injector_evals.py` (from suites/)
  - `sentry_evals.py` (from suites/)
  - `triage_evals.py` (from suites/)
  - `orchestrator_evals.py` (from suites/)

- **skills/**: Suites that evaluate internal skill/audit-rule bundles
  - `python_quality_evals.py` (split from skill_evals.py)
  - `go_quality_evals.py` (split from skill_evals.py)
  - `security_evals.py` (split from skill_evals.py)
  - `typescript_quality_evals.py` (split from skill_evals.py)

- **workflows/**: Suites that evaluate end-to-end workflow runs
  - `autopilot_evals.py` (from suites/workflow_autopilot_evals.py)
  - `feature_implementation_evals.py` (from suites/workflow_feature_implementation_evals.py)
  - `package_audit_evals.py` (from suites/workflow_package_audit_evals.py)

Each category gets an `__init__.py` that re-exports its suites, builders, and runners so `evals/__init__.py` can import from a clean namespace.

### Secondary: Split evaluator.py into focused modules
- **evaluator.py**: `Evaluator` class + `run_case`, `run_suite`, `run_report`, `persist_report_summary`, `render_eval_report`, `write_json_report` (the pure eval runner)
- **cli.py**: `main()`, `main_async()`, `_build_parser()`, `_resolve_mode` (CLI entry point)
- **hosted.py**: `push_all_datasets`, `run_all_evals`, `run_eval_from_hosted`, `_HOSTED_PUSHERS`, `_HOSTED_RUNNERS`, `_resolve_hosted_suites` (hosted dataset orchestration)

This keeps each module under 350 lines with a single responsibility.

### Tertiary: Move logfire_client.py next to hosted orchestration
- **hosted/logfire_client.py**: alongside the hosted orchestration code

`logfire_client.py` is only imported by hosted dataset operations. Moving it next to `hosted.py` (or into a `hosted/` sub-package if it grows) keeps the Logfire dependency boundary explicit.

### Move common.py to evals/ root
`suites/common.py` → `common.py` in the evals/ root. The `HostedTextOutput`, `HostedTextMeta`, `build_text_meta`, and `expected_text` helpers are used across all three categories, so they should live at the infrastructure level, not inside a category.

### Directory layout after refactor
```
evals/
  __init__.py
  evaluator.py          # Pure eval runner
  cli.py                # CLI entry point
  scorers.py            # Scoring functions
  fixtures.py           # Fixture loading
  common.py             # Shared suite helpers (moved from suites/)
  hosted/
    __init__.py
    hosted.py           # Hosted dataset orchestration (split from evaluator.py)
    logfire_client.py   # Moved from evals/ root
  agents/
    __init__.py
    audit_evals.py
    chat_evals.py
    document_evals.py
    fix_evals.py
    map_evals.py
    orchestrator_evals.py
    router_evals.py
    rule_injector_evals.py
    sentry_evals.py
    triage_evals.py
    validate_evals.py
  skills/
    __init__.py
    python_quality_evals.py
    go_quality_evals.py
    security_evals.py
    typescript_quality_evals.py
  workflows/
    __init__.py
    autopilot_evals.py
    feature_implementation_evals.py
    package_audit_evals.py
```

### Import path changes
After refactor, imports shift from:
```python
from .suites import run_chat_eval, CHAT_EVAL_SUITE
from .audit_evals import AUDIT_EVAL_SUITE, build_audit_binding
```
To:
```python
from .agents.chat_evals import run_chat_eval, CHAT_EVAL_SUITE
from .agents.audit_evals import AUDIT_EVAL_SUITE, build_audit_binding
```

The `evals/__init__.py` re-exports maintain the public API so downstream code importing `from mem_graph.evals import CHAT_EVAL_SUITE` still works.

### Not recommended
- Keeping `suites/` as a sub-directory — the flat structure doesn't scale and the `suites/` vs top-level split is the current pain point
- Creating per-agent sub-directories (e.g., `agents/chat/`) — each suite is a single file; one level of category grouping is sufficient
- Keeping `skill_evals.py` as a single 416-line file with four suites — each skill has its own EvalSuite, runner, and dataset builder, making them natural single-file modules
