# FastMCP 3.0 Upgrade & Feature Plan

This document outlines the strategy for upgrading the `syntx-memory` MCP server to leverage the full suite of features introduced in FastMCP 3.0.

## 1. Architectural Upgrades

### 1.1 Dependency Injection with `Depends()`
- **Goal:** Clean up manual service and DB connection retrieval.
- **Action:** 
    - Convert `get_conn()` to a dependency that can be injected into tools via `Depends(get_conn)`.
    - Create dependencies for services like `AuditDependencies`, `AuditReport`, and `Summarizer`.
    - Inject `httpx.AsyncClient` where needed.

### 1.2 Authentication & Authorization (Local-First)
- **Goal:** Maintain simplicity for local use while enabling granular control over tool access.
- **Action:**
    - Replace the custom `ApiKeyMiddleware` with FastMCP 3.0's built-in `StaticKeyAuthProvider` if `MEM_GRAPH_API_KEYS` is set.
    - **Authorization Scopes:** Use scopes to differentiate between "safe" (read-only) and "destructive" (write/delete) tools.
        - Example: `memory_store` gets `scope="memory:write"`, while `memory_recall` gets `scope="memory:read"`.
    - This allows a local user to run an agent with a "read-only" token for safety when exploring unfamiliar codebases.

### 1.3 Middleware & Telemetry
- **Goal:** Standardize request/response processing and leverage existing oTel.
- **Action:**
    - **OpenTelemetry:** oTel is already initialized in `main.py`. Ensure all FastMCP 3.0 components (tools, resources) are properly wrapped in spans for deep visibility.
    - **Middleware:** Use `@mcp.middleware` for logging and error handling.
    - **Pagination:** Enable `list_page_size` in the `FastMCP` constructor. This is critical for context management when listing large numbers of memories, tasks, or symbols (improves response latency and prevents context window overflow).

### 1.4 Lifespan & Background Tasks
- **Goal:** Formalize startup/shutdown and handle long-running operations.
- **Action:**
    - **Lifespan:** Transition to `mcp.on_startup` and `mcp.on_shutdown` for cleaner coordination.
    - **Background Tasks:** Use `task=True` for heavy operations like `audit_package`, `map_codebase`, and `triage_violations`.
        - **Lakehouse Integration:** As the Lakehouse project matures, use the Redis backend (`FASTMCP_DOCKET_URL`) for persistent, distributed task execution.

## 2. Feature Enhancements

### 2.1 Resources & Templates
- **Goal:** Enable LLMs to "read" data without always calling tools.
- **Action:**
    - **Memory:** Implement `memory://{memory_id}` and `memory://list?scope={scope}`.
    - **Work:** Implement `work://tasks/{task_id}`, `work://projects/{project_id}`, and `work://decisions/{decision_id}`.
    - **Audit:** Implement `audit://reports/{report_id}` to retrieve historical audit results.

### 2.2 Context-Aware Tools (The "Gift from Heaven")
- **Goal:** Improve real-time feedback and interactivity.
- **Action:**
    - **Progress Reporting:** Add `ctx.report_progress()` to all background-capable tools (`audit`, `map`, `triage`).
    - **Logging:** Use `ctx.info()`, `ctx.warn()`, etc., to pipe tool logs directly to the MCP client (e.g., Claude Code or Cursor).
    - **Sampling:** Integrate `ctx.sample_completions()` in the `audit_package` tool to allow the auditor agent to request peer reviews or clarification during analysis.
    - **User Elicitation:** Use `ctx.request_input()` for destructive operations or critical decisions.

### 2.3 Agent Boost: Skill Store
- **Goal:** Make the server "agent-heavy" by exposing specialized skills.
- **Action:**
    - **SkillsProvider:** Continue using `SkillsDirectoryProvider("skills")`.
    - **Skill Manifests:** Ensure every skill in `skills/` has a `SKILL.md` with proper YAML frontmatter (`description`, `version`).
    - **Dynamic Discovery:** Use `reload=True` during development so new skills are picked up instantly. This allows you to "hot-load" new agent personas or rule-sets without restarting the server.

### 2.4 "Apps" & UI Features (Rich Content)
- **Goal:** Provide a polished, visual experience in modern MCP clients.
- **Action:**
    - **Icons:** Add `Icon` objects to all tools and the server itself. Use the `Image` utility to embed local assets.
    - **Rich Content:** Ensure tools return multi-part content (text + images/diagrams) where appropriate. FastMCP 3.0 handles this natively, allowing for "Agentic UI" elements (like progress bars and rich tables) in supported clients.
    - **Website URL:** Provide a `website_url` to link to the documentation or the Lakehouse dashboard.

## 3. Tool Discovery & CodeMode Improvements

### 3.1 Tiered Visibility
- **Goal:** Keep the tool catalog lean while maintaining power.
- **Action:**
    - **Core Tools:** Keep `tools_activate`, `tools_search`, and `memory_recall` as always-visible core tools.
    - **Lazy Loading:** Use `mcp.disable(tags={...})` for all other namespaces.
    - **Discovery:** Refine `tools_search` to return not just the name, but the `Icon` and `Description` metadata from FastMCP 3.0.

### 3.2 CodeMode
- **Action:** Ensure `CodeMode` is active to allow agents to generate and execute Python logic that coordinates multiple tools (e.g., "Recall relevant memories, then audit this package, then store a new violation").

## 4. Implementation Phases

1. **Phase 1: Foundation (Context, DI & Pagination)**
    - Inject `Context` and `Depends(get_conn)`.
    - Implement `ctx.report_progress()` and enable pagination.
2. **Phase 2: Data & Skills (Resources & Skill Store)**
    - Implement Resource Templates.
    - Standardize the `skills/` directory structure.
3. **Phase 3: Interactivity (Sampling & Elicitation)**
    - Add sampling to the audit agent.
    - Add user confirmation for destructive actions.
4. Phase 4: Polish (Icons & Tasks)
    - Add icons and rich content returns.
    - Transition heavy tools to `task=True`.

5. Phase 5: Knowledge Graph Dashboard (The "Sidecar" UI)
    - **Goal:** Provide a visual, interactive dashboard of the Memory Graph, Jira tickets, and Codebase structure that runs alongside the CLI.
    - **Interactive Components (Prefab UI + AG-UI):**
        - **ForceGraph Visualization:** A zoomable, interactive graph representing:
            - **Memory Nodes:** Facts, preferences, and architectural patterns.
            - **Code Nodes:** Files and Symbols (functions/classes) extracted via `map_codebase`.
            - **Jira Nodes:** Tickets and epics fetched via a dedicated **Jira Embedder** service.
            - **Relationships:** `AFFECTS`, `IMPLEMENTS`, `MENTIONS`, and `RESOLVES`.
        - **Jira Code Embedder (On-Demand):** A specialized tool to search and link Jira tickets. 
            - **Model:** `hf.co/jinaai/jina-embeddings-v4-text-code-GGUF:Q5_K_M` (~1.9GB).
            - **VRAM Fallback:** If VRAM usage is excessive, fall back to `IQ4_NL` variant.
            - **VRAM Management:** Model is **lazy-loaded** via Ollama only upon first use. 
            - **Auto-Unload:** Implements a TTL (Time-To-Live) mechanism to stop the model and free VRAM after 5 minutes of inactivity.
            - **Manual Control:** `tools_deactivate(namespace='jira')` explicitly stops the model.

        - **File Explorer Tab:** A `TreeView` component to browse the audited codebase with inline markers for violations and memories.
    - **Workflow:** The user runs `fastmcp dev apps` to open this visual "Command Center." As the agent audits code in the CLI, the graph updates in the browser to show new violations linked to their corresponding source files and Jira tasks.

