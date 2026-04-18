"""
resources/prompts.py — Master workflow prompts and instructions for sub-agent spin-up.
"""

from __future__ import annotations
from .personas import PERSONA_REGISTRY

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

# --- Master Workflow Prompts ---

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

# Registry for easy lookup
PROMPT_REGISTRY: dict[str, str] = {
    "sync_context": SYNC_CONTEXT_PROMPT,
    "plan_feature": PLAN_FEATURE_PROMPT,
    "run_audit": RUN_AUDIT_PROMPT,
    "close_session": CLOSE_SESSION_PROMPT,
    "workflow_agent": WORKFLOW_AGENT_PROMPT,
    "agent_builder_discovery": AGENT_BUILDER_DISCOVERY_PROMPT,
    "agent_builder_update": AGENT_BUILDER_UPDATE_PROMPT,
}
