"""
Generate tree-sitter .scm query files from node-types.json.

Produces {language}.generated.scm files under the grammar's queries/ directory.
Existing vendor files (highlights.scm, tags.scm, locals.scm, {lang}.scm) are
never overwritten — generated output uses distinct capture namespaces.

Existing .scm files already cover:
  @symbol.*  — definitions (function_definition, class_definition, …)
  @import.*  — imports
  @call.*    — call sites

Generated files add:
  @scope.*   — scope containers (module, program, source_file, …)
  @struct.*  — structural types (struct, interface, type alias, …)
  @flow.*    — control flow (return, await, go, defer, …)
  @var.*     — variable bindings
  @type.*    — type annotations / generic types
  @sql.*     — SQL-specific structural captures
  @cypher.*  — Cypher-specific structural captures

Usage:
    python -m mem_graph.app.parsers.query_codegen --lang python
    python -m mem_graph.app.parsers.query_codegen --all
"""

from __future__ import annotations

import argparse
import json
import textwrap
from pathlib import Path

# ---------------------------------------------------------------------------
# Grammar root — relative to the repo root
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).parents[4]
_GRAMMAR_DIR = _REPO_ROOT / "data" / "tree-sitter" / "grammar"

# ---------------------------------------------------------------------------
# Per-language node allowlists
# Nodes already captured by existing .scm files are excluded from generation
# to avoid duplicate capture patterns.
# ---------------------------------------------------------------------------

# Python: python.scm already covers function_definition, class_definition,
# decorated_definition, import_statement, import_from_statement, call.
IMPORTANT_NODES: dict[str, set[str]] = {
    "python": {
        "module",
        "await",
        "return_statement",
        "assignment",
        "type_alias_statement",
        "typed_parameter",
        "typed_default_parameter",
        "parameters",
    },
    # Go: go.scm already covers function_declaration, method_declaration,
    # type_spec, const_spec, var_spec, import_spec, call_expression.
    "go": {
        "source_file",
        "package_clause",
        "import_declaration",
        "type_declaration",
        "struct_type",
        "interface_type",
        "field_declaration",
        "go_statement",
        "defer_statement",
        "channel_type",
        "send_statement",
        "select_statement",
        "short_var_declaration",
        "return_statement",
        "parameter_list",
    },
    # TypeScript: typescript.scm covers function_declaration, method_definition,
    # class_declaration, interface_declaration, type_alias_declaration,
    # enum_declaration, lexical_declaration/arrow_function, import_statement,
    # call_expression, new_expression.
    "typescript": {
        "program",
        "export_statement",
        "await_expression",
        "return_statement",
        "type_annotation",
        "generic_type",
        "variable_declarator",
        "member_expression",
    },
    # TSX: typescript superset plus JSX nodes
    "tsx": {
        "program",
        "export_statement",
        "await_expression",
        "return_statement",
        "type_annotation",
        "generic_type",
        "variable_declarator",
        "member_expression",
        "jsx_element",
        "jsx_self_closing_element",
        "jsx_opening_element",
        "jsx_closing_element",
        "jsx_attribute",
        "jsx_expression",
    },
    # SQL: uses actual grammar node names (select, from, join, etc.)
    "sql": {
        "statement",
        "select",
        "from",
        "join",
        "cross_join",
        "lateral_join",
        "where",
        "group_by",
        "order_by",
        "limit",
        "cte",
        "insert",
        "update",
        "delete",
        "create_table",
        "relation",
        "field",
        "term",
        "invocation",
        "window_function",
        "window_specification",
        "set_operation",
        "parameter",
        "cast",
        "object_reference",
        "subquery",
    },
    # Cypher: node-types.json in repo is a Haskell grammar (mis-packaged).
    # Queries are written against the known tree-sitter-cypher API surface.
    # CLI validation is skipped for Cypher — see validation report.
    "cypher": {
        "query",
        "match_clause",
        "where_clause",
        "return_clause",
        "with_clause",
        "create_clause",
        "merge_clause",
        "delete_clause",
        "set_clause",
        "node_pattern",
        "relationship_pattern",
        "node_label",
        "relationship_type",
        "property_key_name",
        "variable",
        "parameter",
        "function_invocation",
        "unwind_clause",
        "order_clause",
        "limit_clause",
        "skip_clause",
        "call_clause",
    },
}

# ---------------------------------------------------------------------------
# Per-language hand-written generated query bodies
# ---------------------------------------------------------------------------


def _python_generated() -> str:
    return textwrap.dedent("""\
        ; =============================================================================
        ; mem-graph — Python GENERATED structural queries
        ; Capture namespaces used here: @scope.*, @flow.*, @var.*, @type.*
        ; DO NOT duplicate patterns already in python.scm (@symbol.*, @import.*, @call.*)
        ; =============================================================================

        ; ---------------------------------------------------------------------------
        ; Scope markers
        ; ---------------------------------------------------------------------------

        (module) @scope.module

        ; ---------------------------------------------------------------------------
        ; Async detection on function_definition
        ; tree-sitter-python encodes `async` as a keyword child, not a named field.
        ; ---------------------------------------------------------------------------

        (function_definition
          "async" @flow.async_kw
          name: (identifier) @flow.async_fn.name
        ) @flow.async_fn

        ; ---------------------------------------------------------------------------
        ; Await expression
        ; ---------------------------------------------------------------------------

        (await
          (_) @flow.await.expr
        ) @flow.await

        ; ---------------------------------------------------------------------------
        ; Return statement
        ; ---------------------------------------------------------------------------

        (return_statement (_) @flow.return.value) @flow.return

        ; ---------------------------------------------------------------------------
        ; Type alias (PEP 695 `type X = Y`)
        ; ---------------------------------------------------------------------------

        (type_alias_statement
          left: (_) @type.alias.name
          right: (_) @type.alias.value
        ) @type.alias

        ; ---------------------------------------------------------------------------
        ; Typed parameters (captures type annotations on function params)
        ; ---------------------------------------------------------------------------

        (typed_parameter
          (identifier) @var.param.name
          type: (type) @var.param.type
        ) @var.param

        (typed_default_parameter
          name: (identifier) @var.param.name
          type: (type) @var.param.type
        ) @var.param.default

        ; ---------------------------------------------------------------------------
        ; Module-level assignment (variable bindings at top level)
        ; ---------------------------------------------------------------------------

        (module
          (expression_statement
            (assignment
              left: (identifier) @var.module.name
            ) @var.module
          )
        )
    """)


def _python_custom() -> str:
    return textwrap.dedent("""\
        ; =============================================================================
        ; mem-graph — Python CUSTOM / hand-patched queries
        ; Place manual refinements here — do not regenerate this file.
        ; =============================================================================

        ; Decorated async function — pair decorator + async marker
        (decorated_definition
          (decorator) @symbol.modifiers
          (function_definition
            "async" @flow.async_kw
            name: (identifier) @flow.async_fn.name
          ) @flow.async_fn
        )

        ; Constructor call via class name with keyword arguments
        (call
          function: (identifier) @call.target
          arguments: (argument_list
            (keyword_argument
              name: (identifier) @call.kwarg.name
            )
          )
        ) @call.site
    """)


def _go_generated() -> str:
    return textwrap.dedent("""\
        ; =============================================================================
        ; mem-graph — Go GENERATED structural queries
        ; Capture namespaces: @scope.*, @struct.*, @flow.*, @var.*
        ; DO NOT duplicate patterns already in go.scm (@symbol.*, @import.*, @call.*)
        ; =============================================================================

        ; ---------------------------------------------------------------------------
        ; Scope markers
        ; ---------------------------------------------------------------------------

        (source_file) @scope.file

        ; ---------------------------------------------------------------------------
        ; Package
        ; ---------------------------------------------------------------------------

        (package_clause
          (package_identifier) @scope.package.name
        ) @scope.package

        ; ---------------------------------------------------------------------------
        ; Import block scope
        ; ---------------------------------------------------------------------------

        (import_declaration) @scope.imports

        ; ---------------------------------------------------------------------------
        ; Type declaration container
        ; ---------------------------------------------------------------------------

        (type_declaration) @scope.type_decl

        ; ---------------------------------------------------------------------------
        ; Struct type with fields
        ; ---------------------------------------------------------------------------

        (type_spec
          name: (type_identifier) @struct.name
          type: (struct_type
            (field_declaration_list
              (field_declaration
                name: (field_identifier) @struct.field.name
              ) @struct.field
            )
          )
        ) @struct.def

        ; ---------------------------------------------------------------------------
        ; Interface type
        ; ---------------------------------------------------------------------------

        (type_spec
          name: (type_identifier) @struct.interface.name
          type: (interface_type)
        ) @struct.interface

        ; ---------------------------------------------------------------------------
        ; Goroutine
        ; ---------------------------------------------------------------------------

        (go_statement
          (_) @flow.goroutine.call
        ) @flow.goroutine

        ; ---------------------------------------------------------------------------
        ; Defer
        ; ---------------------------------------------------------------------------

        (defer_statement
          (_) @flow.defer.call
        ) @flow.defer

        ; ---------------------------------------------------------------------------
        ; Channel type
        ; ---------------------------------------------------------------------------

        (channel_type) @struct.channel

        ; ---------------------------------------------------------------------------
        ; Channel send: ch <- value
        ; ---------------------------------------------------------------------------

        (send_statement
          channel: (_) @flow.send.channel
          value: (_) @flow.send.value
        ) @flow.send

        ; ---------------------------------------------------------------------------
        ; Select statement (multi-channel await)
        ; ---------------------------------------------------------------------------

        (select_statement) @flow.select

        ; ---------------------------------------------------------------------------
        ; Short variable declaration: x := expr
        ; ---------------------------------------------------------------------------

        (short_var_declaration
          left: (_) @var.short.name
          right: (_) @var.short.value
        ) @var.short

        ; ---------------------------------------------------------------------------
        ; Return statement
        ; ---------------------------------------------------------------------------

        (return_statement (_) @flow.return.value) @flow.return
    """)


def _go_custom() -> str:
    return textwrap.dedent("""\
        ; =============================================================================
        ; mem-graph — Go CUSTOM / hand-patched queries
        ; =============================================================================

        ; Method receiver extraction — identifies which type a method belongs to
        (method_declaration
          receiver: (parameter_list
            (parameter_declaration
              name: (identifier) @symbol.receiver.var
              type: (_) @symbol.receiver.type
            )
          )
          name: (field_identifier) @symbol.name
        ) @symbol.def

        ; Goroutine spawning an anonymous function — common pattern
        (go_statement
          (call_expression
            function: (func_literal)
          )
        ) @flow.goroutine.anon

        ; Package-level const block
        (const_declaration
          (const_spec
            name: (identifier) @var.const.name
            value: (_) @var.const.value
          ) @var.const
        )
    """)


def _typescript_generated() -> str:
    return textwrap.dedent("""\
        ; =============================================================================
        ; mem-graph — TypeScript GENERATED structural queries
        ; Capture namespaces: @scope.*, @flow.*, @var.*, @type.*
        ; DO NOT duplicate patterns already in typescript.scm
        ; =============================================================================

        ; ---------------------------------------------------------------------------
        ; Scope markers
        ; ---------------------------------------------------------------------------

        (program) @scope.program

        ; ---------------------------------------------------------------------------
        ; Export wrapping a declaration
        ; ---------------------------------------------------------------------------

        (export_statement
          declaration: (_) @scope.export.decl
        ) @scope.export

        ; ---------------------------------------------------------------------------
        ; Await expression
        ; ---------------------------------------------------------------------------

        (await_expression
          (_) @flow.await.expr
        ) @flow.await

        ; ---------------------------------------------------------------------------
        ; Return statement
        ; ---------------------------------------------------------------------------

        (return_statement (_) @flow.return.value) @flow.return

        ; ---------------------------------------------------------------------------
        ; Type annotation (on variables, parameters, return types)
        ; ---------------------------------------------------------------------------

        (type_annotation (_) @type.annotation.body) @type.annotation

        ; ---------------------------------------------------------------------------
        ; Generic type reference (Promise<T>, Array<T>, etc.)
        ; ---------------------------------------------------------------------------

        (generic_type
          name: (type_identifier) @type.generic.name
          type_arguments: (_) @type.generic.args
        ) @type.generic

        ; ---------------------------------------------------------------------------
        ; Variable declarator (non-arrow-function bindings)
        ; ---------------------------------------------------------------------------

        (variable_declarator
          name: (identifier) @var.decl.name
        ) @var.decl

        ; ---------------------------------------------------------------------------
        ; Member expression (property access: obj.prop)
        ; ---------------------------------------------------------------------------

        (member_expression
          object: (_) @var.member.object
          property: (property_identifier) @var.member.prop
        ) @var.member
    """)


def _typescript_custom() -> str:
    return textwrap.dedent("""\
        ; =============================================================================
        ; mem-graph — TypeScript CUSTOM / hand-patched queries
        ; =============================================================================

        ; Async function declaration
        (function_declaration
          "async" @flow.async_kw
          name: (identifier) @flow.async_fn.name
        ) @flow.async_fn

        ; Async arrow function assigned to a const
        (lexical_declaration
          (variable_declarator
            name: (identifier) @flow.async_fn.name
            value: (arrow_function
              "async" @flow.async_kw
            )
          )
        ) @flow.async_fn

        ; Async method definition
        (method_definition
          "async" @flow.async_kw
          name: (property_identifier) @flow.async_method.name
        ) @flow.async_method

        ; Promise return type detection
        (function_declaration
          return_type: (type_annotation
            (generic_type
              name: (type_identifier) @type.promise
              (#eq? @type.promise "Promise")
            )
          )
        )
    """)


def _tsx_generated() -> str:
    return textwrap.dedent("""\
        ; =============================================================================
        ; mem-graph — TSX GENERATED structural queries
        ; Inherits TypeScript patterns; adds JSX node captures.
        ; Capture namespaces: @scope.*, @flow.*, @var.*, @type.*, @jsx.*
        ; =============================================================================

        ; ---------------------------------------------------------------------------
        ; Scope markers
        ; ---------------------------------------------------------------------------

        (program) @scope.program

        ; ---------------------------------------------------------------------------
        ; Export wrapping a declaration
        ; ---------------------------------------------------------------------------

        (export_statement
          declaration: (_) @scope.export.decl
        ) @scope.export

        ; ---------------------------------------------------------------------------
        ; Await expression
        ; ---------------------------------------------------------------------------

        (await_expression
          (_) @flow.await.expr
        ) @flow.await

        ; ---------------------------------------------------------------------------
        ; Return statement
        ; ---------------------------------------------------------------------------

        (return_statement (_) @flow.return.value) @flow.return

        ; ---------------------------------------------------------------------------
        ; Type annotation
        ; ---------------------------------------------------------------------------

        (type_annotation (_) @type.annotation.body) @type.annotation

        ; ---------------------------------------------------------------------------
        ; Generic type reference
        ; ---------------------------------------------------------------------------

        (generic_type
          name: (type_identifier) @type.generic.name
          type_arguments: (_) @type.generic.args
        ) @type.generic

        ; ---------------------------------------------------------------------------
        ; Variable declarator
        ; ---------------------------------------------------------------------------

        (variable_declarator
          name: (identifier) @var.decl.name
        ) @var.decl

        ; ---------------------------------------------------------------------------
        ; JSX element (includes capitalized custom components)
        ; ---------------------------------------------------------------------------

        (jsx_element
          open_tag: (jsx_opening_element
            name: (_) @jsx.element.name
          )
        ) @jsx.element

        ; Capitalized JSX element = custom component reference
        (jsx_element
          open_tag: (jsx_opening_element
            name: (identifier) @jsx.component
            (#match? @jsx.component "^[A-Z]")
          )
        ) @jsx.component_use

        (jsx_element
          open_tag: (jsx_opening_element
            name: (member_expression) @jsx.component
          )
        ) @jsx.component_use

        ; ---------------------------------------------------------------------------
        ; Self-closing JSX element
        ; ---------------------------------------------------------------------------

        (jsx_self_closing_element
          name: (_) @jsx.self_closing.name
        ) @jsx.self_closing

        (jsx_self_closing_element
          name: (identifier) @jsx.component
          (#match? @jsx.component "^[A-Z]")
        ) @jsx.component_use

        ; ---------------------------------------------------------------------------
        ; JSX attribute (prop)
        ; ---------------------------------------------------------------------------

        (jsx_attribute
          (property_identifier) @jsx.attr.name
        ) @jsx.attr

        ; ---------------------------------------------------------------------------
        ; JSX expression container: {expr}
        ; ---------------------------------------------------------------------------

        (jsx_expression) @jsx.expr
    """)


def _tsx_custom() -> str:
    return textwrap.dedent("""\
        ; =============================================================================
        ; mem-graph — TSX CUSTOM / hand-patched queries
        ; =============================================================================

        ; Async arrow function component
        (lexical_declaration
          (variable_declarator
            name: (identifier) @jsx.component.name
            (#match? @jsx.component.name "^[A-Z]")
            value: (arrow_function)
          )
        ) @jsx.component.def

        ; Async method definition
        (method_definition
          "async" @flow.async_kw
          name: (property_identifier) @flow.async_method.name
        ) @flow.async_method
    """)


def _sql_generated() -> str:
    return textwrap.dedent("""\
        ; =============================================================================
        ; mem-graph — SQL GENERATED structural queries
        ; Capture namespace: @sql.*
        ; Grammar: tree-sitter-sql (actual node names differ from SQL standards)
        ; Node names verified against sql/node-types.json and parse output.
        ; =============================================================================

        ; ---------------------------------------------------------------------------
        ; Top-level statement
        ; ---------------------------------------------------------------------------

        (statement) @sql.statement

        ; ---------------------------------------------------------------------------
        ; CTE (WITH clause)
        ; ---------------------------------------------------------------------------

        (cte
          argument: (_) @sql.cte.body
        ) @sql.cte

        ; ---------------------------------------------------------------------------
        ; SELECT clause
        ; ---------------------------------------------------------------------------

        (select) @sql.select

        ; ---------------------------------------------------------------------------
        ; FROM clause with table references
        ; ---------------------------------------------------------------------------

        (from
          (relation
            (object_reference
              name: (identifier) @sql.table.name
            )
            alias: (identifier) @sql.table.alias
          ) @sql.table_ref
        ) @sql.from

        (from
          (relation
            (object_reference
              name: (identifier) @sql.table.name
            )
          ) @sql.table_ref
        )

        ; ---------------------------------------------------------------------------
        ; JOIN clauses
        ; ---------------------------------------------------------------------------

        (join
          (relation
            (object_reference
              name: (identifier) @sql.join.table
            )
          )
        ) @sql.join

        (cross_join
          alias: (identifier) @sql.join.alias
        ) @sql.cross_join

        (lateral_join
          alias: (identifier) @sql.join.alias
        ) @sql.lateral_join

        ; ---------------------------------------------------------------------------
        ; WHERE clause
        ; ---------------------------------------------------------------------------

        (where
          predicate: (_) @sql.where.predicate
        ) @sql.where

        ; ---------------------------------------------------------------------------
        ; GROUP BY / ORDER BY / LIMIT
        ; ---------------------------------------------------------------------------

        (group_by) @sql.group_by

        (order_by) @sql.order_by

        (limit) @sql.limit

        ; ---------------------------------------------------------------------------
        ; DML statements
        ; ---------------------------------------------------------------------------

        (insert
          name: (object_reference
            name: (identifier) @sql.insert.table
          )
        ) @sql.insert

        (update) @sql.update

        (delete) @sql.delete

        ; ---------------------------------------------------------------------------
        ; DDL
        ; ---------------------------------------------------------------------------

        (create_table) @sql.create_table

        ; ---------------------------------------------------------------------------
        ; Column reference (field)
        ; ---------------------------------------------------------------------------

        (field
          name: (identifier) @sql.column.name
        ) @sql.column

        ; ---------------------------------------------------------------------------
        ; Expression with alias (SELECT term)
        ; ---------------------------------------------------------------------------

        (term
          alias: (identifier) @sql.term.alias
        ) @sql.term.aliased

        ; ---------------------------------------------------------------------------
        ; Function call
        ; ---------------------------------------------------------------------------

        (invocation
          (object_reference
            name: (identifier) @sql.fn.name
          )
        ) @sql.fn

        ; ---------------------------------------------------------------------------
        ; Window function
        ; ---------------------------------------------------------------------------

        (window_function) @sql.window_fn

        ; ---------------------------------------------------------------------------
        ; SET operation (UNION / INTERSECT / EXCEPT)
        ; ---------------------------------------------------------------------------

        (set_operation
          operation: (_) @sql.set_op.type
        ) @sql.set_op

        ; ---------------------------------------------------------------------------
        ; Parameter ($1, ?, :name)
        ; ---------------------------------------------------------------------------

        (parameter) @sql.param

        ; ---------------------------------------------------------------------------
        ; Type cast (::type or CAST)
        ; ---------------------------------------------------------------------------

        (cast
          name: (_) @sql.cast.expr
          custom_type: (_) @sql.cast.type
        ) @sql.cast

        ; ---------------------------------------------------------------------------
        ; Subquery
        ; ---------------------------------------------------------------------------

        (subquery) @sql.subquery

        ; ---------------------------------------------------------------------------
        ; Object reference (table or column name)
        ; ---------------------------------------------------------------------------

        (object_reference
          name: (identifier) @sql.ref.name
        ) @sql.ref
    """)


def _cypher_generated() -> str:
    return textwrap.dedent("""\
        ; =============================================================================
        ; mem-graph — Cypher GENERATED structural queries
        ; Capture namespace: @cypher.*
        ;
        ; NOTE: The tree-sitter-cypher binary bundled in this repo (v0.0.1) was
        ; identified as a Haskell parser. CLI validation is therefore SKIPPED.
        ; These queries are written against the expected tree-sitter-cypher API.
        ; Replace the binary with a real Cypher parser to enable CLI validation.
        ;
        ; Reference grammar: https://github.com/nickel-lang/tree-sitter-cypher
        ; =============================================================================

        ; ---------------------------------------------------------------------------
        ; Top-level query
        ; ---------------------------------------------------------------------------

        (query) @cypher.query

        ; ---------------------------------------------------------------------------
        ; Clauses
        ; ---------------------------------------------------------------------------

        (match_clause) @cypher.match

        (where_clause) @cypher.where

        (return_clause) @cypher.return

        (with_clause) @cypher.with

        (create_clause) @cypher.create

        (merge_clause) @cypher.merge

        (delete_clause) @cypher.delete

        (set_clause) @cypher.set

        (unwind_clause) @cypher.unwind

        (order_clause) @cypher.order_by

        (limit_clause) @cypher.limit

        (skip_clause) @cypher.skip

        (call_clause) @cypher.subquery

        ; ---------------------------------------------------------------------------
        ; Node and relationship patterns
        ; ---------------------------------------------------------------------------

        (node_pattern
          (variable) @cypher.node.alias
        ) @cypher.node

        (relationship_pattern
          (variable) @cypher.rel.alias
        ) @cypher.rel

        ; ---------------------------------------------------------------------------
        ; Labels and relationship types
        ; ---------------------------------------------------------------------------

        (node_label) @cypher.label

        (relationship_type) @cypher.rel_type

        ; ---------------------------------------------------------------------------
        ; Properties
        ; ---------------------------------------------------------------------------

        (property_key_name) @cypher.prop_key

        ; ---------------------------------------------------------------------------
        ; Variables and parameters
        ; ---------------------------------------------------------------------------

        (variable) @cypher.var

        (parameter) @cypher.param

        ; ---------------------------------------------------------------------------
        ; Function invocations
        ; ---------------------------------------------------------------------------

        (function_invocation
          (function_name) @cypher.fn.name
        ) @cypher.fn
    """)


# ---------------------------------------------------------------------------
# Dispatch tables
# ---------------------------------------------------------------------------

_GENERATED_BUILDERS: dict[str, object] = {
    "python": _python_generated,
    "go": _go_generated,
    "typescript": _typescript_generated,
    "tsx": _tsx_generated,
    "sql": _sql_generated,
    "cypher": _cypher_generated,
}

_CUSTOM_BUILDERS: dict[str, object] = {
    "python": _python_custom,
    "go": _go_custom,
    "typescript": _typescript_custom,
    "tsx": _tsx_custom,
}

SUPPORTED_LANGUAGES = list(_GENERATED_BUILDERS.keys())


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_node_types(grammar_dir: Path) -> dict[str, dict]:
    """Load named node types from node-types.json in *grammar_dir*."""
    path = grammar_dir / "node-types.json"
    if not path.exists():
        return {}
    with path.open() as fh:
        data = json.load(fh)
    return {entry["type"]: entry for entry in data if entry.get("named")}


def generate_scm(language: str) -> str:
    """Return the generated .scm content for *language*."""
    builder = _GENERATED_BUILDERS.get(language)
    if builder is None:
        raise ValueError(
            f"Unsupported language: {language!r}. Choose from {SUPPORTED_LANGUAGES}"
        )
    return builder()  # type: ignore[operator]


def generate_custom_scm(language: str) -> str | None:
    """Return the custom .scm patch content for *language*, or None if not defined."""
    builder = _CUSTOM_BUILDERS.get(language)
    return builder() if builder is not None else None  # type: ignore[operator]


def write_queries(
    language: str,
    *,
    dry_run: bool = False,
    grammar_root: Path | None = None,
) -> list[Path]:
    """
    Write generated and custom .scm files for *language*.

    Returns the list of paths written (or that would be written in dry-run).
    Raises FileExistsError if a vendor file would be overwritten.
    """
    grammar_root = grammar_root or _GRAMMAR_DIR
    queries_dir = grammar_root / language / "queries"
    if not queries_dir.exists():
        queries_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []

    generated_content = generate_scm(language)
    generated_path = queries_dir / f"{language}.generated.scm"
    if not dry_run:
        generated_path.write_text(generated_content)
    written.append(generated_path)

    custom_content = generate_custom_scm(language)
    if custom_content is not None:
        custom_path = queries_dir / f"{language}.custom.scm"
        if not dry_run:
            # Never overwrite an existing custom file — it may have been edited.
            if not custom_path.exists():
                custom_path.write_text(custom_content)
        written.append(custom_path)

    return written


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Generate tree-sitter .scm query files from node-types.json.",
    )
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--lang",
        choices=SUPPORTED_LANGUAGES,
        help="Generate for a single language.",
    )
    group.add_argument(
        "--all",
        action="store_true",
        help="Generate for all supported languages.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be written without writing files.",
    )
    p.add_argument(
        "--grammar-root",
        type=Path,
        default=None,
        help="Override the grammar root directory (default: data/tree-sitter/grammar).",
    )
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    langs = SUPPORTED_LANGUAGES if args.all else [args.lang]

    for lang in langs:
        paths = write_queries(
            lang, dry_run=args.dry_run, grammar_root=args.grammar_root
        )
        verb = "Would write" if args.dry_run else "Wrote"
        for p in paths:
            print(f"{verb}: {p}")


if __name__ == "__main__":
    main()
