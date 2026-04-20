"""Named DB templates and gated Cypher helpers for curated commands."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from ...db import db_bootstrap_status, db_get_connection, db_run_migrations
from .base import (
    RAW_CYPHER_ENV,
    RAW_CYPHER_WRITE_ENV,
    env_flag,
    failed,
    ok,
    require_gate,
)

_TPL_SCHEMA_COUNTS = "schema.counts"
_TPL_SCHEMA_INDEXES = "schema.indexes"
_TPL_PROJECTS_LIST = "projects.list"
_TPL_TASKS_OPEN = "tasks.open"
_TPL_DECISIONS_RECENT = "decisions.recent"
_TPL_VIOLATIONS_OPEN = "violations.open"
_TPL_CODE_SYMBOLS = "code.symbols_by_file"
_TPL_EVALS_RECENT = "evals.recent"

_CMD_QUERY_TPL = "db query-template"
_CMD_CYPHER = "db cypher"

TemplateRunner = Callable[[dict[str, Any]], list[dict[str, Any]]]


@dataclass(frozen=True)
class ParamSpec:
    name: str
    kind: type[Any]
    required: bool = True
    default: Any = None


@dataclass(frozen=True)
class QueryTemplate:
    name: str
    description: str
    query: str | None = None
    columns: tuple[str, ...] = ()
    params: tuple[ParamSpec, ...] = ()
    runner: TemplateRunner | None = None

    def execute(self, raw_params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        params = _validate_params(self, raw_params or {})
        if self.runner is not None:
            return self.runner(params)
        if self.query is None:
            return []
        return _rows_to_dicts(_rows(self.query, params), self.columns)


def list_templates() -> list[dict[str, str]]:
    return [
        {"name": template.name, "description": template.description}
        for template in TEMPLATES.values()
    ]


def db_migrate() -> dict[str, Any]:
    status = db_run_migrations()
    return ok("db migrate", {"status": status})


def db_inspect(*, inspect_set: str = "overview", limit: int = 10) -> dict[str, Any]:
    sets = {
        "overview": [_TPL_SCHEMA_COUNTS, _TPL_SCHEMA_INDEXES, _TPL_PROJECTS_LIST, _TPL_TASKS_OPEN],
        "schema": [_TPL_SCHEMA_COUNTS, _TPL_SCHEMA_INDEXES],
        "work": [_TPL_PROJECTS_LIST, _TPL_TASKS_OPEN, _TPL_DECISIONS_RECENT, _TPL_VIOLATIONS_OPEN],
        "code": [_TPL_CODE_SYMBOLS, _TPL_EVALS_RECENT],
    }
    template_names = sets.get(inspect_set)
    if template_names is None:
        return failed("db inspect", f"Unknown inspect set: {inspect_set!r}")
    results: dict[str, Any] = {}
    warnings: list[str] = []
    for name in template_names:
        params = (
            {"limit": limit} if name not in {_TPL_SCHEMA_COUNTS, _TPL_SCHEMA_INDEXES} else {}
        )
        if name == _TPL_CODE_SYMBOLS:
            warnings.append(
                f"{_TPL_CODE_SYMBOLS} requires file_path and was skipped in the overview set."
            )
            continue
        results[name] = TEMPLATES[name].execute(params)
    results["bootstrap_status"] = db_bootstrap_status()
    return ok("db inspect", {"inspect_set": inspect_set, "results": results}, warnings)


def db_query_template(
    name: str, params: dict[str, Any] | None = None
) -> dict[str, Any]:
    template = TEMPLATES.get(name)
    if template is None:
        return failed(_CMD_QUERY_TPL, f"Unknown template: {name!r}")
    try:
        rows = template.execute(params)
    except (TypeError, ValueError) as exc:
        return failed(_CMD_QUERY_TPL, str(exc), data={"template": name})
    return ok(_CMD_QUERY_TPL, {"template": name, "rows": rows})


def db_cypher(query: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        require_gate(RAW_CYPHER_ENV, f"{_CMD_CYPHER} is disabled by default.")
    except PermissionError as exc:
        return failed(_CMD_CYPHER, str(exc))

    normalized = " ".join(query.strip().upper().split())
    if not _is_read_only_query(normalized) and not env_flag(RAW_CYPHER_WRITE_ENV):
        return failed(
            _CMD_CYPHER,
            f"Raw write Cypher is disabled. Set {RAW_CYPHER_WRITE_ENV}=1 to allow it.",
        )

    rows = _rows(query, params or {})
    return ok(_CMD_CYPHER, {"rows": rows})


def _validate_params(
    template: QueryTemplate, raw_params: dict[str, Any]
) -> dict[str, Any]:
    validated: dict[str, Any] = {}
    known_names = {spec.name for spec in template.params}
    extras = sorted(set(raw_params) - known_names)
    if extras:
        raise ValueError(f"Unexpected params for {template.name}: {', '.join(extras)}")

    for spec in template.params:
        if spec.name not in raw_params:
            if spec.required:
                raise ValueError(
                    f"Missing required param for {template.name}: {spec.name}"
                )
            validated[spec.name] = spec.default
            continue
        value = raw_params[spec.name]
        if value is not None and not isinstance(value, spec.kind):
            raise TypeError(
                f"Param {spec.name!r} for {template.name} must be {spec.kind.__name__}."
            )
        validated[spec.name] = value
    return validated


def _rows(query: str, params: dict[str, Any] | None = None) -> list[list[Any]]:
    result = db_get_connection().execute(query, params or {})
    if isinstance(result, list):
        return result
    return result.get_all()


def _rows_to_dicts(
    rows: list[list[Any]], columns: tuple[str, ...]
) -> list[dict[str, Any]]:
    return [
        {
            column: row[index] if index < len(row) else None
            for index, column in enumerate(columns)
        }
        for row in rows
    ]


def _schema_indexes(_: dict[str, Any]) -> list[dict[str, Any]]:
    rows = _rows("CALL SHOW_INDEXES() RETURN *;")
    return [
        {
            "entity": row[0] if len(row) > 0 else None,
            "name": row[1] if len(row) > 1 else None,
            "type": row[2] if len(row) > 2 else None,
            "property": row[3] if len(row) > 3 else None,
            "raw": row,
        }
        for row in rows
    ]


def _is_read_only_query(normalized: str) -> bool:
    read_prefixes = (
        "MATCH",
        "RETURN",
        "WITH",
        "CALL SHOW_INDEXES",
        "CALL QUERY_VECTOR_INDEX",
        "CALL QUERY_FTS_INDEX",
    )
    return normalized.startswith(read_prefixes)


TEMPLATES: dict[str, QueryTemplate] = {
    _TPL_SCHEMA_COUNTS: QueryTemplate(
        name=_TPL_SCHEMA_COUNTS,
        description="Return top-level counts for core graph entities.",
        query="""
        OPTIONAL MATCH (p:Project)
        WITH count(p) AS projects
        OPTIONAL MATCH (t:Task)
        WITH projects, count(t) AS tasks
        OPTIONAL MATCH (d:Decision)
        WITH projects, tasks, count(d) AS decisions
        OPTIONAL MATCH (v:Violation)
        WITH projects, tasks, decisions, count(v) AS violations
        OPTIONAL MATCH (n:Note)
        WITH projects, tasks, decisions, violations, count(n) AS notes
        OPTIONAL MATCH (cf:CodeFile)
        WITH projects, tasks, decisions, violations, notes, count(cf) AS code_files
        OPTIONAL MATCH (cs:CodeSymbol)
        WITH projects, tasks, decisions, violations, notes, code_files, count(cs) AS code_symbols
        OPTIONAL MATCH (e:EvalRun)
        RETURN projects, tasks, decisions, violations, notes, code_files, code_symbols, count(e) AS eval_runs
        """,
        columns=(
            "projects",
            "tasks",
            "decisions",
            "violations",
            "notes",
            "code_files",
            "code_symbols",
            "eval_runs",
        ),
    ),
    _TPL_SCHEMA_INDEXES: QueryTemplate(
        name=_TPL_SCHEMA_INDEXES,
        description="Return index metadata from Ladybug.",
        runner=_schema_indexes,
    ),
    _TPL_PROJECTS_LIST: QueryTemplate(
        name=_TPL_PROJECTS_LIST,
        description="List projects by name.",
        query="""
        MATCH (p:Project)
        RETURN p.id, p.name, p.repo_path
        ORDER BY p.name
        LIMIT $limit
        """,
        columns=("id", "name", "repo_path"),
        params=(ParamSpec("limit", int, required=False, default=10),),
    ),
    "projects.detail": QueryTemplate(
        name="projects.detail",
        description="Return one project with task, decision, and violation counts.",
        query="""
        MATCH (p:Project {id: $project_id})
        OPTIONAL MATCH (p)-[:HAS_TASK]->(t:Task)
        WITH p, count(DISTINCT t) AS task_count
        OPTIONAL MATCH (p)-[:HAS_DECISION]->(d:Decision)
        WITH p, task_count, count(DISTINCT d) AS decision_count
        OPTIONAL MATCH (p)-[:HAS_VIOLATION]->(v:Violation)
        RETURN p.id, p.name, p.repo_path, task_count, decision_count, count(DISTINCT v) AS violation_count
        LIMIT 1
        """,
        columns=(
            "id",
            "name",
            "repo_path",
            "task_count",
            "decision_count",
            "violation_count",
        ),
        params=(ParamSpec("project_id", str),),
    ),
    _TPL_TASKS_OPEN: QueryTemplate(
        name=_TPL_TASKS_OPEN,
        description="List open tasks across projects.",
        query="""
        MATCH (t:Task)
        WHERE coalesce(t.status, 'open') <> 'done' AND coalesce(t.status, 'open') <> 'closed'
        RETURN t.id, t.title, t.status, t.priority, t.project_id
        ORDER BY t.priority DESC, t.created_at DESC
        LIMIT $limit
        """,
        columns=("id", "title", "status", "priority", "project_id"),
        params=(ParamSpec("limit", int, required=False, default=10),),
    ),
    "tasks.by_project": QueryTemplate(
        name="tasks.by_project",
        description="List tasks linked to a project.",
        query="""
        MATCH (p:Project {id: $project_id})-[:HAS_TASK]->(t:Task)
        RETURN t.id, t.title, t.status, t.priority
        ORDER BY t.priority DESC, t.created_at DESC
        LIMIT $limit
        """,
        columns=("id", "title", "status", "priority"),
        params=(
            ParamSpec("project_id", str),
            ParamSpec("limit", int, required=False, default=10),
        ),
    ),
    _TPL_DECISIONS_RECENT: QueryTemplate(
        name=_TPL_DECISIONS_RECENT,
        description="List recent decisions.",
        query="""
        MATCH (d:Decision)
        RETURN d.id, d.title, d.status, d.impact, d.created_at
        ORDER BY d.created_at DESC
        LIMIT $limit
        """,
        columns=("id", "title", "status", "impact", "created_at"),
        params=(ParamSpec("limit", int, required=False, default=10),),
    ),
    _TPL_VIOLATIONS_OPEN: QueryTemplate(
        name=_TPL_VIOLATIONS_OPEN,
        description="List unresolved violations.",
        query="""
        MATCH (v:Violation)
        WHERE v.resolved_at IS NULL
        RETURN v.id, v.rule, v.severity, v.status, v.file_path
        ORDER BY v.detected_at DESC
        LIMIT $limit
        """,
        columns=("id", "rule", "severity", "status", "file_path"),
        params=(ParamSpec("limit", int, required=False, default=10),),
    ),
    "violations.by_file": QueryTemplate(
        name="violations.by_file",
        description="List violations for a repo-relative file path.",
        query="""
        MATCH (v:Violation)
        WHERE v.file_path = $file_path
        RETURN v.id, v.rule, v.severity, v.status, v.description
        ORDER BY v.detected_at DESC
        LIMIT $limit
        """,
        columns=("id", "rule", "severity", "status", "description"),
        params=(
            ParamSpec("file_path", str),
            ParamSpec("limit", int, required=False, default=10),
        ),
    ),
    "notes.recent": QueryTemplate(
        name="notes.recent",
        description="List recent notes.",
        query="""
        MATCH (n:Note)
        RETURN n.id, n.title, n.updated_at
        ORDER BY n.updated_at DESC
        LIMIT $limit
        """,
        columns=("id", "title", "updated_at"),
        params=(ParamSpec("limit", int, required=False, default=10),),
    ),
    _TPL_CODE_SYMBOLS: QueryTemplate(
        name=_TPL_CODE_SYMBOLS,
        description="List code symbols for one indexed file.",
        query="""
        MATCH (s:CodeSymbol)
        WHERE s.file_path = $file_path
        RETURN s.id, s.name, s.kind, s.qualified_name, s.line_start, s.line_end
        ORDER BY s.line_start ASC
        LIMIT $limit
        """,
        columns=("id", "name", "kind", "qualified_name", "line_start", "line_end"),
        params=(
            ParamSpec("file_path", str),
            ParamSpec("limit", int, required=False, default=100),
        ),
    ),
    "code.callers": QueryTemplate(
        name="code.callers",
        description="List callers for a code symbol by name or qualified name.",
        query="""
        MATCH (caller:CodeSymbol)-[r:CALLS]->(callee:CodeSymbol)
        WHERE callee.qualified_name = $symbol OR callee.name = $symbol
        RETURN caller.id, caller.qualified_name, caller.file_path, r.call_name, r.is_awaited
        LIMIT $limit
        """,
        columns=("id", "qualified_name", "file_path", "call_name", "is_awaited"),
        params=(
            ParamSpec("symbol", str),
            ParamSpec("limit", int, required=False, default=25),
        ),
    ),
    "code.callees": QueryTemplate(
        name="code.callees",
        description="List callees for a caller symbol by name or qualified name.",
        query="""
        MATCH (caller:CodeSymbol)-[r:CALLS]->(callee:CodeSymbol)
        WHERE caller.qualified_name = $symbol OR caller.name = $symbol
        RETURN callee.id, callee.qualified_name, callee.file_path, r.call_name, r.is_awaited
        LIMIT $limit
        """,
        columns=("id", "qualified_name", "file_path", "call_name", "is_awaited"),
        params=(
            ParamSpec("symbol", str),
            ParamSpec("limit", int, required=False, default=25),
        ),
    ),
    _TPL_EVALS_RECENT: QueryTemplate(
        name=_TPL_EVALS_RECENT,
        description="List recent eval summaries.",
        query="""
        MATCH (e:EvalRun)
        RETURN e.id, e.mode, e.label, e.trigger, e.passed_suites, e.total_suites, e.suite_pass_rate, e.completed_at
        ORDER BY e.completed_at DESC
        LIMIT $limit
        """,
        columns=(
            "id",
            "mode",
            "label",
            "trigger",
            "passed_suites",
            "total_suites",
            "suite_pass_rate",
            "completed_at",
        ),
        params=(ParamSpec("limit", int, required=False, default=10),),
    ),
}
