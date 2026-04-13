#!/usr/bin/env python3
# src/mem_graph/resources/coding_standards.py
"""
Language-specific coding standards for the Scribe and Validation agents.

Encodes the documentation format, style tooling, and type-checking rules
for each supported language. Injected into Scribe and Validation agent
system prompts to enforce consistent output across all code changes.
"""

from __future__ import annotations

################
#   PYTHON
################

PYTHON_STANDARDS = """
## Python Standards (v3.13+)

### File Header (MANDATORY — every .py file)
Line 1: #!/usr/bin/env python3
Line 2: # path/to/file.py
Lines 3–7: \"\"\"Module summary.\\n\\nLonger description if needed.\"\"\"

### Style Tooling (MANDATORY)
- ruff check --fix   (linting + auto-fix)
- ruff format        (formatting)
- mypy or pyrefly for strict typing (no Any)

### Type Annotations
- PEP 604 union syntax: int | None  (NOT Optional[int])
- All function parameters and return types MUST be annotated

### Docstrings
- Google Style for all public functions and classes
- Args, Returns, Raises sections as applicable

### Package Entry
- __init__.py MUST document: package name, concerns (max 2), public API
"""

################
#   GO
################

GO_STANDARDS = """
## Go Standards (v1.25.4)

### File Header (MANDATORY — every .go file)
Line 1: // path/to/file.go

### Style Tooling (MANDATORY)
- gofumpt (strict formatting, superset of gofmt)
- golangci-lint for static analysis
- go vet for correctness checks
- govulncheck for external integrations

### Error Handling
- Explicit if err != nil checks — no error silencing
- Use fmt.Errorf("context: %w", err) for wrapping

### Docstrings
- Google Style for all exported symbols
- doc.go MUST exist for every package (description + concerns)
"""

################
#   TYPESCRIPT
################

TYPESCRIPT_STANDARDS = """
## TypeScript Standards (v5.9.2 / Node 25.9)

### File Header (MANDATORY — every .ts file)
Line 1: // path/to/file.ts

### Style Tooling (MANDATORY)
- pnpm workspace standards
- tsc --noEmit (typecheck must pass)

### Type Safety
- NO any — use unknown + type guards instead
- Proper async/await (no floating promises)

### Docstrings
- TSDoc format: @param, @returns, @throws for all exports
- index.ts MUST: re-export all public API + describe package
"""

################
#   COMBINED
################

CODING_STANDARDS_ALL = "\n".join([
    "# Syntx Coding Standards",
    PYTHON_STANDARDS,
    GO_STANDARDS,
    TYPESCRIPT_STANDARDS,
])

#: Map language key → its standards block (for selective injection).
STANDARDS_BY_LANGUAGE: dict[str, str] = {
    "python": PYTHON_STANDARDS,
    "go": GO_STANDARDS,
    "typescript": TYPESCRIPT_STANDARDS,
}


def coding_standards_get_for_language(language: str) -> str:
    """
    Retrieve the standards block for a specific language.

    Falls back to CODING_STANDARDS_ALL when the language is unknown,
    so agents always receive valid guidance.

    Args:
        language: The target language key (python, go, typescript).

    Returns:
        The standards string for the requested language.
    """
    return STANDARDS_BY_LANGUAGE.get(language.lower(), CODING_STANDARDS_ALL)
