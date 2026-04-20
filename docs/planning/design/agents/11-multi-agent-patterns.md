# Multi-Agent Patterns in Pydantic AI

This document explores the architectural patterns for multi-agent applications using Pydantic AI, detailing how specialized agents can collaborate to solve complex tasks.

## 1. Overview of Multi-Agent Complexity

Pydantic AI defines five levels of complexity for agent-based systems, ranging from simple standalone entities to coordinated autonomous graphs.

| Level | Name | Description |
| :--- | :--- | :--- |
| **1** | **Single Agent** | A single agent with tools. Simple and predictable. |
| **2** | **Agent Delegation** | An agent calls another agent as a tool. Control returns to the caller. |
| **3** | **Programmatic Hand-off** | Application code manages switching between agents (e.g., using loops or conditionals). |
| **4** | **Graph-based Flow** | Complex workflows orchestrated by `pydantic-graph`. |
| **5** | **Deep Agents** | Autonomous agents capable of planning and recursive self-delegation. |

---

## 2. Agent Delegation (Level 2)

**Agent Delegation** occurs when a "Delegator" agent uses another "Delegate" agent as a tool. This is ideal when a sub-task requires a fundamentally different system prompt, model, or set of tools.

### How It Works
1. The Delegator agent has a tool function.
2. This tool function calls the `run()` (or `run_sync()`) method of the Delegate agent.
3. The Delegate performs its task and returns the result to the tool.
4. The Delegator receives the result and continues its reasoning.

### Implementation Pattern

```python
from pydantic_ai import Agent, RunContext
from dataclasses import dataclass

@dataclass
class Deps:
    api_key: str

researcher = Agent('openai:gpt-4o', system_prompt="You are a data researcher.")
writer = Agent('openai:gpt-4o', system_prompt="You are an expert technical writer.")

@writer.tool
async def research_topic(ctx: RunContext[Deps], topic: str) -> str:
    # Delegate the work to the researcher
    result = await researcher.run(
        f"Research the following: {topic}",
        deps=ctx.deps,
        usage=ctx.usage  # Track token usage across agents
    )
    return result.output

# Execution
result = await writer.run("Write a report on AI safety", deps=Deps(api_key="..."))
```

### Key Considerations
- **Usage Tracking**: Always pass `usage=ctx.usage` to have a unified view of tokens consumed by the entire chain.
- **Dependency Passing**: Pass the `RunContext` dependencies (`ctx.deps`) to delegates if they share the same resource pool.
- **Recursive Limits**: Be cautious of agents delegating back to themselves or creating infinite loops.

---

## 3. Programmatic Agent Hand-off (Level 3)

**Programmatic Hand-off** involves using Python logic to orchestrate agent execution. Instead of an agent deciding when to call another (delegation), the application code directs the flow.

### How It Works
- The application calls Agent A.
- Based on Agent A's output or program logic, the application then calls Agent B.
- Message history or specific data is passed manually between agents.

### Implementation Pattern

```python
from pydantic_ai import Agent, RunUsage

agent_a = Agent('openai:gpt-4o', system_prompt="Answer the user's question briefly.")
agent_b = Agent('openai:gpt-4o', system_prompt="Flesh out the answer with details.")

async def run_workflow(prompt: str):
    usage = RunUsage()
    
    # Step 1: Initial response
    result_a = await agent_a.run(prompt, usage=usage)
    
    # Step 2: Handoff with message history
    result_b = await agent_b.run(
        "Make this more comprehensive",
        message_history=result_a.all_messages(),
        usage=usage
    )
    
    return result_b.output
```

### When to Use
- When the flow depends on **business logic** that is too critical or rigid to leave to LLM uncertainty.
- When you need to **interrupt** the flow (e.g., for user confirmation) before proceeding to the next agent.
- When transitioning between completely different personas that shouldn't "hear" each other's entire internal monologue.

---

## 4. Advanced Patterns (Level 4 & 5)

### Level 4: Graph-based Control Flow
Uses the `pydantic-graph` library to define state machines or directed acyclic graphs (DAGs) of agents.
- **State Persistence**: The graph maintains persistent state across nodes.
- **Explicit Transitions**: Nodes (agents or functions) return instructions on which node to visit next.
- **Ideal For**: Multi-step workflows with loops, branching, and complex state management (e.g., a "Review -> Fix -> Re-review" loop).

### Level 5: Deep Agents
Deep Agents are autonomous entities that use "Planning" and "Reflection" loops.
- They often use a "Plan" tool to outline steps before execution.
- They may recursively spawn sub-agents to handle specific sub-problems identified during planning.
- **Focus**: Solving ambiguous, open-ended tasks with high autonomy.

---

## 5. Design Recommendations for `mem_graph`

For the `mem_graph` architecture, we should adopt the following:

1.  **Prefer Delegation for Discrete Tools**: If an orchestrator needs to "audit a package," it should delegate to a specialized `audit_agent` via a tool.
2.  **Use Programmatic Hand-off for Workflows**: The `WorkflowRegistry` and runtime should manage transitions between `Plan`, `Execute`, and `Verify` phases in Python code to ensure reliability.
3.  **Unified Usage Aggregation**: All agent calls within a single "Job" or "Task" must share a `RunUsage` instance to provide accurate billing and telemetry.
4.  **Context Scoping**: When delegating, decide whether the delegate needs the entire conversation history (`all_messages()`) or just a specific prompt. Usually, a clean prompt is better for specialized delegates.

---

## References
- [Multi-agent applications | Pydantic AI Docs](https://pydantic.dev/docs/ai/guides/multi-agent-applications/)
- [Agent Delegation](https://pydantic.dev/docs/ai/guides/multi-agent-applications/#agent-delegation)
- [Programmatic Agent Hand-off](https://pydantic.dev/docs/ai/guides/multi-agent-applications/#programmatic-agent-hand-off)
