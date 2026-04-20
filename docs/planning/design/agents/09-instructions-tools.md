# Agent Instructions (@agent.instructions)

This document formalizes the usage of the `@agent.instructions` pattern in the `mem_graph` agent system. It explains why this pattern is a "direct token saver" and how to implement it to leverage model-level prompt caching.

## Overview

In Pydantic AI, `@agent.instructions` is a mechanism for providing system-level guidance to an agent. While it shares some similarities with `@agent.system_prompt`, it differs fundamentally in how it is delivered to the Large Language Model (LLM).

> [!TIP]
> **Token Saving**: Unlike system prompts, instructions are **never** added to the message history. This means in a multi-turn conversation, the system-level instructions are sent exactly once as context, rather than being repeated in every message pair.

---

## What It Does

1.  **Deduplication**: By keeping instructions out of the message history, Pydantic AI ensures that the model doesn't "re-read" the system prompt as part of the conversation logs.
2.  **Stable Prefixing**: Instructions (especially static ones) are sorted and placed at the absolute start of the request. This makes the prompt highly predictable, which is essential for **Prompt Caching**.
3.  **Context Isolation**: In multi-agent scenarios (e.g., an Orchestrator calling an Audit agent), only the instructions belonging to the *currently active* agent are sent to the model. This prevents the "instruction bleed" where one agent's role interferes with another's.

---

## When to Use It

| Feature | `@agent.system_prompt` | `@agent.instructions` |
| :--- | :--- | :--- |
| **History Injection** | Yes (repeated in history) | No (context only) |
| **Prompt Caching** | Low (changes with history) | High (stable prefix) |
| **Dynamic Context** | Excellent (`RunContext`) | Excellent (`RunContext`) |
| **Recommended Use** | Legacy / Single-turn | **Default for all agents** |

---

## How to Use It

There are two primary ways to provide instructions: **Static** and **Dynamic**.

### 1. Static Instructions (Constructor)
Static instructions are provided when the agent is initialized. These are the best for caching because they never change.

```python
from pydantic_ai import Agent

# Static role and mission
audit_agent = Agent(
    "openai:gpt-4o",
    instructions="You are a security auditor. Focus on SQL injection and XSS."
)
```

### 2. Dynamic Instructions (@agent.instructions)
Use the decorator when instructions need to adapt based on runtime dependencies (`RunContext`).

```python
@audit_agent.instructions
async def add_project_context(ctx: RunContext[AuditDeps]) -> str:
    return f"The current project root is {ctx.deps.package_path}."
```

### 3. Multiple Instructions
You can stack multiple instruction decorators. Pydantic AI will concatenate them in the order they are defined.

```python
@agent.instructions
def base_mission():
    return "Mission: Analyze code quality."

@agent.instructions
def specific_rules(ctx: RunContext[Deps]):
    return f"Active Rules: {ctx.deps.rule_ids}"
```

---

## Implementation Strategy for `mem_graph`

To maximize token efficiency across the `mem_graph` platform, we should adopt the following convention:

1.  **Constructors**: All `Agent` definitions should include a static `instructions` argument containing the **Persona** (Who am I?) and the **Workflow** (What are my steps?).
2.  **Decorators**: Use `@agent.instructions` to inject **Session Data** (Package Paths, Project IDs, Rulesets).
3.  **Deprecation**: Phase out `@agent.system_prompt` entirely to ensure that system-level guidance does not pollute the conversation history during long-running orchestrations.

---

## Benefits Summary

- **Lower Latency**: Cached prompts process significantly faster.
- **Lower Cost**: Reduced token count in the history directly translates to lower API bills.
- **Higher Accuracy**: By keeping the message history "clean" of repetitive system prompts, the model can maintain a higher effective context length for the actual codebase content.
