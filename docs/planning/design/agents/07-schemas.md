# 07 — Schemas

## Principle

Schemas are the typed contracts between the Python runtime and the LLM. Every agent's `output_type=` parameter points to a Pydantic `BaseModel`. When the LLM returns a response that fails validation, Pydantic AI automatically feeds the validation error back to the model, triggering a self-correction loop without manual retry logic.

> **Critical:** `Field(description="...")` annotations are not optional decoration — they are the instructions the model reads when deciding how to populate a field. Rich descriptions directly improve output quality and reduce validation failures.

---

## Schema Organisation

Schemas currently live in two locations:

| Location | Role |
|----------|------|
| `src/mem_graph/models/` | Graph-node data models — shapes of data stored in Ladybug DB |
| Inline in agent files (`agents/*/`) | Agent I/O contracts — structured outputs agents produce |

These serve distinct purposes and should remain separated.

---

## `models/` — Graph Node Schemas

These Pydantic models define the shape of data flowing into and out of the Ladybug graph.

### `models/audit.py`

| Model | Fields | Used by |
|-------|--------|---------|
| `AuditRule` | `rule_id`, `category` (enum), `severity` (enum), `description`, `examples: list[str]` | `AuditDependencies.rules`, `factory.py` |
| `AuditFinding` | `rule_id`, `file_path`, `line_start`, `line_end`, `severity`, `category`, `description`, `code_snippet`, `suggested_fix` | Agent output, `report_writer.py` |
| `FileAuditResult` | `file_path`, `findings: list[AuditFinding]`, `skipped: bool`, `skip_reason: str \| None` | `AuditReport.file_results` |
| `AuditStats` | `total_files_analysed`, `total_files_skipped`, `total_findings`, `by_severity: dict`, `by_category: dict`, `blocker_count`, `critical_count` | `AuditReport.stats` |
| `AuditReport` | `package_path`, `summary`, `file_results`, `stats`, `rules_applied`, `partial_failure` | Final agent output, graph persistence |
| `Severity` | enum: `BLOCKER | CRITICAL | HIGH | MEDIUM | LOW | INFO` | `AuditFinding.severity` |
| `FindingCategory` | enum: `BUG | SECURITY | PERFORMANCE | STYLE | DOCS | MISSING_IMPL | OTHER` | `AuditFinding.category` |

### `models/conversation.py`

Shapes for `Conversation` and `Turn` graph nodes. Used by `tools/memory/conversation.py`.

### `models/memory.py`

Shapes for `Session`, `MemoryCapture`, and recall results. Used by `services/memory.py`.

### `models/project.py`

Shapes for `Project`, `ProjectSummary`. Used by `tools/work/projects.py`.

### `models/task.py`

`Task`, `TaskStatus` enum. Used by `tools/work/tasks.py` and `task_agent.py`.

### `models/work.py`

`Decision`, `Violation`, and their status enums. Used by `tools/work/decisions.py` and `tools/work/violations.py`.

### `models/code.py`

`CodeSymbol`, `SymbolKind` enum. Used by `tools/code/parser.py` and the Tree-sitter pipeline.

### `models/evals.py`

Eval framework models (see `08-evals.md`).

---

## Agent I/O Schemas (Inline in Agent Files)

These are the structured outputs that agents produce. They are defined close to the agents that use them, not in `models/`.

| Model | Defined in | Fields |
|-------|------------|--------|
| `BatchFileContent` | `orchestrator_agent.py` | `path`, `content`, `truncated` |
| `BatchResult` | `orchestrator_agent.py` | `batch_index`, `files_processed`, `output`, `failed`, `error` |
| `OrchestratorReport` | `orchestrator_agent.py` | `package_path`, `subagent_name`, `total_files`, `aggregate: dict`, `summary`, `partial_failure` |
| `RouterSubTask` | `router_agent.py` | `index`, `description`, `target_files`, `agent` |
| `WorkflowStagePlan` | `router_agent.py` | `name`, `depends_on`, `model`, `allowed_tools` |
| `WorkflowPlan` | `router_agent.py` | `objective`, `project_id`, `target_files`, `required_stages`, `max_retries`, `ask_user_policy` |
| `RouterDecision` | `router_agent.py` | `tier`, `file_count`, `concurrency`, `solo_mode`, `intent`, `summary`, `sub_tasks`, `workflow_mode`, `workflow_plan` |
| `DriftStatus` | `decision_agent.py` | enum: `HONOURED \| DRIFTED \| SUPERSEDED \| UNVERIFIABLE` |
| `DecisionReview` | `decision_agent.py` | `decision_id`, `status`, `evidence`, `drifted_files`, `recommendation`, `severity` |
| `ReviewReport` | `decision_agent.py` | `project_id`, `reviews`, `summary`, `honoured_count`, `drifted_count` |
| `Task` | `task_agent.py` | `task_id`, `title`, `phase`, `priority`, `primary_file`, `dependencies`, `acceptance_criteria` |
| `DecompositionReport` | `task_agent.py` | `feature_description`, `project_id`, `tasks`, `identified_blockers`, `estimated_complexity` |
| `FilePatch` | `fixer_agent.py` | `file_path`, `original_snippet`, `proposed_snippet`, `violation_ids`, `rationale` |
| `FixerReport` | `fixer_agent.py` | `patches`, `unresolved_violations`, `summary`, `tier_used` |
| `FeatureLocation` | `map_agent.py` | `feature_name`, `primary_file`, `supporting_files`, `consumers`, `description` |
| `FileRelationship` | `map_agent.py` | `source_file`, `target_file`, `relationship_kind`, `symbols` |
| `MapReport` | `map_agent.py` | `package_path`, `features`, `relationships`, `entry_points`, `summary`, `partial_failure` |
| `TestCaseProposal` | `sentry_agent.py` | `file_path`, `test_name`, `failing_assertion`, `rationale` |
| `SentryReport` | `sentry_agent.py` | `test_cases`, `summary`, `framework` |
| `ValidationStatus` | `validation_agent.py` | enum: `APPROVED \| REJECTED` |
| `ValidationViolation` | `validation_agent.py` | `file_path`, `check`, `description`, `severity` |
| `ValidationReport` | `validation_agent.py` | `status`, `violations`, `rationale`, `files_checked` |

---

## Reflection Loop (Validation Feedback)

Pydantic AI automatically re-invokes the model with validation errors when structured output fails to parse. The quality of `Field(description="...")` directly affects how accurately the model self-corrects.

**Good (enables self-correction):**
```python
class AuditFinding(BaseModel):
    line_start: int = Field(
        description="1-indexed line where the finding begins. "
                    "Use the nearest function boundary if exact line is unknown."
    )
    code_snippet: str = Field(
        description="The literal offending lines from the file — not paraphrased."
    )
    suggested_fix: str = Field(
        description="A concrete replacement for the offending code, or an action to take."
    )
```

**Weak (reduces self-correction precision):**
```python
class AuditFinding(BaseModel):
    line_start: int
    code_snippet: str
    suggested_fix: str
```

---

## Improvement Opportunities

No new folders — all changes stay within `models/` (graph nodes) and agent files (I/O schemas).

| Issue | Recommendation |
|-------|---------------|
| Agent I/O schemas are embedded in agent files | Move structured output types to `models/agent_outputs.py` so evals and services can import them without pulling the full agent module |
| `OrchestratorReport.aggregate: dict` is untyped | Type as `AuditAggregate \| MapAggregate \| DecisionAggregate` via discriminated union |
| `BatchResult.output: Any` | Type using the agent-specific output type; callers currently use `hasattr` checks |
| `Task.phase` is a `str` | Should be `Literal["planning", "red", "green", "refactor", "audit"]` to enable validation-driven self-correction |
| `RouterDecision.intent: str` | Should be `Literal["audit", "fix", "map", "refactor", "document", "review"]` to prevent hallucinated intent values |
