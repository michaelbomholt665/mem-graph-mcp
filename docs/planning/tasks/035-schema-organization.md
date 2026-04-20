# Task 035: Schema Organization — Typed Contracts and Validation-Driven Self-Correction

**Status:** Planning
**Priority:** Medium
**Blocked by:** Task 029 (Base Agent Architecture), Task 033 (Tool System)
**Blocks:** Task 036 (Evaluations)
**Complexity:** MEDIUM

## Problem Statement

Schemas are defined in two places: `models/` (graph node shapes) and inline in agent files (agent I/O contracts). There's no clear separation of concerns, and some fields use weak types (`dict`, `Any`, `str` enums) that don't enable validation-driven self-correction. Field descriptions are incomplete, losing calibration signals the model uses during output refinement.

The goal is to:
1. **Separate concerns:** Graph node schemas in `models/`, agent I/O schemas in a dedicated module.
2. **Use discriminated unions:** Type variants explicitly (e.g., `AuditAggregate | MapAggregate` instead of `dict`).
3. **Use Literal types:** Constrain enum fields (e.g., `Literal["planning", "red", "green", "refactor", "audit"]` for Task.phase).
4. **Enrich Field descriptions:** Every field has a clear, detailed description for validation self-correction.
5. **Validate schema compliance:** Add linting to catch weak types in new schemas.

## Non-Goals

- Redesigning the Pydantic AI validation mechanism.
- Adding backward compatibility shims.
- Building a schema editor UI.

## Current State

### Schema Organization (Fragmented)

**`models/` — Graph Node Schemas (9 files):**
- `audit.py` — AuditRule, AuditFinding, FileAuditResult, AuditStats, AuditReport, Severity, FindingCategory
- `conversation.py` — Conversation, Turn
- `memory.py` — Session, MemoryCapture, recall results
- `project.py` — Project, ProjectSummary
- `task.py` — Task, TaskStatus
- `work.py` — Decision, Violation, status enums
- `code.py` — CodeSymbol, SymbolKind
- `evals.py` — Eval framework models
- `__init__.py` — Exports

**Agent I/O Schemas (Inline in Agent Files):**
- `orchestrator_agent.py` — BatchFileContent, BatchResult, OrchestratorReport
- `router_agent.py` — RouterSubTask, WorkflowStagePlan, WorkflowPlan, RouterDecision
- `decision_agent.py` — DriftStatus, DecisionReview, ReviewReport
- `task_agent.py` — Task, DecompositionReport
- `fixer_agent.py` — FilePatch, FixerReport
- `map_agent.py` — FeatureLocation, FileRelationship, MapReport
- `sentry_agent.py` — TestCaseProposal, SentryReport
- `validation_agent.py` — ValidationStatus, ValidationViolation, ValidationReport

### Weak Type Issues

| Field | Type | Issue | Fix |
|-------|------|-------|-----|
| `OrchestratorReport.aggregate` | `dict` | Untyped; can contain anything | Discriminated union: `AuditAggregate \| MapAggregate \| DecisionAggregate` |
| `BatchResult.output` | `Any` | Untyped; requires runtime `hasattr` checks | Use agent-specific output type |
| `Task.phase` | `str` | No validation | `Literal["planning", "red", "green", "refactor", "audit"]` |
| `RouterDecision.intent` | `str` | Can be misspelled/hallucinated | `Literal["audit", "fix", "map", "refactor", "document", "review"]` |
| `ValidationStatus` | enum | Minimal | Enum is fine (APPROVED \| REJECTED) |

### Missing Field Descriptions

**Example — `AuditFinding` (weak):**
```python
class AuditFinding(BaseModel):
    line_start: int  # NO DESCRIPTION
    code_snippet: str  # NO DESCRIPTION
    suggested_fix: str  # NO DESCRIPTION
```

**Should be:**
```python
class AuditFinding(BaseModel):
    line_start: int = Field(
        description="1-indexed line where the finding begins. "
                    "Use the nearest function boundary if exact line is unknown."
    )
    code_snippet: str = Field(
        description="The literal offending lines from the file — not paraphrased or summarized."
    )
    suggested_fix: str = Field(
        description="A concrete replacement for the offending code, or an action to take (e.g. 'remove this line')."
    )
```

## Target Files

### New Files

```
src/mem_graph/models/agent_outputs.py
  - All agent I/O schemas (formerly inline)
  - Organized by agent group

src/mem_graph/schemas.py (Optional)
  - Re-exports from models/ for convenience

docs/planning/design/schemas/validation-self-correction-guide.md
  - Explain Pydantic AI validation loop
  - Show how Field descriptions enable self-correction
  - Provide examples of good vs weak descriptions
```

### Modifications

```
src/mem_graph/models/audit.py
  - Enrich all Field descriptions
  - Add examples to enum variants

src/mem_graph/models/work.py
  - Enrich all Field descriptions
  - Add examples

src/mem_graph/models/task.py
  - Add @dataclass Task fields (if not already)
  - Add Field descriptions
  - Enrich Task.phase to Literal enum

src/mem_graph/models/__init__.py
  - Export all schemas for external use

src/mem_graph/agents/orchestrator_agent.py
  - Remove BatchFileContent, BatchResult, OrchestratorReport
  - Import from models/agent_outputs.py
  - Update OrchestratorReport.aggregate to discriminated union

src/mem_graph/agents/router_agent.py
  - Remove RouterSubTask, WorkflowStagePlan, WorkflowPlan, RouterDecision
  - Import from models/agent_outputs.py
  - Update RouterDecision.intent to Literal enum

src/mem_graph/agents/document/decision_agent.py
  - Remove DriftStatus, DecisionReview, ReviewReport
  - Import from models/agent_outputs.py

src/mem_graph/agents/document/task_agent.py
  - Remove Task, DecompositionReport (or keep Task if used elsewhere)
  - Import from models/agent_outputs.py

src/mem_graph/agents/fix/fixer_agent.py
  - Remove FilePatch, FixerReport
  - Import from models/agent_outputs.py

src/mem_graph/agents/map/map_agent.py
  - Remove FeatureLocation, FileRelationship, MapReport
  - Import from models/agent_outputs.py

src/mem_graph/agents/validate/sentry_agent.py
  - Remove TestCaseProposal, SentryReport
  - Import from models/agent_outputs.py

src/mem_graph/agents/validate/validation_agent.py
  - Remove ValidationStatus, ValidationViolation, ValidationReport
  - Import from models/agent_outputs.py
```

## Implementation Phases

### Phase 1: Create `models/agent_outputs.py` (Sprint 1)

**Organize by agent group:**
- [ ] Create file structure:
  ```python
  """Agent I/O Schemas — Structured outputs agents produce.

  These are defined separately from graph-node schemas (models/) because:
  1. Agent outputs are Pydantic AI validation contracts, not persistent DB shapes.
  2. Evals and services may reference these without importing full agent modules.
  3. Separation enables schema versioning independent of graph schema.
  """

  from dataclasses import dataclass
  from typing import Literal
  from pydantic import BaseModel, Field

  # =============================================================================
  # Orchestration Layer
  # =============================================================================

  @dataclass
  class BatchFileContent:
      """A batch of file contents to process."""
      path: str = Field(description="File path")
      content: str = Field(description="File content (may be truncated)")
      truncated: bool = Field(description="True if content was truncated to byte limit")

  @dataclass
  class BatchResult:
      """Result of processing one batch."""
      batch_index: int = Field(description="Index of this batch in the sequence")
      files_processed: int = Field(description="Number of files in this batch")
      output: dict = Field(description="Agent output for this batch (schema varies by agent)")
      failed: bool = Field(description="True if processing failed")
      error: str | None = Field(description="Error message if failed")

  class OrchestratorReport(BaseModel):
      """Report from orchestrator_agent."""
      package_path: str = Field(description="Path to analyzed package")
      subagent_name: str = Field(description="Name of sub-agent that ran (e.g. 'audit', 'map')")
      total_files: int = Field(description="Total files processed")
      aggregate: AuditAggregate | MapAggregate | DecisionAggregate = Field(
          description="Aggregated results; type varies by subagent_name"
      )
      summary: str = Field(description="High-level summary of findings")
      partial_failure: bool = Field(description="True if any files failed processing")

  # =============================================================================
  # Router Layer
  # =============================================================================

  @dataclass
  class RouterSubTask:
      """A sub-task for orchestrated execution."""
      index: int = Field(description="Task index in sequence")
      description: str = Field(description="What this task should accomplish")
      target_files: list[str] = Field(description="Files relevant to this task")
      agent: str = Field(description="Agent to route this task to")

  @dataclass
  class WorkflowStagePlan:
      """One stage in a workflow."""
      name: str = Field(description="Stage name (e.g. 'sentry', 'logic_draft')")
      depends_on: str | None = Field(description="Previous stage, if any")
      model: str = Field(description="Model tier to use (MICRO, STANDARD, etc)")
      allowed_tools: list[str] = Field(description="Tools this stage can call")

  @dataclass
  class WorkflowPlan:
      """Complete workflow plan from router_agent."""
      objective: str = Field(description="Overall goal of the workflow")
      project_id: str = Field(description="Target project ID")
      target_files: list[str] = Field(description="Files in scope for this workflow")
      required_stages: list[WorkflowStagePlan] = Field(description="Ordered stages")
      max_retries: int = Field(description="Max retries before giving up")
      ask_user_policy: Literal["never", "on_error", "always"] = Field(
          description="When to ask user for approval"
      )

  class RouterDecision(BaseModel):
      """Decision from router_agent."""
      tier: Literal["MICRO", "STANDARD", "PREMIUM", "TURBO", "AUTOPILOT"] = Field(
          description="Selected model tier for this task"
      )
      file_count: int = Field(description="Number of files in scope")
      concurrency: int = Field(description="Parallelism factor (1..N)")
      solo_mode: bool = Field(description="True if single-agent mode, False if orchestrated")
      intent: Literal["audit", "fix", "map", "refactor", "document", "review"] = Field(
          description="Classified intent of the request"
      )
      summary: str = Field(description="Routing rationale")
      sub_tasks: list[RouterSubTask] = Field(description="Tasks if orchestrated")
      workflow_mode: Literal["solo", "subagent_workflow"] = Field(
          description="Execution mode"
      )
      workflow_plan: WorkflowPlan | None = Field(
          description="Complete plan if workflow_mode=='subagent_workflow'"
      )

  # =============================================================================
  # Document Layer
  # =============================================================================

  class DriftStatus(str, Enum):
      """Status of a decision against current codebase."""
      HONOURED = "honoured"
      DRIFTED = "drifted"
      SUPERSEDED = "superseded"
      UNVERIFIABLE = "unverifiable"

  @dataclass
  class DecisionReview:
      """Review of one decision."""
      decision_id: str = Field(description="ID of decision being reviewed")
      status: DriftStatus = Field(description="Whether decision is still honoured")
      evidence: list[str] = Field(description="Specific code locations supporting this status")
      drifted_files: list[str] = Field(description="Files that diverged from decision")
      recommendation: str = Field(description="Action to take (e.g. 'update decision', 'implement it')")
      severity: Literal["low", "medium", "high", "critical"] = Field(
          description="Impact of drift"
      )

  class ReviewReport(BaseModel):
      """Report from decision_agent."""
      project_id: str
      reviews: list[DecisionReview] = Field(description="Reviews for each decision")
      summary: str
      honoured_count: int
      drifted_count: int

  @dataclass
  class Task:
      """One task in a feature implementation."""
      task_id: str = Field(description="Unique task ID")
      title: str = Field(description="Task title")
      phase: Literal["planning", "red", "green", "refactor", "audit"] = Field(
          description="TDD phase this task addresses"
      )
      priority: Literal["low", "medium", "high", "blocker"] = Field(
          description="Task priority"
      )
      primary_file: str = Field(description="Main file to modify")
      dependencies: list[str] = Field(description="Task IDs this depends on")
      acceptance_criteria: list[str] = Field(description="Criteria for 'done'")

  class DecompositionReport(BaseModel):
      """Report from task_agent."""
      feature_description: str
      project_id: str
      tasks: list[Task]
      identified_blockers: list[str]
      estimated_complexity: Literal["low", "medium", "high", "very_high"]

  # =============================================================================
  # Fix Layer
  # =============================================================================

  @dataclass
  class FilePatch:
      """Proposed fix for violations in one file."""
      file_path: str = Field(description="Path to file")
      original_snippet: str = Field(description="Original code (literal from file)")
      proposed_snippet: str = Field(description="Proposed replacement")
      violation_ids: list[str] = Field(description="IDs of violations this patch addresses")
      rationale: str = Field(description="Why this fix is correct")

  class FixerReport(BaseModel):
      """Report from fixer_agent."""
      patches: list[FilePatch]
      unresolved_violations: list[str] = Field(
          description="Violation IDs that couldn't be fixed (e.g. false positives)"
      )
      summary: str
      tier_used: str = Field(description="Model tier that was used")

  # =============================================================================
  # Map Layer
  # =============================================================================

  @dataclass
  class FeatureLocation:
      """Location of a feature in the codebase."""
      feature_name: str
      primary_file: str
      supporting_files: list[str]
      consumers: list[str] = Field(description="Other features that use this one")
      description: str

  @dataclass
  class FileRelationship:
      """Relationship between two files."""
      source_file: str
      target_file: str
      relationship_kind: Literal["imports", "extends", "calls", "references"] = Field(
          description="Type of relationship"
      )
      symbols: list[str] = Field(description="Symbols involved in relationship")

  class MapReport(BaseModel):
      """Report from map_agent."""
      package_path: str
      features: list[FeatureLocation]
      relationships: list[FileRelationship]
      entry_points: list[str] = Field(description="Public API entry points")
      summary: str
      partial_failure: bool

  # =============================================================================
  # Validate Layer
  # =============================================================================

  @dataclass
  class TestCaseProposal:
      """Proposed failing test case."""
      file_path: str = Field(description="Where to place this test")
      test_name: str = Field(description="Test function name")
      failing_assertion: str = Field(
          description="The assertion that should fail before feature is implemented"
      )
      rationale: str = Field(description="Why this test matters")

  class SentryReport(BaseModel):
      """Report from sentry_agent."""
      test_cases: list[TestCaseProposal]
      summary: str
      framework: str = Field(description="Detected test framework (pytest, unittest, etc)")

  class ValidationStatus(str, Enum):
      """Result of validation check."""
      APPROVED = "approved"
      REJECTED = "rejected"

  @dataclass
  class ValidationViolation:
      """A validation failure."""
      file_path: str
      check: str = Field(description="Check that failed (e.g. 'no_new_violations')")
      description: str
      severity: Literal["info", "warning", "error"] = Field(description="Severity of check")

  class ValidationReport(BaseModel):
      """Report from validation_agent."""
      status: ValidationStatus
      violations: list[ValidationViolation]
      rationale: str = Field(description="Why validation passed or failed")
      files_checked: int
  ```

### Phase 2: Enrich Existing Schema Field Descriptions (Sprint 1–2)

**For each model in `models/`:**
- [ ] `audit.py`:
  ```python
  class AuditFinding(BaseModel):
      rule_id: str = Field(
          description="ID of the rule that was violated (e.g. 'PY001', 'SEC-SQL-001'). "
                      "Must match a rule in the audit skill."
      )
      file_path: str = Field(
          description="Relative path to the file where the violation was found."
      )
      line_start: int = Field(
          description="1-indexed line number where the violation begins. "
                      "Use the nearest function/class boundary if exact line is unknown."
      )
      line_end: int = Field(
          description="1-indexed line number where the violation ends (inclusive). "
                      "May equal line_start for single-line violations."
      )
      severity: Severity = Field(
          description="How severe this violation is (BLOCKER > CRITICAL > HIGH > MEDIUM > LOW > INFO). "
                      "BLOCKER: prevents app from running. CRITICAL: exploitable or data-losing."
      )
      category: FindingCategory = Field(
          description="Category of violation (BUG, SECURITY, PERFORMANCE, STYLE, DOCS, MISSING_IMPL, OTHER)."
      )
      description: str = Field(
          description="Human-readable explanation of what was found and why it's wrong. "
                      "Assume the reader is not expert in the relevant domain."
      )
      code_snippet: str = Field(
          description="The literal offending code from the file — not paraphrased or summarized. "
                      "Should match lines [line_start, line_end] from the file."
      )
      suggested_fix: str = Field(
          description="A concrete replacement for the offending code, or an action to take "
                      "(e.g. 'remove this line', 'call function X before Y'). "
                      "Must be implementable without the agent's further guidance."
      )
  ```

- [ ] `work.py` — add field descriptions for Decision, Violation.
- [ ] `task.py` — add field descriptions for Task; ensure phase is Literal.

### Phase 3: Create Discriminated Union for OrchestratorReport (Sprint 2)

**Update `orchestrator_agent.py`:**
- [ ] Define aggregate union types:
  ```python
  # In models/agent_outputs.py

  @dataclass
  class AuditAggregate:
      """Aggregated audit findings."""
      total_findings: int
      by_severity: dict[str, int]
      by_file: dict[str, int]

  @dataclass
  class MapAggregate:
      """Aggregated codebase map."""
      feature_count: int
      relationship_count: int
      entry_points: list[str]

  @dataclass
  class DecisionAggregate:
      """Aggregated decision review."""
      honoured_count: int
      drifted_count: int
      severity_distribution: dict[str, int]

  class OrchestratorReport(BaseModel):
      aggregate: AuditAggregate | MapAggregate | DecisionAggregate = Field(
          discriminator="__typename__",  # or use Union discriminator
          description="Aggregated results from sub-agent; type depends on subagent_name"
      )
  ```

- [ ] Update agent code:
  ```python
  # Before:
  report = OrchestratorReport(
      aggregate={
          "total_findings": len(findings),
          "by_severity": {...},
      }
  )

  # After:
  report = OrchestratorReport(
      aggregate=AuditAggregate(
          total_findings=len(findings),
          by_severity={...},
      )
  )
  ```

### Phase 4: Add Schema Validation Linter (Sprint 2)

**Create `scripts/validate_schemas.py`:**
- [ ] Check for weak types:
  ```python
  def validate_schemas():
      """Check that schemas follow best practices."""

      issues = []

      for model_file in glob("src/mem_graph/models/**/*.py"):
          tree = ast.parse(read_file(model_file))

          for node in ast.walk(tree):
              if isinstance(node, ast.ClassDef):
                  # Check: All fields have Field(..., description="...")
                  # Check: No `dict`, `Any`, untyped string enums
                  # Check: Enum fields use Literal if small (<5 variants)

      if issues:
          raise RuntimeError(f"Schema validation errors:\n" + "\n".join(issues))
  ```

- [ ] Run on CI.

### Phase 5: Documentation (Sprint 3)

- [ ] Create `docs/planning/design/schemas/validation-self-correction-guide.md`:
  ```markdown
  # Validation-Driven Self-Correction

  ## How Pydantic AI Uses Field Descriptions

  When an agent's output fails validation, Pydantic AI re-invokes the model with:
  1. The original prompt
  2. The validation error message
  3. The model's previous response (for context)

  The model then attempts to fix the error. Quality of `Field(description="...")` directly affects success rate.

  ## Good Description (Enables Self-Correction)

  ```python
  line_start: int = Field(
      description="1-indexed line where the violation begins. "
                  "Use the nearest function boundary if exact line is unknown."
  )
  ```

  Model learns:
  - Line numbers are 1-indexed (not 0-indexed)
  - Can use fuzzy boundaries for complex cases
  - Must be an integer

  ## Weak Description (Reduces Success Rate)

  ```python
  line_start: int  # No description; model has to guess
  ```

  ## Testing Self-Correction

  ```bash
  # Run validation evals to measure self-correction success rate
  MEM_GRAPH_LOGFIRE_ENABLED=false \
    uv run pytest tests/schemas/test_validation_correction.py -q
  ```
  ```

## Acceptance Criteria

1. **Agent I/O schemas consolidated:** All moved to `models/agent_outputs.py`.
2. **Weak types eliminated:** All `dict`, `Any` fields typed explicitly; enums converted to Literal.
3. **Field descriptions enriched:** Every field in every schema has a clear, detailed description.
4. **Discriminated unions used:** `OrchestratorReport.aggregate`, `RouterDecision.intent`, etc. are typed properly.
5. **No imports break:** All imports from agent files to models work unchanged.
6. **Validation linter passes:** `scripts/validate_schemas.py` finds no issues.
7. **No regression:** Agent outputs unchanged; validation success rate >= current rate.

## Test Plan

```bash
# Test schema validation
uv run pytest tests/schemas/test_agent_outputs.py -q

# Test discriminated unions
uv run pytest tests/schemas/test_discriminated_unions.py -q

# Validate all schemas
python scripts/validate_schemas.py

# Test validation self-correction with fixture cases
MEM_GRAPH_LOGFIRE_ENABLED=false OTEL_SDK_DISABLED=true \
  uv run pytest tests/schemas/test_validation_correction.py -q

# Regression on agents
MEM_GRAPH_LOGFIRE_ENABLED=false OTEL_SDK_DISABLED=true \
  uv run pytest tests/agents/ -q -k "output"

# Broad gate
MEM_GRAPH_LOGFIRE_ENABLED=false OTEL_SDK_DISABLED=true \
  uv run pytest tests/ -q
```

## Dependencies

- Task 029 (Base Agent Architecture) — agent structure must be stable.
- Task 033 (Tool System) — tools return typed schema objects.

## Notes

- Schema changes are backward compatible; old `dict` outputs can still be validated.
- Validation self-correction is probabilistic; good descriptions improve but don't guarantee success.
- Schema versioning (e.g., breaking changes) is future work.
