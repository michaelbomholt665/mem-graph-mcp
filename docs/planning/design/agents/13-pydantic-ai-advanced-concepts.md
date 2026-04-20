# Pydantic AI: Message History, Advanced Tools, and Toolsets

This document provides a comprehensive technical overview of advanced features in Pydantic AI, focusing on state management (Message History), sophisticated tool behaviors (Advanced Tools), and modular capability management (Toolsets).

---

## 1. Message History

Message history is the primary mechanism for maintaining state and context across multiple interactions in Pydantic AI. It is built upon a sequence of `ModelMessage` objects.

### 1.1 Core Message Structure
Pydantic AI uses several message types to represent the dialogue:

- **`ModelRequest`**: Represents messages sent *to* the model.
  - Contains `parts` (e.g., `UserPromptPart`, `SystemPromptPart`).
- **`ModelResponse`**: Represents messages received *from* the model.
  - Contains `parts` (e.g., `TextPart`, `ToolCallPart`).
- **`ToolReturnPart`**: Represents the result of a tool execution, sent back to the model in a subsequent `ModelRequest`.

### 1.2 Accessing History
After running an agent, history can be retrieved from the `run` result:

- `result.new_messages()`: Returns only the messages generated in the most recent turn (typically a `ModelRequest` and a `ModelResponse`).
- `result.all_messages()`: Returns the complete history, including any messages passed into the `run()` method.

### 1.3 Persistence and Serialization
For long-term storage (e.g., in Ladybug DB), messages must be serialized to JSON. Pydantic AI provides a built-in adapter for this:

```python
from pydantic_ai.messages import ModelMessagesTypeAdapter
import json

# Serialize
messages_json = ModelMessagesTypeAdapter.dump_json(result.all_messages())

# Deserialize
history = ModelMessagesTypeAdapter.validate_json(messages_json)
```

### 1.4 Continuing a Conversation
To maintain context, pass the accumulated history back into the `run()` method:

```python
result = await agent.run("What was my last question?", message_history=previous_messages)
```

> [!NOTE]
> If `message_history` is provided and is not empty, Pydantic AI **skips** generating new system prompts by default, as it assumes the history already contains the necessary context.

---

## 2. Advanced Tool Features

Advanced tools allow for dynamic control, rich outputs, and self-correction patterns.

### 2.1 Dynamic Tool Availability (`prepare`)
Tools can decide at runtime whether they should be available to the model or modify their own metadata. This is done via the `prepare` parameter in `@agent.tool` or the `prepare` method on a `Tool` instance.

```python
async def prepare_database_tool(ctx: RunContext[MyDeps], tool: Tool) -> Tool | None:
    if not ctx.deps.db_connected:
        return None  # Tool will not be visible to the model
    return tool

@agent.tool(prepare=prepare_database_tool)
def query_db(ctx: RunContext[MyDeps], query: str):
    ...
```

### 2.2 Rich Returns (`ToolReturn`)
Tools can return more than just strings. `ToolReturn` allows sending multimodal data (images, audio) and structured metadata back to the model.

```python
from pydantic_ai.tools import ToolReturn

@agent.tool
def capture_screenshot(ctx: RunContext[MyDeps]) -> ToolReturn:
    image_data = ... 
    return ToolReturn(
        content=[image_data],
        tool_output="Screenshot captured successfully."
    )
```

### 2.3 Model Self-Correction (`ModelRetry`)
If a model provides invalid arguments to a tool, you can raise `ModelRetry` to force the model to correct its input and try again.

```python
from pydantic_ai.exceptions import ModelRetry

@agent.tool
def set_age(ctx: RunContext[MyDeps], age: int):
    if age < 0:
        raise ModelRetry("Age cannot be negative. Please provide a valid age.")
    ...
```

### 2.4 Tools from JSON Schema
You can define tools using existing JSON schemas, which is useful for integrating with external systems or pre-defined API specifications.

```python
from pydantic_ai.tools import Tool

my_tool = Tool.from_schema(
    name="my_external_api",
    description="Calls an external API",
    parameters_schema={...}
)
```

---

## 3. Toolsets

Toolsets provide a modular way to group and register multiple tools simultaneously, facilitating cleaner architecture and reusability.

### 3.1 FunctionToolsets
A `FunctionToolset` is a class where methods decorated with `@tool` are automatically registered as tools.

```python
from pydantic_ai.tools import FunctionToolset, tool

class FileSystemTools(FunctionToolset):
    @tool
    def read_file(self, path: str):
        ...

    @tool
    def write_file(self, path: str, content: str):
        ...
```

### 3.2 Toolset Instructions
Toolsets can include `@instructions` (static or dynamic) that are appended to the model's system prompt when the toolset is active.

```python
from pydantic_ai.tools import instructions

class DatabaseTools(FunctionToolset):
    @instructions
    def db_instructions(self):
        return "Only use these database tools if the user specifies a 'read' operation."
    
    @tool
    def read_record(self, id: str):
        ...
```

### 3.3 Composition and Registration
Toolsets can be registered during agent initialization or passed dynamically to individual runs.

```python
# During Init
agent = Agent(..., toolsets=[FileSystemTools()])

# During Run
result = await agent.run("...", toolsets=[DatabaseTools()])
```

### 3.4 Benefits of Toolsets
- **Encapsulation**: Group related logic together.
- **Shared Context**: Instructions ensure the model knows *how* and *when* to use the tool group.
- **Dynamic Configuration**: Easily swap functionality blocks based on the user's intent or current workflow stage.
