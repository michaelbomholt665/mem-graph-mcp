"""Shared structured outputs for mem-graph agents.

Graph-node schemas live in the sibling ``models`` modules. This module holds
the validation contracts used for agent input/output so they can be reused by
evals, workflow runtimes, and MCP tools without importing full agent modules.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, Field

from ..config import ModelTier
from .audit import AuditFinding, AuditReport

type JSONValue = (
    str | int | float | bool | None | list[JSONValue] | dict[str, JSONValue]
)

RouterIntent: TypeAlias = Literal[
    "audit",
    "fix",
    "map",
    "refactor",
    "document",
    "review",
]
WorkflowMode: TypeAlias = Literal["route_only", "subagent_workflow"]
AskUserPolicy: TypeAlias = Literal["never", "on_error", "always"]
TaskPhase: TypeAlias = Literal["planning", "red", "green", "refactor", "audit"]
TaskPriorityLabel: TypeAlias = Literal["low", "medium", "high", "blocker"]
TaskComplexity: TypeAlias = Literal["low", "medium", "high", "very_high"]
DriftSeverity: TypeAlias = Literal["info", "minor", "major", "critical"]
ValidationSeverity: TypeAlias = Literal["critical", "major", "minor"]
ValidationCheck: TypeAlias = Literal[
    "logic",
    "style",
    "naming",
    "scope_exceeded",
    "documentation",
]
RelationshipKind: TypeAlias = Literal[
    "imports",
    "calls",
    "implements",
    "embeds",
    "references",
]


class BatchFileContent(BaseModel):
    """Pre-read file content passed to one orchestrated batch."""

    path: str = Field(
        description="Absolute or repo-relative path for the file included in this batch."
    )
    content: str = Field(
        description=(
            "Literal file content supplied to the sub-agent. May contain an error "
            "message when the file could not be read."
        )
    )
    truncated: bool = Field(
        default=False,
        description="True when content was clipped to the orchestrator byte cap.",
    )


class WorkflowStagePlan(BaseModel):
    """One stage in the optional router-produced workflow plan."""

    name: str = Field(
        description="Unique workflow stage name, for example 'planning' or 'implementation'."
    )
    depends_on: list[str] = Field(
        default_factory=list,
        description="Names of prerequisite stages that must complete before this stage runs.",
    )
    model: str | None = Field(
        default=None,
        description="Optional explicit model identifier to use for this stage.",
    )
    allowed_tools: list[str] = Field(
        default_factory=list,
        description="Tool names the stage is allowed to call when the workflow executes.",
    )


class WorkflowPlan(BaseModel):
    """Structured workflow plan emitted by the router for managed execution."""

    objective: str = Field(
        description="End-to-end objective the managed workflow should accomplish."
    )
    project_id: str = Field(
        description="Project identifier used to scope workflow execution and graph writes."
    )
    target_files: list[str] = Field(
        default_factory=list,
        description="Initial file set the workflow should treat as in scope.",
    )
    required_stages: list[WorkflowStagePlan] = Field(
        default_factory=list,
        description="Ordered stage plan the workflow should execute when present.",
    )
    stage_dependencies: dict[str, list[str]] = Field(
        default_factory=dict,
        description="Explicit dependency graph keyed by stage name for deterministic execution ordering.",
    )
    model_overrides: dict[str, str] = Field(
        default_factory=dict,
        description="Optional model overrides keyed by workflow stage name.",
    )
    allowed_tools: dict[str, list[str]] = Field(
        default_factory=dict,
        description="Per-stage tool allow-lists keyed by workflow stage name.",
    )
    max_retries: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Maximum number of validation or refinement retries for the workflow.",
    )
    ask_user_policy: AskUserPolicy = Field(
        default="on_error",
        description="When the workflow may stop and ask the user for intervention.",
    )


class RouterSubTask(BaseModel):
    """One sub-task decomposed from a routed request."""

    index: int = Field(
        ge=0,
        description="Execution order index for this sub-task within the routed plan.",
    )
    description: str = Field(
        description="Specific action this sub-task should complete before the next begins."
    )
    target_files: list[str] = Field(
        default_factory=list,
        description="Files most relevant to this sub-task's work.",
    )
    agent: str = Field(
        description="Downstream agent or helper that should own this sub-task.",
    )


class RouterDecision(BaseModel):
    """Routing and decomposition output for an incoming request."""

    tier: ModelTier = Field(
        description="Selected model tier for downstream execution, based on task complexity and scope."
    )
    file_count: int = Field(
        ge=0,
        description="Number of files currently in scope for this request.",
    )
    concurrency: int = Field(
        ge=1,
        description="Recommended level of parallelism for downstream execution.",
    )
    solo_mode: bool = Field(
        default=False,
        description="True when a single agent should work the full context instead of orchestration.",
    )
    intent: RouterIntent = Field(
        description="Classified user intent used to choose workflow shape and downstream tools.",
    )
    summary: str = Field(
        description="Short routing rationale explaining why this tier and plan were selected."
    )
    sub_tasks: list[RouterSubTask] = Field(
        default_factory=list,
        description="Ordered sub-tasks for downstream execution when decomposition is needed.",
    )
    workflow_mode: WorkflowMode = Field(
        default="route_only",
        description="Whether the router should only classify or emit a full managed workflow plan.",
    )
    workflow_plan: WorkflowPlan | None = Field(
        default=None,
        description="Structured workflow plan present only when workflow_mode is 'subagent_workflow'.",
    )


class DriftStatus(str, Enum):
    """Whether an architectural decision is still reflected in the codebase."""

    HONOURED = "honoured"
    DRIFTED = "drifted"
    SUPERSEDED = "superseded"
    UNVERIFIABLE = "unverifiable"


class DecisionReview(BaseModel):
    """Review outcome for one stored architectural decision."""

    decision_id: str = Field(
        description="Graph decision identifier being checked for drift or continued compliance."
    )
    decision_title: str = Field(
        description="Human-readable decision title so reports remain understandable without graph lookups."
    )
    status: DriftStatus = Field(
        description="Whether the decision is still honoured, drifted, superseded, or unverifiable."
    )
    evidence: str = Field(
        description="Concrete code evidence supporting the status, including files or symbols when available."
    )
    drifted_files: list[str] = Field(
        default_factory=list,
        description="Files where drift or non-compliance is visible; empty when the decision remains honoured.",
    )
    recommendation: str = Field(
        description="Specific next action, such as updating the decision, fixing code, or taking no action."
    )
    severity: DriftSeverity = Field(
        default="minor",
        description="Impact of the drift on the project if the current implementation remains unchanged.",
    )


class ReviewReport(BaseModel):
    """Complete decision-review report for a project."""

    project_id: str = Field(
        description="Project identifier this review report belongs to."
    )
    reviews: list[DecisionReview] = Field(
        default_factory=list,
        description="Per-decision review results produced during the run.",
    )
    summary: str = Field(
        description="Narrative summary of how the project's recorded decisions align with the codebase."
    )
    honoured_count: int = Field(
        default=0, ge=0, description="Number of decisions still honoured."
    )
    drifted_count: int = Field(
        default=0, ge=0, description="Number of decisions that have drifted."
    )
    unverifiable_count: int = Field(
        default=0,
        ge=0,
        description="Number of decisions that could not be verified from the available code evidence.",
    )
    partial_failure: bool = Field(
        default=False,
        description="True when the review completed with missing files, tool failures, or partial evidence.",
    )


class Task(BaseModel):
    """A single implementation task emitted by the task decomposition agent."""

    task_id: str = Field(
        description="Short stable task identifier, such as 'T01', referenced by dependencies."
    )
    title: str = Field(
        description="Action-oriented task title stating exactly what the engineer should do."
    )
    description: str = Field(
        description="Expanded implementation guidance, constraints, and rationale for this task."
    )
    phase: TaskPhase = Field(
        description="TDD-oriented phase this task belongs to: planning, red, green, refactor, or audit."
    )
    priority: TaskPriorityLabel = Field(
        default="medium",
        description="Relative delivery priority for ordering work within the decomposition.",
    )
    primary_file: str | None = Field(
        default=None,
        description="Primary file expected to carry most of the task's changes, when known.",
    )
    affected_files: list[str] = Field(
        default_factory=list,
        description="Other files likely to change or require validation because of this task.",
    )
    dependencies: list[str] = Field(
        default_factory=list,
        description="Other task IDs that must finish before this task can start.",
    )
    open_violations: list[str] = Field(
        default_factory=list,
        description="Violation IDs or summaries this task should address or work around.",
    )
    relevant_decisions: list[str] = Field(
        default_factory=list,
        description="Decision IDs that constrain how this task should be implemented.",
    )
    acceptance_criteria: list[str] = Field(
        default_factory=list,
        description="Specific verifiable outcomes that define 'done' for this task.",
    )


class DecompositionReport(BaseModel):
    """Complete task decomposition for a feature or change request."""

    feature_description: str = Field(
        description="Original feature or change request that was decomposed into tasks."
    )
    project_id: str = Field(
        description="Project identifier the decomposition applies to."
    )
    tasks: list[Task] = Field(
        default_factory=list,
        description="Ordered implementation tasks with dependencies and acceptance criteria.",
    )
    summary: str = Field(
        description="Narrative explanation of the decomposition strategy and key sequencing choices."
    )
    identified_blockers: list[str] = Field(
        default_factory=list,
        description="Known blockers, risks, or prerequisite issues discovered during planning.",
    )
    estimated_complexity: TaskComplexity = Field(
        default="medium",
        description="Overall complexity estimate for delivering the full request.",
    )
    partial_failure: bool = Field(
        default=False,
        description="True when decomposition completed with missing context or incomplete graph data.",
    )


class FilePatch(BaseModel):
    """Proposed code patch for one file."""

    file_path: str = Field(
        description="Repo-relative path to the file this patch should modify."
    )
    original_snippet: str = Field(
        description="Literal offending code to replace so patch application stays scoped and reviewable."
    )
    proposed_snippet: str = Field(
        description="Replacement code or insertion that resolves the targeted violation without widening scope."
    )
    violation_ids: list[str] = Field(
        default_factory=list,
        description="Violation identifiers this patch is intended to resolve.",
    )
    rationale: str = Field(
        description="Why this exact change resolves the problem while preserving surrounding behavior."
    )


class FixerReport(BaseModel):
    """Complete fixer output for a remediation run."""

    patches: list[FilePatch] = Field(
        default_factory=list,
        description="All proposed file patches produced during the run.",
    )
    unresolved_violations: list[str] = Field(
        default_factory=list,
        description="Violation identifiers the agent could not fix safely or deterministically.",
    )
    summary: str = Field(
        description="Narrative summary of what was changed and what remains unresolved."
    )
    tier_used: str = Field(
        description="Model tier or model identifier used when generating the proposed fixes."
    )


class FeatureLocation(BaseModel):
    """Map of a feature or concern to its primary implementation files."""

    feature_name: str = Field(
        description="Human-readable name of the feature, subsystem, or concern that was identified."
    )
    primary_file: str = Field(
        description="File that appears to be the main implementation home for this feature."
    )
    supporting_files: list[str] = Field(
        default_factory=list,
        description="Other files that implement, configure, or expose the same feature.",
    )
    consumers: list[str] = Field(
        default_factory=list,
        description="Files or features that depend on this feature's public surface.",
    )
    description: str = Field(
        description="One-sentence explanation of what the feature does in the codebase."
    )


class FileRelationship(BaseModel):
    """Directional relationship between two files discovered during mapping."""

    source_file: str = Field(
        description="File that depends on or references the target file."
    )
    target_file: str = Field(
        description="File being imported, called, extended, or otherwise referenced."
    )
    relationship_kind: RelationshipKind = Field(
        description="Nature of the relationship between source and target.",
    )
    symbols: list[str] = Field(
        default_factory=list,
        description="Specific symbols, APIs, or types involved in the relationship when known.",
    )


class MapReport(BaseModel):
    """Complete codebase map produced by the map agent."""

    package_path: str = Field(description="Root path that was mapped during the run.")
    features: list[FeatureLocation] = Field(
        default_factory=list,
        description="Identified features and the files that primarily own them.",
    )
    relationships: list[FileRelationship] = Field(
        default_factory=list,
        description="Directional file relationships that explain coupling and blast radius.",
    )
    entry_points: list[str] = Field(
        default_factory=list,
        description="Files identified as public or operational entry points into the package.",
    )
    summary: str = Field(
        description="Narrative overview of the package structure and the most important dependencies."
    )
    partial_failure: bool = Field(
        default=False,
        description="True when some files could not be read or mapped during the run.",
    )


class TestCaseProposal(BaseModel):
    """One failing test the sentry agent wants to add before implementation."""

    file_path: str = Field(
        description="Repo-relative or package-relative path where the new failing test should live."
    )
    test_name: str = Field(description="Name of the test case to add or update.")
    failing_assertion: str = Field(
        description="Assertion or expectation that should fail before the production fix is applied."
    )
    rationale: str = Field(
        description="Why this test is necessary to prove the bug or missing behavior exists first."
    )


class SentryReport(BaseModel):
    """Complete failing-test plan produced by the sentry agent."""

    test_cases: list[TestCaseProposal] = Field(
        default_factory=list,
        description="Proposed red tests that should be written before any production-code change.",
    )
    summary: str = Field(
        description="Narrative overview of the proposed red-test strategy.",
    )
    framework: str = Field(
        description="Detected or assumed test framework that the proposed tests should follow.",
    )


class ValidationStatus(str, Enum):
    """Outcome of a validation-gate review."""

    APPROVED = "approved"
    REJECTED = "rejected"


class ValidationViolation(BaseModel):
    """One issue found by the validation agent while reviewing a proposed patch."""

    file_path: str = Field(
        description="File where the validation issue was identified."
    )
    check: ValidationCheck = Field(
        description="Named validation check that failed, such as logic or scope_exceeded."
    )
    description: str = Field(
        description="Specific explanation of what is wrong and what must change before approval."
    )
    severity: ValidationSeverity = Field(
        default="major",
        description="Severity of the validation issue relative to the approve or reject decision.",
    )


class ValidationReport(BaseModel):
    """Complete validation decision over one proposed patch set."""

    status: ValidationStatus = Field(
        description="Approval decision for the proposed patch set after all validation checks ran."
    )
    violations: list[ValidationViolation] = Field(
        default_factory=list,
        description="Validation issues found during review; empty only when the patch set is approved.",
    )
    rationale: str = Field(
        description="Detailed explanation of why the patch set was approved or rejected."
    )
    files_checked: int = Field(
        ge=0,
        description="Number of files included in the patch set that the validator inspected.",
    )


class GenericBatchOutput(BaseModel):
    """Fallback wrapper for non-standard sub-agent outputs."""

    output_type: Literal["generic"] = Field(
        default="generic",
        description="Discriminator used when the batch payload is not one of the built-in report models.",
    )
    payload: dict[str, JSONValue] = Field(
        default_factory=dict,
        description="JSON-safe fallback payload returned by a custom registered sub-agent.",
    )


class AuditAggregate(BaseModel):
    """Merged audit findings across all orchestrated batches."""

    aggregate_type: Literal["audit"] = Field(
        default="audit",
        description="Discriminator identifying an audit aggregation payload.",
    )
    all_findings: list[AuditFinding] = Field(
        default_factory=list,
        description="All findings merged from successful batch AuditReport outputs.",
    )
    files_analysed: int = Field(
        default=0,
        ge=0,
        description="Count of files successfully analysed across all successful batches.",
    )
    files_skipped: int = Field(
        default=0,
        ge=0,
        description="Count of files skipped by the audit agent due to size or read failures.",
    )


class DecisionAggregate(BaseModel):
    """Merged decision-review data across orchestrated batches."""

    aggregate_type: Literal["decision"] = Field(
        default="decision",
        description="Discriminator identifying a decision-review aggregation payload.",
    )
    reviews: list[DecisionReview] = Field(
        default_factory=list,
        description="All decision reviews merged from successful decision-agent batches.",
    )
    drifted: list[str] = Field(
        default_factory=list,
        description="Decision identifiers that ended in the drifted state across the whole run.",
    )


class MapAggregate(BaseModel):
    """Merged code-map data across orchestrated batches."""

    aggregate_type: Literal["map"] = Field(
        default="map",
        description="Discriminator identifying a code-map aggregation payload.",
    )
    features: list[FeatureLocation] = Field(
        default_factory=list,
        description="All mapped features merged from successful batches.",
    )
    relationships: list[FileRelationship] = Field(
        default_factory=list,
        description="All file relationships merged from successful batches.",
    )
    entry_points: list[str] = Field(
        default_factory=list,
        description="Combined entry points discovered across batches.",
    )


class GenericAggregate(BaseModel):
    """Fallback aggregate payload for custom registered orchestrator sub-agents."""

    aggregate_type: Literal["generic"] = Field(
        default="generic",
        description="Discriminator identifying a generic aggregation payload.",
    )
    payload: dict[str, JSONValue] = Field(
        default_factory=dict,
        description="JSON-safe aggregate payload for custom sub-agents with no dedicated schema yet.",
    )


AggregateReport: TypeAlias = Annotated[
    AuditAggregate | DecisionAggregate | MapAggregate | GenericAggregate,
    Field(discriminator="aggregate_type"),
]
SubagentBatchOutput: TypeAlias = (
    AuditReport | ReviewReport | MapReport | GenericBatchOutput
)


class BatchResult(BaseModel):
    """Result of processing one orchestrator batch."""

    batch_index: int = Field(
        ge=0,
        description="Zero-based index of this batch within the full orchestrator run.",
    )
    files_processed: list[str] = Field(
        default_factory=list,
        description="Exact file paths processed in this batch, in deterministic order.",
    )
    output: SubagentBatchOutput | None = Field(
        default=None,
        description=(
            "Typed output returned by the sub-agent for this batch. Null only when "
            "the batch failed before a result could be produced."
        ),
    )
    failed: bool = Field(
        default=False,
        description="True when the batch timed out or raised before producing a valid result.",
    )
    error: str | None = Field(
        default=None,
        description="Error message captured for failed batches; null for successful ones.",
    )


class OrchestratorReport(BaseModel):
    """Final report produced by the codebase orchestrator."""

    package_path: str = Field(
        description="Root path that was processed by the orchestrator."
    )
    subagent_name: str = Field(
        description="Registered sub-agent name used for each batch, such as audit, map, or decision."
    )
    total_files: int = Field(
        ge=0,
        description="Total file count processed across all batches, including failed ones.",
    )
    total_batches: int = Field(
        ge=0, description="Number of batches attempted in this run."
    )
    failed_batches: int = Field(
        default=0,
        ge=0,
        description="Number of batches that timed out or failed before returning output.",
    )
    batch_results: list[BatchResult] = Field(
        default_factory=list,
        description="Per-batch outputs preserved for provenance and partial-failure analysis.",
    )
    aggregate: AggregateReport = Field(
        description="Merged typed aggregate generated from all successful batch outputs."
    )
    summary: str = Field(
        description="Narrative summary of the full orchestration run and the most important outcomes."
    )
    partial_failure: bool = Field(
        default=False,
        description="True when one or more batches failed but the orchestrator still returned an aggregate report.",
    )


__all__ = [
    "AggregateReport",
    "AskUserPolicy",
    "AuditAggregate",
    "BatchFileContent",
    "BatchResult",
    "DecisionAggregate",
    "DecisionReview",
    "DecompositionReport",
    "DriftStatus",
    "FeatureLocation",
    "FilePatch",
    "FileRelationship",
    "FixerReport",
    "GenericAggregate",
    "GenericBatchOutput",
    "JSONValue",
    "MapAggregate",
    "MapReport",
    "OrchestratorReport",
    "RelationshipKind",
    "ReviewReport",
    "RouterDecision",
    "RouterIntent",
    "RouterSubTask",
    "SentryReport",
    "SubagentBatchOutput",
    "Task",
    "TaskComplexity",
    "TaskPhase",
    "TaskPriorityLabel",
    "TestCaseProposal",
    "ValidationCheck",
    "ValidationReport",
    "ValidationSeverity",
    "ValidationStatus",
    "ValidationViolation",
    "WorkflowMode",
    "WorkflowPlan",
    "WorkflowStagePlan",
]
