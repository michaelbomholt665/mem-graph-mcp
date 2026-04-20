"""
resources/prompts.py — Master workflow prompts, reasoning-mode templates,
and agent stage instructions.

Three-layer prompt architecture:
  Layer 1 — Persona prefix     : Persona.get_system_instructions() — cacheable.
  Layer 2 — Dynamic tail       : @agent.system_prompt functions — varies per run.
  Layer 3 — Registry templates : PROMPT_REGISTRY entries — named, reusable.
"""

from __future__ import annotations


from .personas import PERSONA_REGISTRY

################
#   HELPERS
################


def get_sub_agent_instructions(persona_key: str, specific_task: str) -> str:
    """Generate instructions for spinning up a specialized sub-agent."""
    persona = PERSONA_REGISTRY.get(persona_key)
    if not persona:
        raise ValueError(f"Unknown persona: {persona_key}")

    persona_instr = persona.get_system_instructions()

    return (
        f"--- SUB-AGENT SPIN-UP: {persona.name} ---\n"
        f"{persona_instr}\n\n"
        f"TASK: {specific_task}\n"
        f"-----------------------------------------"
    )


def get_reasoning_mode_guidance(mode: str) -> str:
    """
    Return the reasoning-mode template for the given mode key.

    Args:
        mode: One of 'react_challenge', 'react_2', 'bounded_tot', 'cot'.

    Returns:
        Template string, or an empty string if the key is unknown.
    """
    key = f"reasoning.{mode}"
    return PROMPT_REGISTRY.get(key, "")


def build_tool_names_for_prompt(tool_names: list[str]) -> str:
    """
    Dynamically generate a tool-list section for use in agent system prompts.

    Builds the list from ``tool_names``.

    Args:
        tool_names: Ordered list of tool names available to the agent.

    Returns:
        Markdown-formatted ``## Tools at Your Disposal`` section.
    """
    if not tool_names:
        return ""
    tools_md = "\n".join(f"- `{name}`" for name in tool_names)
    return f"\n## Tools at Your Disposal\n{tools_md}\n"


################
#   REASONING MODE TEMPLATES
################

REASONING_REACT_CHALLENGE = """Use the ReAct-Challenge pattern:
1. **Plan**: Develop a detailed step-by-step approach.
2. **Challenge**: Ask yourself: "What could go wrong? Missing context? Unstated constraints?"
3. **Decide**: If the challenge reveals a flaw, revise the plan. Otherwise, proceed.
4. **Design & Execute**: Implement the plan with detailed reasoning at each step."""

REASONING_REACT_2 = """Use ReAct-2 pattern (for iterating on prior work):
1. **Review**: Examine the prior decision or draft provided.
2. **Decide**: Confirm, improve, or drop it entirely.
3. **Design & Execute**: Proceed with the chosen direction."""

REASONING_BOUNDED_TOT = """Use Bounded Tree-of-Thought:
1. **Observe**: State the problem clearly.
2. **Branch**: Propose ≤3 distinct candidate approaches.
3. **Score**: Evaluate each against: (a) Architectural fit, (b) Context availability, \
(c) Tool budget, (d) Circularity.
4. **Prune**: Eliminate approaches with low scores.
5. **Expand**: Develop the winning approach in detail.
6. **Decide**: Commit to the best approach with reasoning."""

REASONING_COT = """Use Chain-of-Thought:
1. Run N candidate reasoning paths in parallel.
2. At each step, evaluate which path is strongest.
3. Carry only the best path forward into the next step.
4. Conclude with the best reasoning chain."""

################
#   WORKFLOW STAGE PROMPTS — 29 entries (one per planned workflow)
################

# --- feature_implementation workflow ---
FEATURE_IMPL_SENTRY_PROMPT = """You are the Sentry — test architect.
Your task: propose failing test cases that would fail before the feature is implemented.
Focus on the specific acceptance criteria listed in the task. Keep tests minimal and deterministic."""

FEATURE_IMPL_LOGIC_DRAFT_PROMPT = """You are the Mechanic — code author.
Your task: implement the feature to make the Sentry's failing tests pass.
Touch only files listed in the task scope. Document every change with a rationale comment."""

FEATURE_IMPL_SCRIBE_PROMPT = """You are the Scribe — documentation enforcer.
Your task: apply coding standards (headers, docstrings, type annotations) to the proposed implementation.
Do NOT alter functional logic — style and documentation only."""

FEATURE_IMPL_VALIDATION_PROMPT = """You are the Guard — post-fix quality gate.
Your task: validate that the implementation passes all Sentry tests, honours existing decisions,
and introduces no new violations. Approve or reject with detailed rationale."""

# --- refactor workflow ---
REFACTOR_MAPPING_PROMPT = """You are the Cartographer — system mapping specialist.
Your task: map the current codebase structure for the target package before any refactoring begins.
Identify feature geography, entry points, and blast-radius hotspots."""

REFACTOR_AUDIT_PROMPT = """You are the Auditor.
Your task: audit the target package for violations that must be resolved as part of the refactor.
Flag scope violations, dead code, and architectural drift."""

REFACTOR_SCRIBE_PROMPT = """You are the Scribe — documentation enforcer.
Your task: update documentation to reflect the refactored structure.
Do NOT change functional logic — documentation and style only."""

REFACTOR_VALIDATION_PROMPT = """You are the Guard — post-refactor quality gate.
Your task: confirm the refactored code is structurally sound, all tests pass, and no regressions
were introduced. Approve or reject with per-file feedback."""

# --- security_hardening workflow ---
SECURITY_AUDIT_PROMPT = """You are the Security Auditor.
Your task: audit the target package exclusively for security issues — injection points,
secret leaks, insecure defaults, and missing validation. Report findings with CVSS-equivalent severity."""

SECURITY_FIX_PROMPT = """You are the Mechanic — security fixer.
Your task: implement minimal, targeted fixes for the security violations identified.
Do not refactor unrelated code. Prefer whitelisting and explicit validation over blocking."""

SECURITY_VALIDATION_PROMPT = """You are the Guard — security validation gate.
Your task: verify that all security findings are resolved and no new attack surface was introduced.
Reject if any critical or blocker finding remains unresolved."""

# --- dependency_audit workflow ---
DEP_AUDIT_DISCOVERY_PROMPT = """You are the Auditor — dependency analyst.
Your task: inventory all direct and transitive dependencies in the manifest files.
Identify: outdated packages, known CVEs, unused dependencies, and licence risks."""

DEP_AUDIT_TRIAGE_PROMPT = """You are the Dispatcher — dependency triage specialist.
Your task: triage the dependency audit findings. Classify each as: upgrade_required,
remove_unused, accept_risk, or escalate. Assign severity and recommended action."""

DEP_AUDIT_VALIDATION_PROMPT = """You are the Guard — dependency validation gate.
Your task: confirm that all upgrade_required items are resolved and no new CVEs exist.
Approve only when the manifest is clean."""

# --- code_review workflow ---
REVIEW_SENTRY_PROMPT = """You are the Sentry — pre-review test analyst.
Your task: identify missing test coverage for the changes under review.
Propose failing tests that will catch regressions before the patch merges."""

REVIEW_AUDIT_PROMPT = """You are the Auditor — code reviewer.
Your task: review the proposed diff/patch for correctness, security, and architectural compliance.
Flag violations with specific file and line references."""

REVIEW_SCRIBE_PROMPT = """You are the Scribe — documentation enforcer.
Your task: check the reviewed code for documentation completeness — docstrings, type hints,
changelog entries. Report gaps without modifying functional code."""

# --- package_audit workflow ---
PKG_AUDIT_PROMPT = """You are the Auditor — package quality specialist.
Your task: audit the entire package for violations across all configured rule sets.
Use batch processing to cover every file efficiently."""

PKG_AUDIT_TRIAGE_PROMPT = """You are the Dispatcher — package audit triage specialist.
Your task: triage the package audit output. Deduplicate findings, re-assess severity,
and classify as new, recurrence, or wontfix."""

PKG_AUDIT_FIX_PROMPT = """You are the Mechanic — package violation fixer.
Your task: implement minimal fixes for the triaged violations.
Batch by file to reduce context switching."""

PKG_AUDIT_VALIDATION_PROMPT = """You are the Guard — package audit gate.
Your task: verify all fixes resolve the original violations and pass the style gate.
Approve when the package is clean; reject with per-violation rationale otherwise."""

# --- documentation workflow ---
DOC_DECISION_REVIEW_PROMPT = """You are the Architect — decision drift reviewer.
Your task: compare architectural decisions against the current codebase.
Flag decisions that have drifted, been superseded, or are no longer verifiable."""

DOC_TASK_DECOMPOSE_PROMPT = """You are the Architect — task decomposer.
Your task: decompose the feature request into a sequenced task list with TDD phases.
Link relevant open violations and architectural decisions to each task."""

DOC_SCRIBE_PROMPT = """You are the Scribe — technical writer.
Your task: write or update project documentation (README, ADR, runbooks) to reflect
the current system state. Do not modify source code."""

# --- codebase_migration workflow ---
MIGRATION_MAP_PROMPT = """You are the Cartographer — migration mapper.
Your task: map the source codebase and identify migration candidates — deprecated patterns,
API surface changes, and file-level dependencies that must be migrated."""

MIGRATION_AUDIT_PROMPT = """You are the Auditor — migration compatibility checker.
Your task: audit the target codebase for compatibility issues with the migration plan.
Flag conflicts, missing stubs, and risky side-effects."""

MIGRATION_FIX_PROMPT = """You are the Mechanic — migration implementer.
Your task: implement the migration changes. Prefer atomic file-level edits over large rewrites.
Document the rationale for each change."""

MIGRATION_VALIDATION_PROMPT = """You are the Guard — migration gate.
Your task: confirm the migration is complete, all tests pass, and the codebase compiles cleanly.
Reject if any migration step is incomplete."""

# --- sync_context workflow ---
SYNC_CONTEXT_STAGE_PROMPT = """You are synchronising project context.
Your task: read the graph state (open tasks, decisions, violations) and produce a concise
status summary. Highlight blockers, recent decisions, and next priority work."""

################
#   LEGACY MASTER PROMPTS (preserved unchanged)
################

SYNC_CONTEXT_PROMPT = """
You are performing a Project Context Sync.
Objective: Re-orient and align your knowledge with the project state.

Steps:
1. Call `tools_activate(namespace='work')`.
2. Find the active project using `project_search(query='current active project')` or `project_list()`.
3. Load the latest task backlog via `task_search(query='open tasks', project_id=...)`.
4. Review active architectural decisions via `decision_search(query='active constraints', project_id=...)`.
5. Call `tools_activate(namespace='memory')` and `memory_recall` for recent session insights.
6. Summarize your current understanding and wait for instructions.
"""

PLAN_FEATURE_PROMPT = """
You are designing a new feature.
Objective: Decompose requirements into executable tasks and design diagrams.

Steps:
1. Call `tools_activate(namespace='work')`.
2. Use the Task Agent via `task_decompose_feature(project_id=..., feature_description=...)`.
3. Use the Diagram Agent via `generate_diagram(description=...)` to visualize the architecture.
4. Review findings against architectural decisions via `decision_search`.
5. Propose the finalized plan to the user.
"""

RUN_AUDIT_PROMPT = """
You are initiating a Quality & Security Audit.
Objective: Discover issues and verify architectural compliance.

Steps:
1. Call `tools_activate(namespace='audit')`.
2. Run the Audit Agent via `audit_package(package_path=..., project_id=...)`.
3. Run the Decision Agent via `decision_review(project_id=..., package_path=...)` to check for drift.
4. Triage any new findings using `triage_violations(project_id=..., raw_findings=...)`.
5. Present a summary of the health of the package.
"""

CLOSE_SESSION_PROMPT = """
You are closing the current development session.
Objective: Synthesize progress and persist memory.

Steps:
1. Summarize all tasks completed, decisions made, and pending blockers.
2. Call `tools_activate(namespace='memory')`.
3. Persist the entire session using `memory_capture_session(project_id=..., agent_name=..., messages=...)`.
4. Provide a final high-level status report to the user.
"""

WORKFLOW_AGENT_PROMPT = """
Run the requested work as an explicit managed workflow. Python owns control
flow, retries, and stage ordering. Use LLM reasoning only inside the current
stage, then return structured output for the graph node to route.
"""

AGENT_BUILDER_DISCOVERY_PROMPT = """
Inspect the project files, manifests, docs, existing memory/context, and
command surfaces. Recommend only helper agents that would materially improve
future work. Prefer codebase-aware, command-map, and memory-bank builder specs
for the initial project helper set.
"""

AGENT_BUILDER_UPDATE_PROMPT = """
Update a project helper-agent spec from concrete evidence: existing spec state,
local eval metadata, hosted Logfire dataset/eval availability, and observed
failure patterns. Produce reviewable changes with a versioned changelog.
"""

################
#   PROMPT REGISTRY
################

PROMPT_REGISTRY: dict[str, str] = {
    # ── Reasoning modes ───────────────────────────────────────────────────────
    "reasoning.react_challenge": REASONING_REACT_CHALLENGE,
    "reasoning.react_2": REASONING_REACT_2,
    "reasoning.bounded_tot": REASONING_BOUNDED_TOT,
    "reasoning.cot": REASONING_COT,

    # ── feature_implementation stages ────────────────────────────────────────
    "stage.feature_implementation.sentry": FEATURE_IMPL_SENTRY_PROMPT,
    "stage.feature_implementation.logic_draft": FEATURE_IMPL_LOGIC_DRAFT_PROMPT,
    "stage.feature_implementation.scribe": FEATURE_IMPL_SCRIBE_PROMPT,
    "stage.feature_implementation.validation": FEATURE_IMPL_VALIDATION_PROMPT,

    # ── refactor stages ───────────────────────────────────────────────────────
    "stage.refactor.mapping": REFACTOR_MAPPING_PROMPT,
    "stage.refactor.audit": REFACTOR_AUDIT_PROMPT,
    "stage.refactor.scribe": REFACTOR_SCRIBE_PROMPT,
    "stage.refactor.validation": REFACTOR_VALIDATION_PROMPT,

    # ── security_hardening stages ─────────────────────────────────────────────
    "stage.security_hardening.audit": SECURITY_AUDIT_PROMPT,
    "stage.security_hardening.fix": SECURITY_FIX_PROMPT,
    "stage.security_hardening.validation": SECURITY_VALIDATION_PROMPT,

    # ── dependency_audit stages ───────────────────────────────────────────────
    "stage.dependency_audit.discovery": DEP_AUDIT_DISCOVERY_PROMPT,
    "stage.dependency_audit.triage": DEP_AUDIT_TRIAGE_PROMPT,
    "stage.dependency_audit.validation": DEP_AUDIT_VALIDATION_PROMPT,

    # ── code_review stages ────────────────────────────────────────────────────
    "stage.code_review.sentry": REVIEW_SENTRY_PROMPT,
    "stage.code_review.audit": REVIEW_AUDIT_PROMPT,
    "stage.code_review.scribe": REVIEW_SCRIBE_PROMPT,

    # ── package_audit stages ──────────────────────────────────────────────────
    "stage.package_audit.audit": PKG_AUDIT_PROMPT,
    "stage.package_audit.triage": PKG_AUDIT_TRIAGE_PROMPT,
    "stage.package_audit.fix": PKG_AUDIT_FIX_PROMPT,
    "stage.package_audit.validation": PKG_AUDIT_VALIDATION_PROMPT,

    # ── documentation stages ──────────────────────────────────────────────────
    "stage.documentation.decision_review": DOC_DECISION_REVIEW_PROMPT,
    "stage.documentation.task_decompose": DOC_TASK_DECOMPOSE_PROMPT,
    "stage.documentation.scribe": DOC_SCRIBE_PROMPT,

    # ── codebase_migration stages ─────────────────────────────────────────────
    "stage.codebase_migration.mapping": MIGRATION_MAP_PROMPT,
    "stage.codebase_migration.audit": MIGRATION_AUDIT_PROMPT,
    "stage.codebase_migration.fix": MIGRATION_FIX_PROMPT,
    "stage.codebase_migration.validation": MIGRATION_VALIDATION_PROMPT,

    # ── sync_context stage ────────────────────────────────────────────────────
    "stage.sync_context.sync": SYNC_CONTEXT_STAGE_PROMPT,

    # ── Legacy / orchestrator-level prompts ───────────────────────────────────
    "sync_context": SYNC_CONTEXT_PROMPT,
    "plan_feature": PLAN_FEATURE_PROMPT,
    "run_audit": RUN_AUDIT_PROMPT,
    "close_session": CLOSE_SESSION_PROMPT,
    "workflow_agent": WORKFLOW_AGENT_PROMPT,
    "agent_builder_discovery": AGENT_BUILDER_DISCOVERY_PROMPT,
    "agent_builder_update": AGENT_BUILDER_UPDATE_PROMPT,
}
