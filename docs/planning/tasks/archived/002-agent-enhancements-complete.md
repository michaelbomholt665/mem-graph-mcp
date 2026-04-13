# Agent Architecture Enhancements: Deterministic Orchestration & Dynamic Tiering

This document serves as the master technical specification for upgrading the `mem-graph` agent suite. It integrates deterministic pipelines, four-tier dynamic model selection, stable deduplication, and strict architectural and coding standards.

## 1. Core Objectives

*   **Memory-First Orchestration:** All autonomous runs must ground themselves in the graph (Violations, Decisions, Map) before acting and sync results (Notes, Status) upon completion.
*   **Deterministic Control:** Move workflow logic (listing, batching, scaling) from LLM reasoning to immutable `pydantic-graph` nodes.
*   **Dynamic Tiering:** Implement a Router to select models based on task complexity (Micro to Autopilot).
*   **Closed-Loop Remediation:** Enable the system to find, fix, document, and validate code changes autonomously.
*   **Architectural & Style Integrity:** Enforce strict organizational patterns (1-2 concerns per package) and language-specific documentation standards.

## 2. Dynamic Model Strategy (The Four Tiers)

Models are managed by the **Router Agent** to balance intelligence, speed, and token cost.

| Tier | Alias | Model Identifier | Usage / Typical Task |
|---|---|---|---|
| **Autopilot** | `XHigh` | `openai:gpt-5.4-xhigh` | Large refactors (10–30 edits), 10+ new files, deep debugging. |
| **Standard** | `Medium` | `openai:gpt-5.4-medium` | Multi-file audits, standard task decomposition, mapping. |
| **Micro** | `Mini` | `openai:gpt-5.4-mini` | Single-file edits, typo fixes, simple context queries. |
| **Turbo** | `Fast` | `x-ai/grok-code-fast-1:optimized:free` | High-volume classification, pattern matching, simple parsing. |

### 2.1 Scaling & Concurrency Logic
*   **1 Worker:** < 10 files (Sequential processing).
*   **2 Workers:** 10–50 files (Parallel batches).
*   **3 Workers:** > 50 files (Max concurrency).
*   **Solo Mode:** For high-complexity tasks (flagged by Router), use the **Autopilot** tier directly on the full context without batching.

## 3. Deterministic Deduplication (Fingerprinting)

To prevent "messy" reports and redundant graph nodes, every finding is assigned a stable `fingerprint`.

*   **Fingerprint Formula:** `SHA256(file_path + rule_id + normalized_snippet)`
*   **Normalization:** The snippet is stripped of whitespace, line numbers, and comments before hashing to ensure stability across code edits.
*   **The Seen-Filter:** The Orchestrator maintains a `seen_fingerprints` set in `deps`. New findings matching a seen fingerprint are discarded immediately.
*   **Graph Sync:** The `violation_writer` uses fingerprints to distinguish between **🆕 New** violations and **🔄 Recurrences**.

## 4. Architectural & Coding Standards

### 4.1 Package Organization ("The Syntx Way")
*   **1-2 Concerns Rule:** A package should handle a maximum of two primary concerns.
*   **Hierarchical Grouping:** Secondary or unrelated concerns must be moved to sub-packages (e.g., `agents/triage/` and `agents/audit/` instead of a flat `agents/` folder).
*   **Orchestration Pattern:** Package roots (e.g., `__init__.py`, `doc.go`) should only contain orchestrators; implementation details stay in sub-packages.

### 4.2 Language-Specific Documentation Rules
| Language | Line 1 | Line 2 | Module Summary (L2-6/7) | Function/Class Docs | Package Entry |
|---|---|---|---|---|---|
| **Python** | Shebang (`#!...`) | `# path/to/file` | `"""Summary + Desc"""` | Google Style Docstrings | `__init__.py` (Desc) |
| **Go** | `// path/to/file` | N/A | `// Summary + Desc` | Google Style Docstrings | `doc.go` (Desc + Concerns) |
| **TS** | `// path/to/file` | N/A | `// Summary + Desc` | TSDoc (`@params`, etc.) | `index.ts` (Exports + Desc) |

## 5. The "Core Five" Agent Architecture

1.  **Router Agent:** The Gateway. Handles intent classification, tier selection, and task decomposition.
2.  **Rule Injector Agent:** The Librarian. Dynamically pulls relevant `AuditRule` sets (Local or External API).
3.  **Violation Fixer Agent:** The Mechanic. Proposes functional logic changes using the selected model tier.
4.  **Docs Agent (The Scribe):** The Stylist. Ensures all changes follow the `Coding Standards` (headers, docstrings).
5.  **Validation Agent:** The Guard. Post-fix quality gate. Re-runs audits and style checks to approve/reject changes.

## 6. Recursive Autopilot Workflow

For tasks flagged as `Autopilot` (10–30 edits), the Orchestrator enters a loop:
1.  **Context Gathering:** Query graph for `Violations`, `Decisions`, and `Map`.
2.  **Logic Draft:** Fixer Agent proposes functional changes.
3.  **Style Draft:** Docs Agent (The Scribe) ensures all headers and docstrings are correct.
4.  **Verify:** Validation Agent audits the patch for both logic and style.
5.  **Refine:** If validation fails, the Fixer/Scribe receives the new violations and attempts a correction.
6.  **Memory Sync:** Upon success (or retry limit), update the graph with a `Note` and update node statuses.

## 7. Implementation Roadmap

### Phase 1: Models, Resources & Configuration
*   **Config:** Update `.env` and `config.py` with the 4 tiers and `get_model_for_tier` helper.
*   **Models:** Expand `models/` to mirror Cypher schema (`project`, `work`, `memory`, `code`, `audit`).
*   **Resources:** Implement `personas.py` (Directives), `architecture.py` (Guardrails), and `coding_standards.py`.

### Phase 2: Deduplication & Service Logic
*   **Services:** Implement `FingerprintService` and update `violation_writer` to use fingerprints.
*   **Reporting:** Update `report_writer` with "New vs. Recurring" bucketing and hierarchical grouping.
*   **Policy Bridge:** Refactor `AuditRule` to be ready for external Enforcer API ingestion.

### Phase 3: Orchestration & Remediation
*   **Agents:** Implement the Router, Rule Injector, Fixer, Scribe, and Validation agents.
*   **Graph:** Refactor the Orchestrator into a `pydantic-graph` supporting the Recursive Autopilot loop and Dynamic Scaling.
