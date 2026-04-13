#!/usr/bin/env python3
# src/mem_graph/resources/architecture.py
"""
Architectural guardrails for the Syntx agent suite.

Defines the structural rules that all agents must enforce when proposing
code changes. These guardrails are injected into agent system prompts
to ensure generated code conforms to the Syntx architectural standards.
"""

from __future__ import annotations

################
#   CONSTANTS
################

PACKAGE_ORGANIZATION_RULES = """
## Package Organization ("The Syntx Way")

### 1-2 Concerns Rule
A package should handle a maximum of TWO primary concerns. If a package
has grown beyond two responsibilities, secondary concerns MUST be extracted
into sub-packages.

### Hierarchical Grouping
Secondary or unrelated concerns go into sub-packages, not the root:
  CORRECT:   agents/triage/   agents/audit/
  INCORRECT: agents/ (flat folder with 10+ files handling different domains)

### Root-File Orchestration
Root files (__init__.py, doc.go, index.ts) are for orchestration and
documentation ONLY. Implementation details live in sub-packages.
  CORRECT:   __init__.py imports and re-exports from sub-packages
  INCORRECT: __init__.py contains 200 lines of business logic
"""

TOKEN_NAMING_RULES = """
## Strict Token Naming Convention

### 2-3 Token Rule
ALL functions, methods, and public symbols MUST have 2 or 3 tokens.
  CORRECT:   get_user_data      process_order_queue    verify_token
  INCORRECT: run()              process()              data()

### Feature Prefix Rule
Functions MUST be prefixed by their primary feature or manager name:
  CORRECT:   database_connect_pool   auth_verify_token   filesystem_read_file
  INCORRECT: connect_pool            verify_token        read_file

### Language-Specific Casing
- Python: snake_case (feature_action_detail)       e.g. fingerprint_compute_hash
- Go:     PascalCase for exports                   e.g. DatabaseConnectPool
- TypeScript: camelCase for internal, PascalCase for exported classes
"""

MANIFEST_GUARD_RULE = """
## Manifest Guard (MANDATORY)
ALWAYS read pyproject.toml, go.mod, or package.json BEFORE proposing changes.
This prevents suggesting dependencies that are already installed or incompatible.
"""

NO_AUTO_INSTALL_RULE = """
## No Auto-Install Rule
Agents MUST NOT execute install commands (uv add, go get, pnpm add).
All required dependencies must be listed in a "Requested Dependencies"
section of the plan for explicit user approval.
"""

################
#   COMBINED
################

ARCHITECTURE_GUARDRAILS = "\n".join([
    "# Syntx Architectural Guardrails",
    MANIFEST_GUARD_RULE,
    NO_AUTO_INSTALL_RULE,
    PACKAGE_ORGANIZATION_RULES,
    TOKEN_NAMING_RULES,
])
