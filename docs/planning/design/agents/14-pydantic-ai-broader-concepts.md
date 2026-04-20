# Pydantic AI: Broader System Concepts

This document explores the foundational "plumbing" of Pydantic AI, detailing the dependency injection system, varied execution modes, operational safeguards, and testing infrastructure.

---

## 1. Dependency Injection & Type Safety

Pydantic AI uses a strictly typed dependency injection system to ensure that tools, prompts, and result validators have access to the services they need (e.g., database connections, API clients).

### 1.1 Typed Agents
Agents are generic over their dependencies and output types:
```python
from dataclasses import dataclass
from pydantic_ai import Agent

@dataclass
class MyDeps:
    db: DatabaseConnection
    api_key: str

# agent[Deps, Output]
agent = Agent('openai:gpt-4o', deps_type=MyDeps, result_type=MyOutput)
```

### 1.2 RunContext
The `RunContext` object is the bridge between the agent's execution loop and your dependencies. It is passed to tools, system prompt functions, and result callbacks.

```python
@agent.tool
def get_user_data(ctx: RunContext[MyDeps], user_id: str):
    return ctx.deps.db.get_user(user_id)
```

---

## 2. Execution Strategy

Pydantic AI provides several ways to execute an agent, depending on whether you need a final result, a stream of tokens, or a detailed audit trail.

### 2.1 Atomic Runs
- `agent.run()`: Asynchronous execution, returns a `RunResult`.
- `agent.run_sync()`: Synchronous wrapper for standard Python environments.

### 2.2 Result Streaming (`run_stream`)
Allows consuming the model's final response as it is generated. This is useful for UI responsiveness.

```python
async with agent.run_stream("Tell me a long story") as result:
    async for text in result.stream_text():
        print(text)
```

### 2.3 Event Streaming (`run_stream_events`)
Provides the highest level of detail. It streams `AgentStreamEvent` objects, which include:
- `ModelRequest`: When the model is about to be called.
- `CallTool`: When a tool call is initiated.
- `ToolResult`: When a tool returns a value.
- `TextDelta`: Individual chunks of text from the model.

### 2.4 Iterative Execution (`iter`)
For low-level control or debugging, `agent.iter()` allows you to manually step through each turn of the agent's internal state machine.

---

## 3. Operational Safeguards

To prevent runaway costs and ensure reliable behavior, Pydantic AI includes built-in safety controls.

### 3.1 Usage Limits
Cap the total number of requests or tokens consumed in a single execution.
```python
from pydantic_ai.usage import UsageLimits

limits = UsageLimits(request_limit=5, request_tokens_limit=1000)
result = await agent.run("...", usage_limits=limits)
```

### 3.2 Model Settings
Consistent configuration across all supported model providers.
```python
from pydantic_ai.settings import ModelSettings

settings = ModelSettings(
    temperature=0.7,
    max_tokens=500,
    timeout=30.0,
    stop_sequences=["END"]
)
result = await agent.run("...", model_settings=settings)
```

---

## 4. Observability with Logfire

Pydantic AI is "observable by default" through native integration with Pydantic Logfire.

### 4.1 Instrumentation
A single line of code instruments the entire framework:
```python
import logfire
logfire.instrument_pydantic_ai()
```

### 4.2 Depth of Coverage
Logfire traces capture:
- Nested tool calls and their arguments.
- Model latency and token usage.
- Validation failures and automatic retries.
- Full prompt history (if configured).

---

## 5. Testing & Mocking Infrastructure

The framework provides robust tools for testing agents without making expensive or non-deterministic API calls.

### 5.1 Dependency Overrides
Use `agent.override()` to replace production dependencies with mocks in test suites.

### 5.2 Mock Models
- **`TestModel`**: Returns static, pre-defined results based on the requested output type.
- **`FunctionModel`**: Allows you to define custom Python logic that acts as the model, perfect for testing complex multi-turn logic or tool-calling orchestration.

```python
from pydantic_ai.models.test import TestModel

agent = Agent(TestModel())
result = await agent.run("test")
assert result.data == "mock response"
```

---

## 6. Structured Output & Multimodal Inputs

### 6.1 Validation & Retries
When a model returns data that doesn't match the `result_type` Pydantic model, Pydantic AI automatically sends the validation error back to the model for a retry (up to `max_result_retries`).

### 6.2 Multimodal Data
Unified classes for passing `Image`, `Audio`, `Video`, and `Document` data to supporting models. These are handled as parts in the `ModelRequest`.
