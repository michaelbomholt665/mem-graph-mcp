# Audit Agent Implementation Plan

The objective is to introduce a Pydantic AI-powered "Audit Agent" to the `memory` MCP server. The agent will perform codebase audits by evaluating a package against its active guidelines, evolving the living package prompts (e.g., `{packagename}.guide.md`), and registering new coding violations in a centralized `smell-registry.md`.

For the initial target, it will audit the `lakehouse/internal/managers/database/` package and modify the following files:
1. `database.guide.md`
2. `smell-registry.md`

## Architecture Integration
We will use `openai:gpt-4o` as the core agent brain, but since this runs under FastMCP, you could dynamically point it at Ollama if preferred.

## Proposed Changes

### Configuration
#### [MODIFY] pyproject.toml
- Add `pydantic-ai` to the `dependencies` array.

---

### Core Agent Logic
#### [NEW] src/mem-graph/agents/audit_agent.py
This file contains the Pydantic AI agent setup (`pydantic_ai.Agent`).
- **Instructions**: The agent is instructed using the rules defined in `SKILL.md` (e.g., "Write corrective behavior, not the complaint", "Keep markdown as prompt surface", "Prefer one stable smell_id per normalized violation class").
- **Dependencies (`RunContext`)**: Accepts `database.guide.md` content, `smell-registry.md` content, and the source code being audited.
- **Output (`pydantic.BaseModel`)**: We use structured Pydantic output to guarantee the agent returns well-formatted diffs or full drop-in replacements for the updated `database.guide.md` and `smell-registry.md`.
- **Tools**: Provide agent-level tools (`@audit_agent.tool`) letting it inspect specific Go files dynamically within the package being audited using `list_package_files` and `read_file`.

---

### FastMCP Tool Exposure
#### [NEW] src/mem-graph/tools/audit.py
Creates the FastMCP interface for you to trigger the audit.
- Exposes an `@mcp.tool()` named `audit_package`.
- Takes `package_path` as a parameter.
- The tool acts as a bridge: it reads the local `*.guide.md` and the `smell-registry.md`, executes the Pydantic AI agent natively, and then applies the structured updates back to the filesystem directly.

#### [MODIFY] src/mem-graph/server.py
- Mounts `audit.mcp` and wires it up to the `tools_activate` gateway.

## Testing & Verification 
- `tests/test_audit.py` provides dry-run checks over the agent prompt structure using `pydantic-ai`'s `TestModel` to dry-run the tool without making live API calls.
