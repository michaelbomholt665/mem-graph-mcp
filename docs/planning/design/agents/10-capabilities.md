# Agent Capabilities

Capabilities are the primary extension mechanism for Pydantic AI. They allow us to bundle related agent behaviors—tools, system instructions, model settings, and lifecycle hooks—into a single, reusable, and composable class.

## Overview

In `mem_graph`, we often have logic that is reused across multiple agents (e.g., memory access, audit logging, or safety checks). Instead of passing individual tools and strings to every agent constructor, **Capabilities** allow us to package these as a single "Skill" or "Feature".

> [!TIP]
> **Capabilities vs. Tools**: A Tool is a single function an agent can call. A Capability is a higher-order component that can provide multiple tools, define its own instructions, and even wrap the agent's internal execution loop using hooks.

---

## What Capabilities Provide

A class inheriting from `pydantic_ai.capabilities.AbstractCapability[StateT]` can override several core behaviors:

1.  **Instructions**: Bundle static or dynamic system prompts (via `get_instructions()`).
2.  **Toolsets**: Provide a related set of tools (via `get_toolset()`).
3.  **Model Settings**: Define default temperature, top_p, or provider-specific settings (via `get_model_settings()`).
4.  **Lifecycle Hooks**: Monitor and modify agent execution at various stages:
    - `on_run_start` / `on_run_end`
    - `on_node_start` / `on_node_end`
    - `wrap_node_run` (interact with the internal graph execution)
    - `on_tool_call_start` / `on_tool_error`

---

## Why Use Capabilities in `mem_graph`?

### 1. Modular Skills
We can package the "Audit" logic as a capability. An agent with `AuditCapability` automatically gets the audit tools, the auditor persona instructions, and any necessary audit-specific logging hooks.

### 2. Provider Adaptation
Capabilities can detect which model provider is being used and adjust the tools or prompting style accordingly. This is critical for supporting multiple backends (OpenAI, Anthropic, Ollama).

### 3. Observability and Safety
By using the `wrap_node_run` or `on_tool_call_start` hooks, we can implement global safety filters, usage tracking, or "Reflection" patterns that apply across all agents assigned that capability.

---

## Implementation Example

```python
from dataclasses import dataclass
from pydantic_ai import RunContext, Agent
from pydantic_ai.capabilities import AbstractCapability

@dataclass
class MemoryCapability(AbstractCapability[None]):
    """Provides semantic memory tools and enforces a reasoning protocol."""

    def get_instructions(self) -> str:
        return "Always check memory before making a decision."

    def get_toolset(self) -> list:
        return [self.search_memory]

    async def search_memory(self, ctx: RunContext[None], query: str):
        """Search the agent's semantic memory graph."""
        # implementation...
        return ["Memory result 1", "Memory result 2"]

    async def on_run_start(self, ctx: RunContext[None]):
        print("Agent run starting with Memory Capability active.")

# Usage
agent = Agent('openai:gpt-4o', capabilities=[MemoryCapability()])
```

---

## Design Pattern: Capability Injection

In `mem_graph`, we should prefer **Capabilities** over direct tool registration when the following are true:
- The tools require specific system instructions to be used correctly.
- We need to monitor the start/end/errors of those specific tools.
- The feature should be easily "toggled" on or off for different agent instances.

## Core Lifecycle Hooks Reference

| Hook | Purpose |
| :--- | :--- |
| `on_run_start` | Initialize state or resources at the start of an agent run. |
| `wrap_node_run` | Wrap the internal graph node execution (Prompt -> Model -> Tool). |
| `on_tool_call_start` | Inspect or modify arguments before a tool is executed. |
| `on_tool_error` | Centralized error recovery or logging for capability tools. |
| `on_run_end` | Finalize reports or persist state after the run completes. |
