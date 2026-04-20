# Models README

## Current Structure

| File | Lines | Role | Key Dependencies |
|------|-------|------|------------------|
| `memory.py` | 101 | MemoryModel, NoteModel, MemoryKind, MemoryScope | pydantic |
| `project.py` | 94 | ProjectModel, BackendModel, ProjectStatus, BackendLanguage | pydantic |
| `conversation.py` | 77 | ConversationMessage, SessionCaptureResult, MemoryRecallResult, AnnotateResult | pydantic |
| `work.py` | 206 | TaskModel, DecisionModel, ViolationModel + enums | pydantic |
| `task.py` | 125 | BackgroundTaskStatus, TaskProgress, TaskResult, Task (queue) | pydantic, ids, agent_outputs |
| `code.py` | 76 | CodeSymbolModel, TagModel, SymbolKind | pydantic |
| `audit.py` | 249 | AuditRule, AuditFinding, FileAuditResult, AuditStats, AuditReport, Severity, FindingCategory | pydantic |
| `evals.py` | 299 | EvalCase, EvalSuite, EvalSuiteResult, EvalReport, SuiteBinding, etc. | pydantic, agent_outputs |
| `agent_outputs.py` | 711 | RouterDecision, DecisionReview, DecompositionReport, FixerReport, MapReport, ValidationReport, SentryReport, OrchestratorReport, aggregates, batch types | pydantic, config, audit |
| `schema_contracts.py` | 159 | Validation helpers for schema field quality | pydantic |
| `__init__.py` | 61 | Re-exports from agent_outputs only | agent_outputs |

## Dependency Analysis

### The primary refactor target: agent_outputs.py (711 lines)
This file contains structured output models for 7+ different agents:
1. **Router**: RouterDecision, RouterSubTask, WorkflowPlan, WorkflowStagePlan, BatchFileContent
2. **Decision reviewer**: DecisionReview, DriftStatus, ReviewReport
3. **Task decomposer**: Task (agent), DecompositionReport, TaskPhase labels
4. **Fixer**: FixerReport, FilePatch
5. **Mapper**: MapReport, FeatureLocation, FileRelationship
6. **Validator**: ValidationReport, ValidationStatus, ValidationViolation
7. **Sentry**: SentryReport, TestCaseProposal
8. **Orchestrator**: OrchestratorReport, BatchResult, SubagentBatchOutput, AggregateReport + 4 aggregate types

These agent output models have **no cross-dependencies between agent families** — they only share base types (JSONValue) and some type aliases. They can be cleanly split.

### Graph node mirrors (3 files)
- `memory.py` — mirrors Memory/Note graph nodes
- `project.py` — mirrors Project/Backend graph nodes
- `work.py` — mirrors Task/Decision/Violation graph nodes
- `conversation.py` — mirrors Conversation/Message graph nodes (tool I/O models)
- `code.py` — mirrors CodeSymbol/Tag graph nodes

These all mirror the Ladybug graph schema and are used for typed I/O in MCP tools and graph services.

### Infrastructure models (2 files)
- `task.py` — in-memory queue task models (different from graph-node `TaskModel` in work.py)
- `evals.py` — eval framework models (EvalCase, EvalSuite, EvalReport, etc.)

### Meta/validation (1 file)
- `schema_contracts.py` — contract validation that checks other model modules

## Refactor Suggestion

### Primary: Split agent_outputs.py by agent family
This is the single highest-value refactor. Split the 711-line file into per-agent output modules:

- **outputs/router.py**: RouterDecision, RouterSubTask, WorkflowPlan, WorkflowStagePlan, BatchFileContent, RouterIntent, WorkflowMode, AskUserPolicy
- **outputs/review.py**: DecisionReview, DriftStatus, ReviewReport
- **outputs/decomposition.py**: Task (agent), DecompositionReport, TaskPhase, TaskPriorityLabel, TaskComplexity
- **outputs/fixer.py**: FixerReport, FilePatch
- **outputs/mapping.py**: MapReport, FeatureLocation, FileRelationship, RelationshipKind
- **outputs/validation.py**: ValidationReport, ValidationStatus, ValidationViolation, ValidationCheck, ValidationSeverity
- **outputs/sentry.py**: SentryReport, TestCaseProposal
- **outputs/orchestration.py**: OrchestratorReport, BatchResult, SubagentBatchOutput, AggregateReport, AuditAggregate, DecisionAggregate, MapAggregate, GenericAggregate, GenericBatchOutput

An `outputs/__init__.py` re-exports everything so existing imports from `mem_graph.models.agent_outputs` continue to work via `mem_graph.models.outputs`.

### Secondary: Group graph node mirrors
- **graph/**: `memory.py`, `project.py`, `work.py`, `conversation.py`, `code.py`

These all mirror Ladybug graph node schemas and serve as typed I/O for the MCP tool surface. Grouping them:
- Makes the graph-schema mirror boundary explicit
- Separates "what the graph stores" from "what agents produce"
- Keeps `task.py` and `evals.py` out — they are infrastructure models, not graph mirrors

### Files staying in root
`__init__.py`, `task.py`, `evals.py`, `schema_contracts.py`

- `task.py` is an in-memory queue model, not a graph node mirror — it belongs with infrastructure
- `evals.py` is the eval framework's data model, not a graph node
- `schema_contracts.py` validates models across modules, so it stays at the root level

### Not recommended
- Grouping `conversation.py` + `work.py` together — conversation is about session capture, work is about task/decision/violation graph nodes; they serve different tools
- Grouping `task.py` + `code.py` together — task.py is a queue infrastructure model, code.py is a graph node mirror
- Keeping `agent_outputs.py` as-is — at 711 lines with 7+ agent families, it violates the single-concern principle and makes it hard to find which model belongs to which agent
