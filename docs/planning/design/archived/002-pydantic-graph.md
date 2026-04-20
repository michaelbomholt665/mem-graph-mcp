# Design: Pydantic-Graph Integration (ReAct Workflows)

**Status:** Design Phase  
**Priority:** High (Core orchestration)  
**Date:** 2026-04-13

---

## Overview

Pydantic-Graph is a type-safe state machine library built on Pydantic that enables deterministic, resumable workflows. While `orchestrator_graph.py` already implements a basic state machine (ContextGather → Sentry → LogicDraft → StyleDraft → Guard → MemorySync), this design enhances it with:

1. **Explicit Node Typing:** Each node is a `BaseNode` subclass with typed input/output
2. **Resumability:** Failed runs can resume from the last successful node
3. **Conditional Routing:** Nodes can route to different paths based on state
4. **Observable Events:** Graph execution can be logged at node boundaries

---

## Goals

1. **Formalize Workflow States:** Make the autopilot state machine type-safe and introspectable
2. **Enable Resumability:** If a node fails, resume from that node on retry
3. **Support Conditional Logic:** Route to different sub-graphs based on tier or language
4. **Integrate with Logging:** Every node transition is logged via OpenTelemetry

---

## Scope

### In Scope
- Enhance existing `AutopilotState` dataclass with Pydantic integration
- Create explicit node classes (`ContextGatherNode`, `SentryNode`, etc.) extending `BaseNode`
- Implement conditional routing between nodes (e.g., if tier=QUICK, skip style node)
- Add graph execution hooks for logging/metrics
- Implement checkpoint persistence for resumability

### Out of Scope
- Replacing the existing agent logic inside each node
- Changing the Core Five agent definitions
- Migrating non-ReAct workflows to graph patterns (keep simple tools as tools)

---

## Current State (orchestrator_graph.py)

The current implementation is a manual state machine:

```python
class AutopilotState(BaseModel):
    language: Literal["go", "python", "typescript"] = "python"
    target_files: list[str] = Field(default_factory=list)
    ...
    retry_count: int = 0
    max_retries: int = 3

# Nodes execute as raw methods, not typed classes
async def orchestrate(initial_state: AutopilotState, graph: OrchestratorGraph) -> AutopilotState:
    state = initial_state
    state = await graph.context_gather(state)
    state = await graph.sentry(state)
    state = await graph.logic_draft(state)
    # ... etc
```

This works but:
- No explicit error handling per-node
- No built-in resumability
- Hard to trace node transitions
- Manual routing logic in the orchestrator

---

## Enhanced Architecture

### 1. Type-Safe Node Definitions

Replace manual orchestration with explicit `BaseNode` classes:

```python
# src/mem_graph/agents/orchestrator_graph.py

from pydantic_graph import BaseNode, End, Graph, GraphRunContext
from typing import Annotated

class ContextGatherNode(BaseNode):
    """
    Reads target files and gathers context from the knowledge graph.
    
    Input: AutopilotState with language, target_files, project_id
    Output: Same state with context_violations, context_decisions, context_map populated
    """
    
    async def run(self, state: AutopilotState, context: GraphRunContext) -> AutopilotState | SentryNode:
        try:
            # Gather violations, decisions, codebase map from graph
            state.context_violations = await gather_violations(state.project_id)
            state.context_decisions = await gather_decisions(state.project_id)
            state.context_map = await gather_codebase_map(state.language, state.project_id)
            
            # Pre-read files
            state.file_contents = {
                path: await asyncio.to_thread(read_file, path)
                for path in state.target_files
            }
            
            logger.info(f"Context gathered: {len(state.file_contents)} files")
            return SentryNode()  # Explicit next node
        except Exception as e:
            logger.error(f"Context gather failed: {e}")
            raise

class SentryNode(BaseNode):
    """
    Runs test suite to establish baseline before modifications.
    
    Input: AutopilotState with file_contents
    Output: Same state with sentry_tests populated
    """
    
    async def run(self, state: AutopilotState, context: GraphRunContext) -> AutopilotState | LogicDraftNode:
        # Run tests, capture baseline
        state.sentry_tests = await run_test_suite(state.language, state.target_files)
        return LogicDraftNode()

class LogicDraftNode(BaseNode):
    """
    First pass: logic refactoring using tier-selected agent.
    """
    
    async def run(self, state: AutopilotState, context: GraphRunContext) -> AutopilotState | StyleDraftNode:
        agent = await get_agent_for_tier(state.tier)
        state.fixer_patches = await agent.generate_patches(state)
        return StyleDraftNode()

class StyleDraftNode(BaseNode):
    """
    Second pass: style cleaning (can be skipped for QUICK tier).
    """
    
    async def run(self, state: AutopilotState, context: GraphRunContext) -> AutopilotState | GuardNode:
        if state.tier == ModelTier.QUICK:
            # Skip style pass
            state.styled_patches = state.fixer_patches
            logger.info("Skipping style pass (QUICK tier)")
            return GuardNode()
        
        agent = await get_agent_for_tier(state.tier)
        state.styled_patches = await agent.style_check(state.fixer_patches)
        return GuardNode()

class GuardNode(BaseNode):
    """
    Validation: Run tests on proposed changes before commit.
    """
    
    async def run(self, state: AutopilotState, context: GraphRunContext) -> AutopilotState | MemorySyncNode | RefineNode:
        violations = await validate_patches(state.styled_patches)
        
        if not violations:
            state.validation_status = "approved"
            return MemorySyncNode()
        
        state.validation_violations = violations
        
        if state.retry_count >= state.max_retries:
            logger.warning(f"Max retries ({state.max_retries}) reached. Forcing approval.")
            state.validation_status = "force_approved"
            return MemorySyncNode()
        
        # Retry: route back to LogicDraft
        state.retry_count += 1
        logger.info(f"Validation failed. Retry {state.retry_count}/{state.max_retries}")
        return RefineNode()

class RefineNode(BaseNode):
    """
    Refinement loop: agent addresses validation failures.
    """
    
    async def run(self, state: AutopilotState, context: GraphRunContext) -> AutopilotState | GuardNode:
        agent = await get_agent_for_tier(state.tier)
        state.fixer_patches = await agent.refine_patches(state.fixer_patches, state.validation_violations)
        state.styled_patches = state.fixer_patches  # Reset for next guard
        return GuardNode()

class MemorySyncNode(BaseNode):
    """
    Final: Persist results to knowledge graph and write summary notes.
    """
    
    async def run(self, state: AutopilotState, context: GraphRunContext) -> End:
        # Write patches to files
        for path, content in state.styled_patches.items():
            await asyncio.to_thread(write_file, path, content)
        
        # Persist to graph
        await persist_to_graph(state)
        
        # Write final note
        state.final_notes = f"Autopilot completed with {len(state.styled_patches)} files patched."
        await write_note_to_graph(state.project_id, state.final_notes)
        
        state.success = True
        logger.info(f"Autopilot run complete: {state.final_notes}")
        
        return End()  # Explicit end
```

### 2. Graph Factory

```python
def create_autopilot_graph() -> Graph:
    """Construct and return the autopilot workflow graph."""
    return Graph(
        nodes=[
            ContextGatherNode(),
            SentryNode(),
            LogicDraftNode(),
            StyleDraftNode(),
            GuardNode(),
            RefineNode(),
            MemorySyncNode(),
        ]
    )

async def run_autopilot(
    initial_state: AutopilotState,
    graph: Graph | None = None,
    checkpoint_path: str | None = None,
) -> AutopilotState:
    """
    Execute autopilot workflow with optional resumability.
    
    If checkpoint_path is provided, load prior state and resume.
    """
    if checkpoint_path and Path(checkpoint_path).exists():
        # Resume from checkpoint
        with open(checkpoint_path) as f:
            state = AutopilotState(**json.load(f))
        logger.info(f"Resuming from checkpoint: {checkpoint_path}")
    else:
        state = initial_state
    
    if graph is None:
        graph = create_autopilot_graph()
    
    # Run graph with checkpointing
    context = GraphRunContext()
    result = await graph.run(state, context)
    
    # Save checkpoint after each node
    if checkpoint_path:
        with open(checkpoint_path, 'w') as f:
            json.dump(result.model_dump(), f)
    
    return result
```

### 3. Conditional Routing Example

The `StyleDraftNode` above shows how to use conditional routing:

```python
if state.tier == ModelTier.QUICK:
    return GuardNode()  # Skip style
else:
    return StyleDraftNode()  # Full workflow
```

### 4. Observability Hooks

Integrate with OpenTelemetry to log node transitions:

```python
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

class ContextGatherNode(BaseNode):
    async def run(self, state: AutopilotState, context: GraphRunContext) -> AutopilotState | SentryNode:
        with tracer.start_as_current_span("context_gather") as span:
            span.set_attribute("project_id", state.project_id)
            span.set_attribute("language", state.language)
            
            try:
                # ... gather logic ...
                span.set_attribute("files_gathered", len(state.file_contents))
                return SentryNode()
            except Exception as e:
                span.record_exception(e)
                raise
```

---

## Benefits Over Current Manual Approach

| Aspect | Manual | Pydantic-Graph |
|--------|--------|---|
| **Type Safety** | `dict` or loose models | Explicit `BaseNode` types |
| **Resumability** | Manual checkpointing | Built-in via graph context |
| **Routing** | If/else chains | Explicit node→node returns |
| **Observability** | Manual logging calls | Automatic span wrapping |
| **Testing** | Test orchestrator logic + nodes separately | Test individual nodes in isolation |

---

## Migration Path

1. **Phase 1:** Leave existing orchestrator intact; create parallel `OrchestratorGraphV2` using new node classes
2. **Phase 2:** Update tools (`orchestrate_codebase` tool) to use `OrchestratorGraphV2`
3. **Phase 3:** Once stable, replace old orchestrator with new one
4. **Phase 4:** Consider applying same pattern to other multi-step workflows (not just autopilot)

---

## Implementation Checklist

- [ ] Create explicit node classes extending `BaseNode`
- [ ] Implement `run()` method for each node
- [ ] Add conditional routing (e.g., tier-based skipping)
- [ ] Create graph factory function
- [ ] Implement checkpoint persistence
- [ ] Add OpenTelemetry span wrapping
- [ ] Test node-by-node execution
- [ ] Test graph-level resumability
- [ ] Integrate into `orchestrate_codebase` tool

---

## Success Criteria

1. Graphs are type-safe and fully introspectable
2. Failed nodes can resume without re-executing earlier nodes
3. Conditional logic (tier-based, language-based) works correctly
4. All node transitions are logged via OpenTelemetry
5. No regression in autopilot performance

---

## Dependencies

- `pydantic-graph>=0.8.1` (already in `pyproject.toml`)
- `opentelemetry-api>=1.20.0` (already in `pyproject.toml`)
