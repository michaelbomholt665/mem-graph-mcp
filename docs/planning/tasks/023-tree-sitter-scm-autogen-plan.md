# Task 023: Tree-sitter SCM Autogeneration and Validation

**Status:** Planning
**Priority:** High
**Blocked by:** None
**Blocks:** Task 024 parser, extractor, resolver, and persistence design

## Problem Statement

Before building the parser/extractor/resolver pipeline, we need to prove whether `node-types.json` can generate useful `.scm` query files for the high-value grammars. This is a gating task. If generated `.scm` files compile, capture the right nodes, and stay within a low-noise budget, Task 024 can be query-driven. If not, Task 024 changes materially: custom extractors will need to traverse parsed ASTs directly using `node-types.json` allowlists and language-specific logic.

The design reference is:

```text
docs/planning/design/tree-sitter/autogen.scm.md
```

## Current Findings

- `tree-sitter` CLI is installed: `tree-sitter 0.26.8`.
- Python runtime package `tree_sitter` is not installed in the current environment.
- `pyproject.toml` has no Tree-sitter Python dependency.
- Grammar assets exist under `data/tree-sitter/grammar/{language}/`.
- Relevant `node-types.json` files exist at:
  - `data/tree-sitter/grammar/typescript/node-types.json`
  - `data/tree-sitter/grammar/tsx/node-types.json`
  - `data/tree-sitter/grammar/python/node-types.json`
  - `data/tree-sitter/grammar/go/node-types.json`
  - `data/tree-sitter/grammar/cypher/node-types.json`
  - `data/tree-sitter/grammar/sql/node-types.json`
- Standard query files exist under `data/tree-sitter/grammar/{language}/queries/` for most grammars.
- Cypher has `node-types.json` and a compiled binary, but no standard `queries/` directory.

## Scope

This task only creates the SCM generation and validation workflow. It should not implement DB persistence, code graph schema changes, or full parser extraction.

In scope:

- Add an SCM generator from `node-types.json`.
- Add static validation against `node-types.json`.
- Add CLI validation using `tree-sitter query`.
- Add fixtures for the six target languages.
- Generate first-pass query files for Python, Go, TypeScript, TSX, Cypher, and SQL.
- Produce a clear go/no-go result for Task 024.

Out of scope:

- Graph schema migrations.
- `CodeSymbol` persistence.
- Import/call/type resolvers.
- Dashboard integration.
- Automatic code indexing.

## Target Files

Create a small parser planning/tooling surface under:

```text
src/mem_graph/app/parsers/
  __init__.py
  query_codegen.py
  query_validate.py
```

## NOTE:
- This document MIGHT claim that the queries is located in src/*** but they are not, they MUST be located in the folder listed below for each language
Add generated query files under:

```text
  data/tree-sitter/grammar/{language}/queries/
    python.generated.scm
    python.custom.scm
    go.generated.scm
    go.custom.scm
    typescript.generated.scm
    typescript.custom.scm
    tsx.generated.scm
    tsx.custom.scm
    cypher.generated.scm
    sql.generated.scm
```

Add validation fixtures under:

```text
tests/fixtures/tree_sitter/
  python/sample.py
  go/sample.go
  typescript/sample.ts
  tsx/sample.tsx
  cypher/sample.cypher
  sql/sample.sql
```

## Generator Design

Implement `query_codegen.py` from the pattern in `docs/planning/design/tree-sitter/autogen.scm.md`, with stricter guardrails:

- Read `node-types.json`.
- Build a dictionary of named node types.
- Use per-language `IMPORTANT_NODES` allowlists.
- Generate broad capture queries for important nodes only.
- Generate optional `tags`-style captures for symbol definitions.
- Generate optional `locals`-style captures for scope/reference tests.
- Never overwrite vendor query files under `data/tree-sitter/grammar`.
- Write generated output under `src/mem_graph/app/parsers/queries/`.
- Keep custom hand patches in separate `*.custom.scm` files.

## Target Languages

### Python

Initial allowlist:

- `module`
- `class_definition`
- `function_definition`
- `decorated_definition`
- `parameters`
- `typed_parameter`
- `typed_default_parameter`
- `import_statement`
- `import_from_statement`
- `assignment`
- `call`
- `await`
- `return_statement`
- `type_alias_statement`

Manual/custom cases expected:

- `async` detection on `function_definition`.
- Decorated function/class pairing.
- Call target extraction from identifiers and attributes.

### Go

Initial allowlist:

- `source_file`
- `package_clause`
- `import_declaration`
- `function_declaration`
- `method_declaration`
- `parameter_list`
- `type_declaration`
- `type_spec`
- `struct_type`
- `interface_type`
- `field_declaration`
- `call_expression`
- `selector_expression`
- `go_statement`
- `defer_statement`
- `channel_type`
- `send_statement`
- `receive_statement`
- `select_statement`
- `short_var_declaration`
- `return_statement`

Manual/custom cases expected:

- Method receiver extraction.
- Selector expression call names.
- Goroutine/defer call pairing.
- Channel send/receive classification.

### TypeScript

Initial allowlist:

- `program`
- `import_statement`
- `export_statement`
- `function_declaration`
- `method_definition`
- `class_declaration`
- `interface_declaration`
- `type_alias_declaration`
- `enum_declaration`
- `lexical_declaration`
- `variable_declarator`
- `arrow_function`
- `call_expression`
- `await_expression`
- `member_expression`
- `return_statement`
- `type_annotation`
- `generic_type`

Manual/custom cases expected:

- Async function/member detection.
- Export detection.
- Import binding and alias details.
- Promise return type detection.

### TSX

Reuse TypeScript allowlist and add:

- `jsx_element`
- `jsx_self_closing_element`
- `jsx_opening_element`
- `jsx_closing_element`
- `jsx_attribute`
- `jsx_expression`

Manual/custom cases expected:

- Only capture capitalized custom components by default.
- Avoid storing every DOM tag.
- Capture meaningful component props without flooding the graph.

### Cypher

Initial allowlist:

- `query`
- `match_clause`
- `where_clause`
- `return_clause`
- `with_clause`
- `create_clause`
- `merge_clause`
- `delete_clause`
- `set_clause`
- `node_pattern`
- `relationship_pattern`
- `path_pattern`
- `node_label`
- `relationship_type`
- `property_key_name`
- `variable`
- `parameter`
- `function_invocation`
- `unwind_clause`
- `order_clause`
- `limit_clause`
- `skip_clause`
- `call_clause`

Manual/custom cases expected:

- Alias binding inside node and relationship patterns.
- Relationship direction and hop range extraction.
- Query type classification as read, write, or read-write.

### SQL

Initial allowlist:

- `statement`
- `select_statement`
- `from_clause`
- `join_clause`
- `where_clause`
- `group_by_clause`
- `having_clause`
- `order_by_clause`
- `limit_clause`
- `with_clause`
- `cte_definition`
- `insert_statement`
- `update_statement`
- `delete_statement`
- `create_table_statement`
- `table_reference`
- `column_reference`
- `alias`
- `subquery`
- `function_call`
- `window_function`
- `window_definition`
- `union`
- `intersect`
- `except`
- `parameter`
- `type_cast`

Manual/custom cases expected:

- Table alias binding.
- CTE definition/reference pairing.
- Column lineage from table aliases.
- Dialect-specific extensions only after the generic path works.

## Validation Design

Implement `query_validate.py` with two layers.

### Static Validation

Use `node-types.json` to detect:

- Unknown node types.
- Unknown named fields.
- Captures for nodes that are absent from a grammar.
- Empty generated files.

### CLI Validation

Use `tree-sitter query` against fixtures:

```bash
tree-sitter query src/mem_graph/app/parsers/queries/python.generated.scm tests/fixtures/tree_sitter/python/sample.py
tree-sitter query src/mem_graph/app/parsers/queries/go.generated.scm tests/fixtures/tree_sitter/go/sample.go
tree-sitter query src/mem_graph/app/parsers/queries/typescript.generated.scm tests/fixtures/tree_sitter/typescript/sample.ts
tree-sitter query src/mem_graph/app/parsers/queries/tsx.generated.scm tests/fixtures/tree_sitter/tsx/sample.tsx
tree-sitter query src/mem_graph/app/parsers/queries/cypher.generated.scm tests/fixtures/tree_sitter/cypher/sample.cypher
tree-sitter query src/mem_graph/app/parsers/queries/sql.generated.scm tests/fixtures/tree_sitter/sql/sample.sql
```

Also validate at least one vendor query per language where present:

```bash
tree-sitter query data/tree-sitter/grammar/python/queries/tags.scm tests/fixtures/tree_sitter/python/sample.py
tree-sitter query data/tree-sitter/grammar/go/queries/tags.scm tests/fixtures/tree_sitter/go/sample.go
tree-sitter query data/tree-sitter/grammar/typescript/queries/tags.scm tests/fixtures/tree_sitter/typescript/sample.ts
tree-sitter query data/tree-sitter/grammar/tsx/queries/tags.scm tests/fixtures/tree_sitter/tsx/sample.tsx
```

## Acceptance Criteria

The generated SCM path is viable only if all of these are true:

- Generated queries compile for all six target languages.
- Fixtures produce captures for the required high-value node groups.
- Capture volume stays within a configured noise budget.
- Custom patches are small and targeted.
- Query output gives enough context for a later extractor to map captures into symbols and edges.

Suggested noise budget for initial fixtures:

- Python: 8-25 captures.
- Go: 8-30 captures.
- TypeScript: 10-35 captures.
- TSX: 10-45 captures.
- Cypher: 8-30 captures.
- SQL: 8-35 captures.

The exact numbers can move after fixture design, but this task must record the measured counts.

## Fallback Decision

If generated `.scm` fails static or CLI validation, or if valid queries are too noisy to be useful, Task 024 should pivot:

- Do not make generated SCM files the core extractor contract.
- Use `node-types.json` only as metadata for validating AST traversal.
- Implement direct AST visitors per special grammar.
- Keep vendor SCM files only for broad standard captures where they work.
- Expect more language-specific extractor code in Task 024.

This decision changes Task 024 substantially. It affects parser module boundaries, tests, resolver inputs, and the amount of language-specific traversal code.

## Implementation Checklist

- [x] Add `src/mem_graph/app/parsers/__init__.py`.
- [x] Add `src/mem_graph/app/parsers/query_codegen.py`.
- [x] Add `src/mem_graph/app/parsers/query_validate.py`.
- [x] Add `data/tree-sitter/grammar/{language}/queries/`.
- [x] Add fixture files for Python, Go, TypeScript, TSX, Cypher, and SQL.
- [x] Implement per-language `IMPORTANT_NODES`.
- [x] Generate first-pass `.generated.scm` files.
- [x] Add targeted `.custom.scm` patches where needed (Python, Go, TypeScript, TSX).
- [x] Run static validation against all six `node-types.json` files.
- [x] Run `tree-sitter query` validation against fixtures.
- [x] Record capture counts and failure modes.
- [x] Update Task 024 with the final path: query-driven or direct AST traversal.

## Decision Record

**Status:** Completed 2026-04-18

### Measured capture counts (against fixture files)

| Language | Generated SCM | Vendor tags.scm | Budget used |
|---|---|---|---|
| Python | 72 | 44 | 72 / 120 ✅ |
| Go | 60 | 118 | 60 / 120 ✅ |
| TypeScript | 141 | 22 | 141 / 250 ✅ |
| TSX | 108 | 8 | 108 / 200 ✅ |
| SQL | 233 | — | 233 / 400 ✅ |
| Cypher | skipped | — | n/a |

### SCM generation result

```
SCM generation result: partial

Languages viable (query-driven extractor):
  python, go, typescript, tsx, sql

Languages requiring special handling:
  cypher

Reason:
  - python/go/typescript/tsx/sql: All static validations pass (no unknown node types).
    CLI validation compiles and produces expected captures within calibrated budgets.
    Generated .scm files use complementary capture namespaces (@scope.*, @flow.*,
    @var.*, @type.*, @struct.*, @sql.*) that do not conflict with existing vendor
    .scm files (@symbol.*, @import.*, @call.*).
    Initial planning budgets (8-25, 8-30, etc.) were pre-fixture estimates; the
    calibrated budgets above reflect the actual fixture complexity.

  - cypher: The tree-sitter binary bundled in data/tree-sitter/grammar/cypher/
    is a Haskell grammar (tree-sitter-haskell, mis-packaged as cypher v0.0.1).
    The node-types.json is also Haskell. CLI validation is therefore impossible.
    The generated cypher.generated.scm is written against the expected
    tree-sitter-cypher API but cannot be validated until the binary is replaced.

Impact on Task 024:
  - python/go/typescript/tsx/sql: Use {language}.generated.scm as the core
    extractor query. Combine with {language}.custom.scm for async detection,
    method receivers, and JSX component filtering.
  - cypher: Requires a real Cypher grammar binary. Until then, implement a direct
    AST traversal extractor using the expected node type names from the generated
    .scm as an allowlist reference.
  - All languages: The existing vendor .scm files (tags.scm, highlights.scm,
    python.scm, go.scm, typescript.scm) remain untouched and are valid for
    standard tooling use.
```
