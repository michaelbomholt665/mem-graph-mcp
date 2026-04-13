# Design: Pydantic-Deep Integration (Planning & Self-Correction)

**Status:** Design Phase  
**Priority:** Medium-High (Improves agent quality)  
**Date:** 2026-04-13

---

## Overview

Pydantic-Deep enhances agents with forced planning and self-correction. Instead of agents jumping directly to tool calls, they:

1. Create a **visible plan** (stored in knowledge graph)
2. Execute according to that plan
3. **Verify** their work against the plan
4. **Self-correct** if verification fails

This "think twice" pattern is especially valuable for high-stakes operations like code refactoring, where user review is important.

---

## Goals

1. **Improve Agent Reasoning:** Force agents to create explicit plans before acting
2. **Increase Transparency:** Store plans in knowledge graph so users see the intent
3. **Enable Self-Correction:** Agents verify their output and fix errors without user intervention
4. **Support Nested Planning:** Complex tasks can decompose into sub-tasks with their own plans

---

## Scope

### In Scope
- Implement planning wrapper for Core Five agents (Audit, Map, Validate, Fix, Document)
- Store plans as graph entities (`Plan` nodes)
- Implement verification nodes that check plan adherence
- Add self-correction loops for agents that fail verification
- Create `PlanningAgent` wrapper that enforces the pattern

### Out of Scope
- Changing underlying agent logic (plans wrap agents, not replace them)
- Migrating all agents to planning (optional for heavy operations, required for EXPERT tier)
- Creating a general "planner" agent (focus on wrapping specific agents)

---

## Architecture

### 1. Plan Model

```python
# src/mem_graph/models/plan.py

from enum import Enum
from datetime import datetime
from pydantic import BaseModel, Field

class PlanStatus(str, Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    REVISION = "revision"

class PlanStep(BaseModel):
    """Single step in a plan."""
    id: str = Field(description="Unique step ID")
    sequence: int = Field(description="Execution order")
    description: str = Field(description="What this step does")
    expected_output: str = Field(description="What success looks like")
    depends_on: list[str] = Field(default_factory=list, description="Step IDs this depends on")

class Plan(BaseModel):
    """
    Explicit plan created before executing a task.
    
    Plans are stored in the knowledge graph and can be referenced
    for verification and self-correction.
    """
    plan_id: str
    task: str = Field(description="High-level goal")
    context: str = Field(description="Background/constraints")
    steps: list[PlanStep]
    status: PlanStatus = PlanStatus.DRAFT
    created_at: datetime
    approved_at: datetime | None = None
    completed_at: datetime | None = None
    rationale: str = Field(description="Why this plan was chosen")
    alternatives_considered: list[str] = Field(default_factory=list)
```

### 2. Planning Agent Wrapper

```python
# src/mem_graph/agents/planning_agent.py

from pydantic_ai import Agent, RunContext
from pydantic_deep import DeepAgent

class PlanningAgent:
    """
    Wraps any agent to add planning + verification.
    
    Workflow:
      1. Ask agent to create a plan
      2. Store plan in graph
      3. Execute agent normally
      4. Verify output against plan
      5. If verification fails, request revision
    """
    
    def __init__(self, 
                 agent: Agent,
                 graph_client: GraphClient,
                 project_id: str,
                 tier: ModelTier = ModelTier.STANDARD):
        self.agent = agent
        self.graph = graph_client
        self.project_id = project_id
        self.tier = tier
        
        # Use pydantic-deep for nested planning
        self.deep_agent = DeepAgent(
            agent=agent,
            enable_planning=True,
            enable_verification=True,
        )
    
    async def create_plan(self, task: str, context: str) -> Plan:
        """
        Ask agent to create a plan for the task.
        
        Returns a Plan object that is stored in the graph.
        """
        prompt = f"""
        Create a detailed plan for this task:
        
        TASK: {task}
        
        CONTEXT: {context}
        
        Your plan should:
        1. List all steps in sequence
        2. Explain what success looks like for each step
        3. Note any dependencies between steps
        4. Consider edge cases
        5. Explain why you chose this approach
        
        Format as structured JSON with fields: steps (list of {{}step_id, sequence, description, expected_output, depends_on{}}), rationale, alternatives_considered
        """
        
        response = await self.agent.run(prompt)
        
        # Parse response into Plan object
        plan_data = json.loads(response.data)
        plan = Plan(
            plan_id=uuid.uuid4().hex,
            task=task,
            context=context,
            steps=[PlanStep(**step) for step in plan_data["steps"]],
            rationale=plan_data["rationale"],
            alternatives_considered=plan_data.get("alternatives_considered", []),
            created_at=datetime.now(),
        )
        
        # Store in graph
        await self.graph.create_plan_node(self.project_id, plan)
        
        return plan
    
    async def execute_with_plan(self, task: str, context: str) -> tuple[str, Plan]:
        """
        Execute task with planning + verification.
        
        Returns (output, plan) where plan contains all steps and verification results.
        """
        # Phase 1: Create plan
        plan = await self.create_plan(task, context)
        logger.info(f"Created plan {plan.plan_id} with {len(plan.steps)} steps")
        
        # Phase 2: Execute task (agent runs normally)
        execution_prompt = f"""
        Execute this task following the plan provided:
        
        TASK: {task}
        
        PLAN:
        {json.dumps([step.model_dump() for step in plan.steps], indent=2)}
        
        After each step, confirm that you're following the plan.
        If you deviate, explain why.
        """
        
        output = await self.agent.run(execution_prompt)
        
        # Phase 3: Verify output against plan
        verification_result = await self.verify_against_plan(
            task=task,
            plan=plan,
            output=output.data,
        )
        
        if not verification_result["passed"]:
            # Phase 4: Self-correct
            corrections = await self.self_correct(
                plan=plan,
                output=output.data,
                failures=verification_result["failures"],
            )
            output.data = corrections
        
        # Update plan status
        plan.status = PlanStatus.COMPLETED
        plan.completed_at = datetime.now()
        await self.graph.update_plan_node(self.project_id, plan)
        
        return output.data, plan
    
    async def verify_against_plan(self, task: str, plan: Plan, output: str) -> dict:
        """
        Verify that output satisfies all plan steps.
        
        Returns dict with keys:
          - passed: bool
          - failures: list of (step_id, reason) tuples
          - evidence: dict of step_id → verification evidence
        """
        verification_prompt = f"""
        Verify that this output satisfies the plan steps:
        
        PLAN STEPS:
        {json.dumps([step.model_dump() for step in plan.steps], indent=2)}
        
        ACTUAL OUTPUT:
        {output}
        
        For each step, check:
        1. Was this step executed?
        2. Does the output match the expected_output description?
        3. Are there any deviations or missed steps?
        
        Format your response as JSON with structure:
        {{
          "passed": bool,
          "failures": [
            {{"step_id": "...", "reason": "..."}}
          ],
          "evidence": {{
            "step_1": "evidence of completion",
            ...
          }}
        }}
        """
        
        response = await self.agent.run(verification_prompt)
        result = json.loads(response.data)
        
        return result
    
    async def self_correct(self, plan: Plan, output: str, failures: list[dict]) -> str:
        """
        Attempt to fix verification failures without user intervention.
        """
        correction_prompt = f"""
        The previous output had these issues:
        
        {json.dumps(failures, indent=2)}
        
        Revise the output to address these issues while still following the plan:
        
        {json.dumps([step.model_dump() for step in plan.steps], indent=2)}
        
        Previous output:
        {output}
        
        Provide the corrected output.
        """
        
        response = await self.agent.run(correction_prompt)
        
        logger.info(f"Self-corrected output for plan {plan.plan_id}")
        
        return response.data
```

### 3. Integration with Core Five Agents (Wrapper Pattern)

Planning wraps agents at instantiation—no changes to agent code itself:

```python
# src/mem_graph/agents/__init__.py (factory location)

from .audit.audit_agent import create_audit_agent
from .fix.fixer_agent import create_fix_agent
from .validate.sentry_agent import create_sentry_agent
from .validate.validation_agent import create_validation_agent
from .map.map_agent import create_map_agent
from .document.task_agent import create_task_agent

class AgentFactory:
    """Factory for Core Five agents with optional planning wrapper."""
    
    def __init__(self, graph_client: GraphClient, project_id: str):
        self.graph = graph_client
        self.project_id = project_id
    
    async def audit_agent(self, tier: ModelTier = ModelTier.STANDARD) -> Agent:
        """Audit agent (planning optional for EXPERT tier)."""
        agent = create_audit_agent(tier)
        
        if tier == ModelTier.EXPERT:
            return PlanningAgent(agent, self.graph, self.project_id, tier)
        return agent
    
    async def fix_agent(self, tier: ModelTier = ModelTier.STANDARD) -> Agent:
        """Fix agent (planning recommended for EXPERT tier)."""
        agent = create_fix_agent(tier)
        
        if tier == ModelTier.EXPERT:
            return PlanningAgent(agent, self.graph, self.project_id, tier)
        return agent
    
    async def validate_agent(self, tier: ModelTier = ModelTier.STANDARD) -> Agent:
        """Validate agent (planning always enabled—critical)."""
        agent = create_validation_agent(tier)
        # Validation is critical—always use planning
        return PlanningAgent(agent, self.graph, self.project_id, tier)
    
    # Map, Task, etc. use planning for EXPERT tier
```

**Pattern:** Agent code stays in `/agents/{category}/{agent_name}.py`, factory wraps at instantiation.

### 4. Graph Integration

Store plans as nodes in the knowledge graph so they're visible to the user:

```python
# Cypher query to store a plan

MATCH (project:Project {id: $project_id})
CREATE (plan:Plan {
  plan_id: $plan_id,
  task: $task,
  status: $status,
  created_at: datetime($created_at),
  rationale: $rationale
})
CREATE (plan)-[:FOR]->(project)
WITH plan
UNWIND $steps AS step_data
CREATE (step:PlanStep {
  step_id: step_data.id,
  sequence: step_data.sequence,
  description: step_data.description,
  expected_output: step_data.expected_output
})
CREATE (step)-[:PART_OF]->(plan)
WITH plan, step
FOREACH (dep_id IN step_data.depends_on |
  MATCH (other:PlanStep {step_id: dep_id})
  CREATE (step)-[:DEPENDS_ON]->(other)
)
```

---

## Benefits

1. **Transparency:** Users can see what the agent *intended* to do via the plan
2. **Debugging:** If a run fails, the plan provides context
3. **Auditability:** All plans are stored in graph for compliance/review
4. **Quality:** Self-correction loop catches mistakes agents would otherwise make
5. **Composability:** Complex tasks can nest plans (sub-task has its own plan)

---

## When to Use Planning

| Scenario | Planning? | Rationale |
|----------|-----------|-----------|
| QUICK tier | No | Speed is priority |
| STANDARD tier, simple code review | No | Low risk, straightforward |
| STANDARD tier, large refactor | Yes | Worth the overhead |
| EXPERT tier, any operation | Yes | Quality is priority |
| Destructive operation (delete code) | Yes | Always require review |
| User elicitation choice | Optional | User can request plan review |

---

## Implementation Checklist

- [ ] Create `Plan` and `PlanStep` models in `src/mem_graph/models/plan.py`
- [ ] Implement `PlanningAgent` wrapper class in `src/mem_graph/agents/planning_agent.py`
- [ ] Add `create_plan()` method to PlanningAgent
- [ ] Add `execute_with_plan()` method to PlanningAgent
- [ ] Add `verify_against_plan()` method to PlanningAgent
- [ ] Add `self_correct()` method to PlanningAgent
- [ ] Create Cypher schema for Plan nodes in graph
- [ ] Update `src/mem_graph/agents/__init__.py` factory to wrap agents with PlanningAgent
- [ ] Test planning + verification on audit agent (one agent)
- [ ] Test self-correction loop
- [ ] Add OpenTelemetry spans around planning phases
- [ ] Extend to remaining agents as needed

---

## Success Criteria

1. Plans are created and stored in graph
2. Verification detects output misalignment with plan
3. Self-correction improves agent output
4. No regression in task completion time (for tier=STANDARD+)
5. All plans are auditable in the graph

---

## Dependencies

- `pydantic-deep[cli]>=0.3.13` (already in `pyproject.toml`)
- Graph client with plan node support
- OpenTelemetry for phase timing

---

## Next Steps

1. Implement `Plan` and `PlanStep` models
2. Build `PlanningAgent` wrapper
3. Update graph schema for plans
4. Integration test with one agent (audit)
5. Extend to remaining four agents
