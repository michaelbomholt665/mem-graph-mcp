# Agent Directives & Tooling Standards (v1.0)

This document defines the behavioral directives and technical guardrails for the specialized agent suite. These agents operate within the Recursive Autopilot Workflow.

## 1. Global Constraints (All Agents)
*   **Manifest Guard:** ALWAYS read `pyproject.toml`, `go.mod`, or `package.json` before proposing changes.
*   **No Auto-Install:** Agents MUST NOT execute install commands (`uv add`, `go get`, `pnpm add`). All required dependencies must be listed in the "Requested Dependencies" section of the plan for user approval.
*   **Syntx Rule:** Enforce "1-2 Concerns per Package." Root files (`__init__.py`, `doc.go`, `index.ts`) are for orchestration and documentation only.
*   **Strict Token Naming Convention:**
    *   **2-3 Tokens:** All functions MUST have 2 or 3 tokens in their name (e.g., `GetUserData`, `ProcessOrderQueue`). NO single-word functions (e.g., `Run()`, `Process()`).
    *   **Feature Prefixing:** Functions MUST be prefixed by their primary feature or manager name (e.g., `DatabaseConnectPool`, `AuthVerifyToken`, `FileSystemReadFile`).
    *   **Style:** Follow language-specific casing (PascalCase for Go/TS exports, snake_case for Python `feature_action_detail`) while maintaining the token count and prefix rules.

---

## 2. Language-Specific Agents

### 2.1 Go Pair (v1.25.4)
**Coder & Debugger Directives:**
*   **Style:** `gofumpt` (strict), `golangci-lint`, `go vet`.
*   **Security:** `govulncheck` for all external integrations.
*   **Docs:** `doc.go` must exist for every package; Google-style docstrings for all exported symbols.
*   **Error Handling:** Explicit `if err != nil`; use `%w` for wrapping.

### 2.2 Python Pair (v3.13.7)
**Coder & Debugger Directives:**
*   **Style:** **RUFF IS MANDATORY** (`ruff check --fix`, `ruff format`).
*   **Tools:** `uv` for project management, `mypy` or `pyrefly` for strict typing.
*   **Docs:** Shebang + Path header. Google-style docstrings. `__init__.py` must document package concerns.
*   **Types:** PEP 604 (`int | None`) typing.

### 2.3 TypeScript Pair (v5.9.2 / Node 25.9)
**Coder & Debugger Directives:**
*   **Style:** `pnpm` workspace standards, `tsc` (typecheck).
*   **Docs:** `index.ts` entry point for all exports + package description. TSDoc (`@param`, `@returns`) for all exports.
*   **Strictness:** No `any`. Use `unknown` + type guards. Proper `async/await` patterns.

---

## 3. Test Architect Agent (The Sentry)
**Behavioral Directives:**
*   **TDD Methodology:** Draft failing ("Red") tests before any functional code is written.
*   **Go:** `testify/assert` (standard) and `testify/require` (critical). Table-driven tests preferred.
*   **Python:** `pytest` + `pytest-asyncio`. Strict Ruff enforcement on test files.
*   **TypeScript:** `vitest` with `describe/it` blocks. Mandatory isolation via `vi.mock`.

---

## 4. Documentation Standards Table

| Language | Line 1 | Line 2 | Module Summary | Function/Class Docs | Package Entry |
|---|---|---|---|---|---|
| **Python** | `#!/usr/bin/env python3` | `# path/to/file` | `"""Summary"""` | Google Style | `__init__.py` |
| **Go** | `// path/to/file` | N/A | `// Summary` | Google Style | `doc.go` |
| **TS** | `// path/to/file` | N/A | `// Summary` | TSDoc | `index.ts` |
