# Agent Component Documentation

## Purpose
This document explains the Syntx Memory MCP Agent component - autonomous agents that interact with the server and tools to perform work, make decisions, and manage state while leveraging the memory capabilities of the system.

## Overview
The agent system is designed around the Pydantic AI framework and is exemplified by the Audit Agent in `src/syntx_mcp/agents/audit_agent.py`. Agents encapsulate:
- Decision-making logic through LLM prompts and tool usage
- State management through dependencies and context
- Interaction with MCP server tools via standardized interfaces
- Error handling and recovery mechanisms

While the current codebase shows one specialized agent (Audit Agent), the pattern is designed to be extensible for other agent types.

## Agent Lifecycle

### Initialization
Agents are initialized with:
1. **Model Specification** - LLM to use (e.g., `'openai:gpt-4o'` in Audit Agent)
2. **Dependencies Type** - Typed dataclass defining required context
3. **Result Type** - Pydantic model defining expected output
4. **System Prompt** - Core instructions and domain knowledge
5. **Tool Definitions** - Functions the agent can invoke

In `audit_agent.py`:
```python
audit_agent = Agent(
    'openai:gpt-4o',
    deps_type=AuditDependencies,
    result_type=AuditOutput,
)
```

### Dependencies Pattern
Agents receive typed dependencies through `RunContext[Deps]`:
```python
@dataclass
class AuditDependencies:
    package_path: str
    guide_path: str
    registry_path: str
    skills_content: str
```

Dependencies are passed when running the agent:
```python
async with audit_agent.run_stream(prompt, deps=deps) as result:
```

### Execution Flow
1. **Prompt Processing** - System prompt combines static instructions with dynamic dependencies
2. **Tool Invocation** - Agent decides which tools to call based on context
3. **Result Collection** - Agent aggregates tool outputs and formulates final response
4. **Output Validation** - Result validated against `result_type` Pydantic model

### Audit Agent Specific Lifecycle
1. Load current guide and registry contents into context
2. Browse source files in target package
3. Identify recurring violation patterns
4. Use `update_registry` to add new smell definitions
5. Use `update_guide` to evolve package guidelines
6. Return summary of actions taken

## Decision Logic

### System Prompt Engineering
The agent's behavior is primarily shaped by its system prompt, which in Audit Agent includes:
- Role definition ("You are an Audit Agent")
- Domain knowledge (loaded skills content)
- Context information (package paths, file contents)
- Current guidelines and smell registry
- Numbered objectives with specific actions

### Tool Selection Logic
Agents decide which tools to invoke based on:
1. **Explicit Instructions** in system prompt (e.g., "Use `update_registry` to add it")
2. **Context Awareness** - accessing file contents through dependencies
3. **Goal-Oriented Reasoning** - working toward objectives defined in prompt
4. **Observation of State** - checking what's already been done

In Audit Agent, the decision flow is:
1. List files → Read files → Identify patterns → Update registry → Update guide → Summarize

### State Machine Characteristics
While not explicitly implemented as a formal state machine, agents exhibit state-like behavior through:
- **Progress Tracking** - What files have been examined
- **Discovered Knowledge** - What smells have been identified
- **Completed Actions** - Which updates have been made
- **Remaining Work** - What objectives are still pending

## Interaction with Server/Tools

### MCP Tool Invocation
Agents interact with the MCP server through tool calls that are:
1. **Exposed via @agent.tool decorators** - Each method becomes an invokable tool
2. **Automatically Serialized** - Arguments and return values handled by framework
3. **Context-Aware** - Receive `RunContext` for accessing dependencies
4. **Error Handling** - Exceptions propagated back to agent for reasoning

### Current Agent-Tool Integration
The Audit Agent demonstrates indirect tool interaction:
1. Agent runs autonomously using its own file reading/tools
2. Agent's `audit_package` tool (exposed via MCP) invokes the agent
3. Agent uses its internal tools (list_package_files, read_file, etc.)
4. Agent calls MCP-exposed tools via `update_guide` and `update_registry`

This creates a layered interaction:
```
MCP Client 
    → audit_package tool (MCP)
        → Audit Agent (Pydantic AI)
            → Internal tools (list/read/update)
                → MCP tools (update_guide/update_registry via tools)
                    → Server → Database
```

## State Management

### Dependency-Based State
Dependencies passed via `RunContext` provide:
- Immutable configuration (package paths)
- Mutable references (file contents loaded in prompt)
- Static resources (skills content)

### Working Memory
Agents maintain working memory through:
- Local variables in tool implementations
- Accumulated results from sequential tool calls
- Context updates between prompt executions

### Persistent State via MCP
Long-term state is stored in the MCP server database:
- Audit findings eventually stored as violations/notes
- Guide and registry updates persisted to filesystem
- Agent actions could be stored as conversation/memory entries

## Error Recovery

### Tool-Level Error Handling
Individual tools catch exceptions and return error strings:
```python
try:
    # tool operation
except Exception as e:
    return f"Error: {e}"
```

### Agent-Level Error Handling
The audit.py tool wrapper catches agent execution failures:
```python
try:
    async with audit_agent.run_stream(...) as result:
        # process result
except Exception as e:
    return f"Audit execution failed: {e}"
```

### Retry and Fallback Strategies
Current implementation shows:
- No automatic retries in agent tools
- Graceful degradation in conversation summarization (placeholder on Ollama failure)
- Explicit error propagation for user notification

## Decision Flow Example (Audit Agent)

### Objective-Oriented Processing
1. **Initialization** 
   - Load guide, registry, skills into context
   - Construct detailed system prompt with all context

2. **Exploration Phase**
   - Invoke `list_package_files` to get target files
   - For each file, invoke `read_file` to examine contents

3. **Analysis Phase**
   - Compare contents against current guidelines (in prompt)
   - Identify patterns suggesting new violation classes

4. **Action Phase**
   - For each new pattern:
     - Generate smell ID and description
     - Invoke `update_registry` to persist new smell
     - Generate guideline text
     - Invoke `update_guide` to incorporate new detection

5. **Completion Phase**
   - Formulate summary of actions taken
   - Return structured output validated against AuditOutput

## Extensibility Patterns

### Adding New Agent Types
To create a new agent following the same pattern:
1. Create `<agent_name>.py` in `src/syntx_mcp/agents/`
2. Define dependencies dataclass
3. Define result Pydantic model
4. Instantiate Agent with model, deps_type, result_type
5. Add system_prompt decorator with instructions
6. Add tool decorators for agent capabilities
7. Expose agent functionality via MCP tool in `tools/` if needed

### Tool Exposure Choices
Agents can expose functionality through:
1. **Direct MCP Tools** - Wrap agent execution in `@mcp.tool()` (like audit_package)
2. **Indirect Interaction** - Agent uses MCP tools internally (future pattern)
3. **Hybrid Approach** - Some capabilities direct, others mediated

## Code References
- Audit Agent Implementation: `src/syntx_mcp/agents/audit_agent.py`
- Agent Tool Exposure: `src/syntx_mcp/tools/audit.py`
- Agent Interface: `src/syntx_mcp/agents/__init__.py`
- Dependencies: Pydantic AI framework (imported as `pydantic_ai`)
- Model Provider: OpenAI GPT-4o (configurable via agent initialization)

## Assumptions and Notes
- Current implementation shows one specialized agent (Audit Agent)
- Pattern is designed for extension to other agent types (coding, planning, etc.)
- Agents currently interact with MCP server primarily through file-based tools
- Future iterations may deepen agent/MCP tool integration
- LLM provider is hardcoded in current agent but could be made configurable
