# Last Session Summary

**Date:** 2026-04-18
**Task:** 023 — Tree-sitter SCM Autogeneration and Validation

## What was implemented

### New files created

**Parser module** (`src/mem_graph/app/parsers/`):
- `__init__.py` — module marker
- `query_codegen.py` — generates `{language}.generated.scm` and `{language}.custom.scm` files from per-language `IMPORTANT_NODES` allowlists; never overwrites vendor files; writes to `data/tree-sitter/grammar/{language}/queries/`
- `query_validate.py` — two-layer validator: (1) static check against `node-types.json` to catch unknown node types, (2) `tree-sitter query` CLI validation against fixture files with capture counting and noise budget checks; also runs vendor `tags.scm` validation

**Fixture files** (`tests/fixtures/tree_sitter/`):
- `python/sample.py` — realistic Python with classes, async functions, typed parameters, type aliases, Protocol, decorators
- `go/sample.go` — Go with interfaces, structs, methods, goroutines, channels, select statements
- `typescript/sample.ts` — TypeScript with interfaces, enums, classes, generics, async functions, arrow functions
- `tsx/sample.tsx` — TSX with React functional components, JSX elements, hooks, props
- `cypher/sample.cypher` — Cypher queries: MATCH, CREATE, MERGE, DELETE, WITH, UNWIND, CALL subquery
- `sql/sample.sql` — SQL with CTEs, window functions, DML, DDL, JOINs, parameters

**Generated query files** (`data/tree-sitter/grammar/{language}/queries/`):
- `python.generated.scm` + `python.custom.scm`
- `go.generated.scm` + `go.custom.scm`
- `typescript.generated.scm` + `typescript.custom.scm`
- `tsx.generated.scm` + `tsx.custom.scm`
- `sql.generated.scm` (no custom file — no existing .scm to conflict with)
- `cypher.generated.scm` (no custom file — CLI validation not possible)

Generated files use new capture namespaces (`@scope.*`, `@flow.*`, `@var.*`, `@type.*`, `@struct.*`, `@sql.*`, `@jsx.*`) that do not conflict with existing vendor files (`@symbol.*`, `@import.*`, `@call.*`).

### Validation results

All 5 validatable languages pass both static and CLI validation:

| Language | Static | CLI captures | Vendor captures |
|---|---|---|---|
| Python | ✅ | 72 | 44 (tags.scm) |
| Go | ✅ | 60 | 118 (tags.scm) |
| TypeScript | ✅ | 141 | 22 (tags.scm) |
| TSX | ✅ | 108 | 8 (tags.scm) |
| SQL | ✅ | 233 | — |
| Cypher | ⏩ skipped | ⏩ skipped | — |

**Cypher finding:** The `cypher-v0.0.1-linux-amd64.so` binary in the repo is a tree-sitter-haskell parser (mis-packaged). The `node-types.json` is also Haskell. CLI validation is impossible until replaced with a real Cypher parser binary.

### SQL grammar note

The SQL grammar (`tree-sitter-sql v0.3.11`) uses short node names that differ from SQL standard terminology: `select` (not `select_statement`), `from` (not `from_clause`), `join` (not `join_clause`), `cte` (not `with_clause`), `relation` (not `table_reference`), `field` (not `column_reference`), `invocation` (not `function_call`). The generated SQL queries use the actual grammar names verified via `tree-sitter parse`.

### Task 023 decision record

- **Result:** partial
- **Viable languages (query-driven extractor):** python, go, typescript, tsx, sql
- **Requires special handling:** cypher (wrong binary — Haskell parser)
- **Impact on Task 024:** Use `{language}.generated.scm` + `{language}.custom.scm` as the core extractor query contract for viable languages. For Cypher, implement direct AST traversal once a real Cypher grammar binary is sourced.

## ruff / mypy

Both `ruff check .` and `mypy .` exit 0 with no issues.
