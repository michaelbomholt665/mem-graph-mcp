To make your "God Stack" document a high-speed reference for your agent's code surgery, you should integrate these specific links from the Pydantic AI documentation. I've categorized them based on the specific "Brain + Muscle" architecture you've designed in your `.md` files.

### 1\. Core Workflow & Logic (The Brain)

Essential for your `pydantic-graph` and `pydantic-ai-slim` setup (Files `001` and `002`).

  * **[Pydantic Graph](https://www.google.com/search?q=https://pydantic.dev/docs/ai/pydantic_graph/)**: Since you're using this for ReAct nodes like `ContextGatherNode` and `SentryNode`, this is your primary reference for state management.
  * **[Agents](https://www.google.com/search?q=https://pydantic.dev/docs/ai/agents/)**: Fundamental guide on defining `Agent` instances, crucial for your `AgentFactory`.
  * **[Dependencies](https://www.google.com/search?q=https://pydantic.dev/docs/ai/dependencies/)**: Critical for your "Dependency Injection" pattern—how you'll pass `DatabaseConn` (Ladybug/DuckDB) into the agent context.

### 2\. Tools & Capability Management (The Muscle)

Essential for moving your tools into **Python-native Skills** (File `004`).

  * **[Toolsets](https://www.google.com/search?q=https://pydantic.dev/docs/ai/toolsets/)**: This is the "secret sauce" for your programmatic skills. It explains how to bundle multiple tools (like your Go binary wrappers) into a single reusable unit.
  * **[Capabilities](https://www.google.com/search?q=https://pydantic.dev/docs/ai/capabilities/)**: A high-level way to bundle tools, instructions, and hooks. This is perfect for your `go-cleaner` skill.
  * **[Function Tools](https://www.google.com/search?q=https://pydantic.dev/docs/ai/tools/)**: Deep dive into `@agent.tool` mechanics and how docstrings are parsed for LLM instructions.

### 3\. Integration & Observability

Essential for your Wails UI and your 32GB Linux performance tuning (Files `005`, `007`, `008`).

  * **[Debugging & Monitoring (Logfire)](https://www.google.com/search?q=https://pydantic.dev/docs/ai/logfire/)**: How to visualize the "Thought Stream" and instrument your Go/Python calls.
  * **[Model Context Protocol (MCP)](https://www.google.com/search?q=https://pydantic.dev/docs/ai/mcp/)**: Since you're using `fastmcp`, this explains how Pydantic AI natively interacts with those servers for tool discovery.
  * **[Streaming](https://www.google.com/search?q=https://pydantic.dev/docs/ai/streaming/)**: How to use `agent.run_stream()` to get that real-time "typing" effect in your Wails frontend.

### 4\. The "Agent Manual" (For the LLM)

Give these directly to your coding agent so it knows its own API limits and patterns:

  * **[llms.txt](https://www.google.com/search?q=https://pydantic.dev/docs/ai/llms.txt)**: A condensed version of the docs specifically formatted for AI consumption.
  * **[llms-full.txt](https://pydantic.dev/docs/ai/llms-full.txt)**: The entire documentation in one text file—best for deep architectural refactoring.

-----

### Implementation Tip for the Document

Add a **"Reference Appendix"** at the bottom of your `pydantic-upgrade.md`. When you start the surgery, prompt your agent with:

> *"Refer specifically to the **Toolsets** and **Capabilities** documentation to ensure the new Python-native skills in `src/mem_graph/agents/skills/` follow the v1.80+ standard."*

Since you have the "Planning & Self-Correction" design in file `003`, do you want me to extract the specific **Testing & Evals** links so the agent can verify its own refactoring work?

---

Based on your request to move from "random" `.md` files to a professional Python-native architecture, here is the updated section for your **God Stack Guide**.

This section specifically addresses how to consolidate instructions, scripts, and assets into single, type-safe Python modules.

-----

## 🛠️ Building Programmatic Skills (Python-Native)

Instead of scattering logic across `.md` and `.py` files, you define each capability as a **First-Class Skill Object**. This removes the "randomness" of file-based discovery and gives your agent (and your IDE) full type safety.

### 1\. The Single-Module Pattern

In your 32GB Linux setup, each skill lives in a dedicated file (e.g., `src/mem_graph/agents/skills/refactor.py`). Everything the agent needs—the "Soul" (instructions), the "Body" (scripts), and the "Memory" (references)—is contained in one importable unit.

```python
from pydantic_ai_skills import Skill, script
from pydantic import BaseModel

# 1. THE SOUL: Replaces SKILL.md (Instructions & Metadata)
go_refactor_skill = Skill(
    name="go-cleaner",
    description="Refactors Go code to resolve architectural smells.",
    instructions="""
    - Favor early returns to reduce indentation.
    - Check the DuckDB registry (Ladybug) for previous smell history.
    - If modifying 'main.go', always run the Go build binary to verify.
    """
)

# 2. THE BODY: Replaces scripts/ (Typed Execution Logic)
class RefactorInput(BaseModel):
    smell_id: str
    file_path: str

@go_refactor_skill.script()
async def apply_refactor(data: RefactorInput):
    """Applies a specific code refactor based on the smell ID."""
    # Logic to interface with your Go backend or local filesystem
    return {"status": "success", "modified": data.file_path}

# 3. THE MEMORY: Replaces references/ (Assets & Live Data)
# You can add static strings OR dynamic fetcher functions
go_refactor_skill.add_reference(
    "style-guide", 
    "Early returns reduce cognitive load by 30% in Go routines..."
)
```

### 2\. Benefits of Python-Native Skills

  * **Zero Randomness:** No more "hoping" the agent finds the right file. Skills are imported explicitly into your `AgentFactory`.
  * **IDE Support:** You get autocomplete, "Jump to Definition," and `mypy` validation across your entire toolset.
  * **Progressive Disclosure:** Even though it's code, the agent only "sees" the full script logic if the `instructions` trigger a need for it, saving your context window.
  * **Testability:** You can write standard `pytest` cases for your skill scripts without spinning up an LLM.

-----

## 🔗 Reference Links for Surgery

Add these to your `pydantic-upgrade.md` to give your agent the "Source of Truth" during the refactor:

**Core Concepts**

  * [Agents Overview](https://www.google.com/search?q=https://pydantic.dev/docs/ai/agents/) - How to define the primary brain.
  * [Dependency Injection](https://www.google.com/search?q=https://pydantic.dev/docs/ai/dependencies/) - How to pass your Go binaries/DuckDB into your skills.

**Skill & Tool Management**

  * [Toolsets](https://www.google.com/search?q=https://pydantic.dev/docs/ai/toolsets/) - The underlying engine for your programmatic skills.
  * [Capabilities](https://www.google.com/search?q=https://pydantic.dev/docs/ai/capabilities/) - The v1.71+ way to bundle tools and instructions into reusable units.
  * [Function Tools](https://www.google.com/search?q=https://pydantic.dev/docs/ai/tools/) - Deep dive into `@agent.tool` logic.

**Observability & UX (Wails Integration)**

  * [Logfire Instrumentation](https://www.google.com/search?q=https://pydantic.dev/docs/ai/logfire/) - Real-time tracing of skill execution.
  * [Streaming Responses](https://www.google.com/search?q=https://pydantic.dev/docs/ai/streaming/) - For the "typing" effect in your Go frontend.

### Final Task for your Agent:

When you hand this over to your agent, use this prompt:

> *"Using the **Python-Native Skills** section of this guide, refactor all existing tools in `src/mem_graph/tools/` into a new `src/mem_graph/agents/skills/` directory. Ensure every tool is wrapped in a `Skill` object with explicit Pydantic-typed inputs."*

Are you going to have the agent also migrate your **OpenTelemetry (OTel)** spans into the new Skill decorators?