# Implementation Plan: Recursive Autopilot Agent Suite (v1.0)

This document provides the technical requirements and orchestration logic for implementing the specialized agent suite within the `mem-graph` system.

## 1. Core Objectives
*   **Specialized Pairs:** Implement 3 pairs of Coder/Debugger agents (Go, Python, TypeScript) + 1 Test Architect.
*   **Deterministic Orchestration:** Use `pydantic-graph` to enforce a **Think-Decide-Build/Drop** workflow.
*   **Strict Standards:** Enforce 2-3 token function naming, feature prefixing, and 1-2 concerns per package.
*   **Manifest Guard:** Ensure no packages are ever auto-installed; read `go.mod`, `pyproject.toml`, and `package.json` for context.

## 2. Global Constraints (All Agents)
*   **Strict Token Naming Convention:**
    *   **2-3 Tokens:** All functions MUST have 2 or 3 tokens (e.g., `GetUserData`, `ProcessOrderQueue`). NO single-word functions.
    *   **Feature Prefixing:** Functions MUST be prefixed by their primary feature (e.g., `DatabaseConnectPool`, `AuthVerifyToken`).
*   **Manifest Guard:** ALWAYS read `pyproject.toml`, `go.mod`, or `package.json` before proposing changes. NO auto-installs.
*   **Syntx Rule:** Enforce "1-2 Concerns per Package." Root files (`__init__.py`, `doc.go`, `index.ts`) are for orchestration/docs only.

## 3. The Agent Suite

| Agent | Language/Role | Tooling & Standards | Key Directive |
|---|---|---|---|
| **Sentry** | Test Architect | `testify`, `pytest`, `vitest` | Draft "Red" failing tests before any code is written. |
| **Go Mechanic** | Go 1.25.4 | `gofumpt`, `golangci-lint`, `govulncheck` | PascalCase exports, `doc.go` mandatory, explicit errors. |
| **Python Mechanic**| Python 3.13.7 | **RUFF IS MANDATORY**, `uv`, `mypy` | Shebang + Path header, Google-style docstrings, `__init__.py`. |
| **TS Mechanic** | TS 5.9.2 | `pnpm`, `tsc`, `vitest` | `index.ts` exports only, TSDoc mandatory, no `any`. |
| **Refiners** | Debuggers (x3) | Language-specific tools | Surgical remediation of linter/test failures without side effects. |

## 4. Orchestration: `pydantic-graph` Nodes

1.  **`AgentRouterNode`**: Intent classification and model tier selection.
2.  **`ReasoningNode` (Think)**: Analyzes memory graph and proposes a Strategy.
3.  **`CritiqueNode` (Decide)**: Validates Strategy against "1-2 Concerns" and "2-3 Token Naming" rules.
    *   **Decision:** `Return ReasoningNode()` (Drop/Backtrack) or `Return SentryNode()` (Build/Proceed).
4.  **`SentryNode` (Build Tests)**: Calls Test Architect to write failing ("Red") tests.
5.  **`MechanicNode` (Build Code)**: Calls Coding Agent to write functional ("Green") logic.
6.  **`GuardNode` (Deterministic Validation)**: Executes `ruff`, `golangci-lint`, `go test`, `vitest`.
7.  **`RefinerNode` (Fix)**: If `GuardNode` fails, calls Debugging Agent with specific error context.
8.  **`ScribeNode` (Finalize)**: Finalizes documentation (headers, `doc.go`, `__init__.py`).

## 5. Shared State Model
```python
class AutopilotState(BaseModel):
    language: Literal['go', 'python', 'typescript']
    tier: Literal['XHigh', 'Medium', 'Mini', 'Fast']
    strategy: str | None = None
    tests_red: bool = False
    code_path: str | None = None
    linter_output: str | None = None
    retry_count: int = 0
    max_retries: int = 3
    manifest_context: dict = {} # Content of go.mod / package.json / pyproject.toml
```

## 6. Embedding Infrastructure (Ollama Optimization)
Refactor `src/mem_graph/embeddings.py` to align with Pydantic AI's `Embedder` interface:
*   **Provider Shorthand:** Use `ollama:<model>` for automatic provider detection.
*   **Interface Split:** Implement `embed_query()` (search-optimized) and `embed_documents()` (index-optimized).
*   **Context Safety:** Set `truncate=True` in `EmbeddingSettings` to prevent errors on long documents.
*   **Preserve Cache:** Maintain the existing LRU cache and dimension validation (`EMBED_DIM`) as a "Guard" layer around the new `Embedder`.
*   **Dependency:** Ensure `pydantic-ai` is the primary driver for embedding calls, keeping the file as the single "swap point."

## 7. Hybrid Search & RAG Optimization
Upgrade the retrieval system to use Hybrid Search (Semantic + Keyword) for maximum precision:
*   **FTS Indexing:** Create Full-Text Search (FTS) indexes in `db.py` / `schema/` using the following Cypher commands:
    *   `CALL fts.create_index('Memory', 'fts_memory_content', ['content']);`
    *   `CALL fts.create_index('Note', 'fts_note_body', ['body', 'title']);`
    *   `CALL fts.create_index('Task', 'fts_task_desc', ['description', 'title']);`
    *   `CALL fts.create_index('Decision', 'fts_decision_rat', ['rationale', 'title']);`
    *   `CALL fts.create_index('Violation', 'fts_violation_desc', ['description']);`
    *   `CALL fts.create_index('CodeSymbol', 'fts_symbol_name', ['name', 'signature']);`
*   **Retrieval Logic:** Update `memory_recall` and related search tools to execute both `QUERY_VECTOR_INDEX` and `CALL fts.search(...)`.
*   **Fusion Strategy:** Implement Reciprocal Rank Fusion (RRF) or a weighted scoring mechanism to merge vector and keyword results into a single ranked list.
*   **Hardware Efficiency:** Since FTS is local/deterministic, it reduces the "Ollama tax" for simple keyword lookups that don't require semantic embedding.

## 8. User-Initiated Chat & Retrieval Agent
Implement a specialized Chat Agent to serve as the user's window into the memory graph:
*   **Interface:** A dedicated CLI command (e.g., `syntx chat`) or persistent UI session that the user explicitly starts.
*   **Role:** Acts as a "Memory Librarian." It does not modify code unless explicitly asked but excels at retrieving, summarizing, and explaining project history.
*   **Capabilities:**
    *   **Contextual RAG:** Uses the new Hybrid Search to ground answers in the memory graph.
    *   **Graph Traversal:** Follows relationships (e.g., "Find the Decision that caused this Violation") to provide deep architectural context.
    *   **User Ownership:** This agent is strictly user-initiated to prevent background token consumption. It serves the user's curiosity and planning phases.
*   **AI Usage:** While primarily for the user, other agents (like the Router) can "hand off" complex inquiry-only tasks to this agent to leverage its specialized retrieval logic.

