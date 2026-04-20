"""Command catalog and snippet builders for curated CLI commands."""

from __future__ import annotations

import inspect
import json
import textwrap
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from .base import ESCAPE_HATCH_ENV, accepted, failed, ok, partial, require_gate
from .command_db import (
    db_cypher,
    db_inspect,
    db_migrate,
    db_query_template,
    list_templates,
)
from .command_embed import embed_code, embed_documents
from .command_evals import eval_gate
from .command_parse_stage import code_commit_index, code_parse, code_stage, code_watch
from .command_shell import (
    lint_fix,
    shell_execute,
    toolchain_go,
    toolchain_python,
    toolchain_security,
)

CallTool = Callable[[str, dict[str, Any]], Awaitable[Any]]
HandlerResult = dict[str, Any] | Awaitable[dict[str, Any]]
CommandHandler = Callable[[dict[str, Any], CallTool | None], HandlerResult]

COMMAND_TOOLCHAIN_GO = "toolchain go"
COMMAND_TOOLCHAIN_PYTHON = "toolchain python"
COMMAND_TOOLCHAIN_SECURITY = "toolchain security"
COMMAND_LINT_FIX = "lint fix"
COMMAND_SHELL_EXECUTE = "shell execute"
COMMAND_AGENT_AUDIT = "agent audit"
COMMAND_AGENT_MAP = "agent map"
COMMAND_AGENT_FIX = "agent fix"
COMMAND_AGENT_VALIDATE = "agent validate"
COMMAND_AGENT_DOCUMENT = "agent document"
COMMAND_WORKFLOW_START = "workflow start"
COMMAND_CODE_PARSE = "code parse"
COMMAND_CODE_WATCH = "code watch"
COMMAND_CODE_STAGE = "code stage"
COMMAND_CODE_COMMIT_INDEX = "code commit-index"
COMMAND_PYTHON_REPL = "python repl"
AGENT_BRIDGE_ERROR = "call_tool bridge is required for agent commands."


@dataclass(frozen=True)
class CommandDefinition:
    name: str
    description: str


COMMANDS: tuple[CommandDefinition, ...] = (
    CommandDefinition(COMMAND_TOOLCHAIN_GO, "Format, test, and scan a Go project."),
    CommandDefinition(
        COMMAND_TOOLCHAIN_PYTHON,
        "Fix, typecheck, test, and scan this Python project.",
    ),
    CommandDefinition(
        COMMAND_TOOLCHAIN_SECURITY, "Run cross-language security scanners."
    ),
    CommandDefinition(COMMAND_AGENT_AUDIT, "Run audit-category agents."),
    CommandDefinition(COMMAND_AGENT_MAP, "Run map/category discovery agents."),
    CommandDefinition(COMMAND_AGENT_FIX, "Run fix/remediation agents."),
    CommandDefinition(COMMAND_AGENT_VALIDATE, "Run validation agents."),
    CommandDefinition(
        COMMAND_AGENT_DOCUMENT, "Run documentation and memory-update agents."
    ),
    CommandDefinition(COMMAND_WORKFLOW_START, "Run the compatibility workflow path."),
    CommandDefinition(
        COMMAND_CODE_PARSE, "Parse code with tree-sitter without DB writes."
    ),
    CommandDefinition(
        COMMAND_CODE_WATCH, "Watch code changes and stage parser output."
    ),
    CommandDefinition(COMMAND_CODE_STAGE, "Stage parser output without DB ingest."),
    CommandDefinition(
        COMMAND_CODE_COMMIT_INDEX,
        "Commit staged parser output to the graph DB.",
    ),
    CommandDefinition("embed documents", "Embed document/text content."),
    CommandDefinition("embed code", "Embed code files or symbols."),
    CommandDefinition("db migrate", "Run idempotent DB bootstrap/migration."),
    CommandDefinition("db inspect", "Run predefined graph inspection templates."),
    CommandDefinition(
        "db query-template", "Run a named Cypher template with typed params."
    ),
    CommandDefinition("db cypher", "Run gated raw Cypher for debugging."),
    CommandDefinition("eval gate", "Run fixture, CI, live, or release eval gates."),
    CommandDefinition(COMMAND_LINT_FIX, "Run Ruff fix/check and mypy."),
    CommandDefinition(COMMAND_PYTHON_REPL, "Run a gated Python diagnostic snippet."),
    CommandDefinition(COMMAND_SHELL_EXECUTE, "Run a gated allowlisted shell command."),
)

COMMAND_INDEX = {definition.name: definition for definition in COMMANDS}


def list_command_catalog() -> list[dict[str, str]]:
    return [definition.__dict__.copy() for definition in COMMANDS]


def build_command_snippet(command: str, arguments: dict[str, Any] | None = None) -> str:
    """Build the async Python snippet that external CLIs pass to execute."""
    if command not in COMMAND_INDEX:
        raise ValueError(f"Unknown curated command: {command!r}")
    payload = json.dumps(arguments or {}, indent=2, sort_keys=True)
    return "\n".join(
        [
            "from mem_graph.services.commands.catalog import dispatch_command",
            "",
            "return await dispatch_command(",
            f"    {command!r},",
            textwrap.indent(payload + ",", "    "),
            "    call_tool=call_tool,",
            ")",
        ]
    )


async def dispatch_command(
    command: str,
    arguments: dict[str, Any] | None = None,
    *,
    call_tool: CallTool | None = None,
) -> dict[str, Any]:
    """Dispatch one curated command envelope."""
    handler = _HANDLERS.get(command)
    if handler is None:
        return failed("command dispatch", f"Unknown curated command: {command!r}")
    result = handler(arguments or {}, call_tool)
    if inspect.isawaitable(result):
        return await result
    return result


async def _toolchain_go(
    arguments: dict[str, Any], call_tool: CallTool | None
) -> dict[str, Any]:
    del call_tool
    return await toolchain_go(root=arguments.get("root"))


async def _toolchain_python(
    arguments: dict[str, Any], call_tool: CallTool | None
) -> dict[str, Any]:
    del call_tool
    return await toolchain_python(root=arguments.get("root"))


async def _toolchain_security(
    arguments: dict[str, Any], call_tool: CallTool | None
) -> dict[str, Any]:
    del call_tool
    return await toolchain_security(root=arguments.get("root"))


async def _lint_fix(
    arguments: dict[str, Any], call_tool: CallTool | None
) -> dict[str, Any]:
    del call_tool
    return await lint_fix(root=arguments.get("root"))


async def _shell_execute(
    arguments: dict[str, Any], call_tool: CallTool | None
) -> dict[str, Any]:
    del call_tool
    return await shell_execute(
        list(arguments.get("argv", [])),
        root=arguments.get("root"),
        timeout_seconds=arguments.get("timeout_seconds"),
    )


def _db_migrate(
    arguments: dict[str, Any], call_tool: CallTool | None
) -> dict[str, Any]:
    del arguments, call_tool
    return db_migrate()


def _db_inspect(
    arguments: dict[str, Any], call_tool: CallTool | None
) -> dict[str, Any]:
    del call_tool
    return db_inspect(
        inspect_set=str(arguments.get("inspect_set") or "overview"),
        limit=int(arguments.get("limit") or 10),
    )


def _db_query_template(
    arguments: dict[str, Any], call_tool: CallTool | None
) -> dict[str, Any]:
    del call_tool
    return db_query_template(str(arguments.get("name") or ""), arguments.get("params"))


def _db_cypher(arguments: dict[str, Any], call_tool: CallTool | None) -> dict[str, Any]:
    del call_tool
    return db_cypher(str(arguments.get("query") or ""), arguments.get("params"))


def _code_parse(
    arguments: dict[str, Any], call_tool: CallTool | None
) -> dict[str, Any]:
    del call_tool
    return ok(
        COMMAND_CODE_PARSE,
        code_parse(
            root=arguments.get("root"),
            path=arguments.get("path"),
            include=arguments.get("include"),
            exclude=arguments.get("exclude"),
            max_files=int(arguments.get("max_files") or 200),
        ),
    )


def _code_stage(
    arguments: dict[str, Any], call_tool: CallTool | None
) -> dict[str, Any]:
    del call_tool
    return ok(
        COMMAND_CODE_STAGE,
        code_stage(
            root=arguments.get("root"),
            path=arguments.get("path"),
            include=arguments.get("include"),
            exclude=arguments.get("exclude"),
            max_files=int(arguments.get("max_files") or 200),
        ),
    )


def _code_commit_index(
    arguments: dict[str, Any], call_tool: CallTool | None
) -> dict[str, Any]:
    del call_tool
    return ok(
        COMMAND_CODE_COMMIT_INDEX,
        code_commit_index(
            root=arguments.get("root"),
            relative_paths=arguments.get("relative_paths"),
        ),
    )


async def _code_watch(
    arguments: dict[str, Any], call_tool: CallTool | None
) -> dict[str, Any]:
    del call_tool
    response = await code_watch(
        root=arguments.get("root"),
        include=arguments.get("include"),
        exclude=arguments.get("exclude"),
        poll_interval=float(arguments.get("poll_interval") or 1.0),
        session_id=arguments.get("session_id"),
    )
    return accepted(
        COMMAND_CODE_WATCH, response["task"], warnings=response.get("warnings")
    )


async def _embed_documents(
    arguments: dict[str, Any], call_tool: CallTool | None
) -> dict[str, Any]:
    del call_tool
    return await embed_documents(
        texts=arguments.get("texts"),
        files=arguments.get("files"),
        root=arguments.get("root"),
        include_vectors=bool(arguments.get("include_vectors", False)),
    )


async def _embed_code(
    arguments: dict[str, Any], call_tool: CallTool | None
) -> dict[str, Any]:
    del call_tool
    return await embed_code(
        root=arguments.get("root"),
        paths=arguments.get("paths"),
        project_id=arguments.get("project_id"),
        force_refresh=bool(arguments.get("force_refresh", False)),
    )


async def _eval_gate(
    arguments: dict[str, Any], call_tool: CallTool | None
) -> dict[str, Any]:
    del call_tool
    return await eval_gate(
        str(arguments.get("gate") or "fixture"),
        suites=arguments.get("suites"),
        suite_pass_threshold=arguments.get("suite_pass_threshold"),
        runs_override=arguments.get("runs_override"),
        project_id=arguments.get("project_id"),
        output_path=arguments.get("output_path"),
    )


async def _agent_audit(
    arguments: dict[str, Any], call_tool: CallTool | None
) -> dict[str, Any]:
    if call_tool is None:
        return failed(COMMAND_AGENT_AUDIT, AGENT_BRIDGE_ERROR)
    await call_tool("tools_activate", {"namespace": "audit"})
    task = await call_tool(
        "audit_package",
        {
            "package_path": arguments["package_path"],
            "project_id": arguments["project_id"],
            "report_output_path": arguments.get("report_output_path"),
            "persist_violations": bool(arguments.get("persist_violations", True)),
            "file_extension": arguments.get("file_extension", ".py"),
            "peer_review": bool(arguments.get("peer_review", False)),
        },
    )
    return accepted(COMMAND_AGENT_AUDIT, task)


async def _agent_map(
    arguments: dict[str, Any], call_tool: CallTool | None
) -> dict[str, Any]:
    if call_tool is None:
        return failed(COMMAND_AGENT_MAP, AGENT_BRIDGE_ERROR)
    await call_tool("tools_activate", {"namespace": "audit"})
    task = await call_tool(
        "map_codebase",
        {
            "package_path": arguments["package_path"],
            "known_features": arguments.get("known_features", []),
            "file_extension": arguments.get("file_extension", ".py"),
        },
    )
    return accepted(COMMAND_AGENT_MAP, task)


async def _agent_fix(
    arguments: dict[str, Any], call_tool: CallTool | None
) -> dict[str, Any]:
    return await _run_workflow_compat(
        COMMAND_AGENT_FIX,
        arguments,
        call_tool=call_tool,
        default_objective="Implement the requested fix using the managed workflow compatibility path.",
    )


async def _agent_validate(
    arguments: dict[str, Any], call_tool: CallTool | None
) -> dict[str, Any]:
    return await _run_workflow_compat(
        COMMAND_AGENT_VALIDATE,
        arguments,
        call_tool=call_tool,
        default_objective="Validate the selected changes, summarize blockers, and propose next steps.",
    )


async def _agent_document(
    arguments: dict[str, Any], call_tool: CallTool | None
) -> dict[str, Any]:
    if call_tool is None:
        return failed(COMMAND_AGENT_DOCUMENT, AGENT_BRIDGE_ERROR)
    await call_tool("tools_activate", {"namespace": "work"})
    outputs: dict[str, Any] = {}
    warnings: list[str] = []
    if arguments.get("feature_description") and arguments.get("project_id"):
        outputs["task_decompose_feature"] = await call_tool(
            "task_decompose_feature",
            {
                "project_id": arguments["project_id"],
                "feature_description": arguments["feature_description"],
            },
        )
    else:
        warnings.append(
            "feature_description and project_id were not provided for task decomposition."
        )
    if arguments.get("package_path") and arguments.get("project_id"):
        outputs["decision_review"] = await call_tool(
            "decision_review",
            {
                "project_id": arguments["project_id"],
                "package_path": arguments["package_path"],
            },
        )
    else:
        warnings.append(
            "package_path and project_id were not provided for decision review."
        )
    if outputs and warnings:
        return partial(COMMAND_AGENT_DOCUMENT, outputs, warnings)
    if outputs:
        return ok(COMMAND_AGENT_DOCUMENT, outputs)
    return failed(
        COMMAND_AGENT_DOCUMENT,
        "No document command inputs were provided.",
        warnings=warnings,
    )


async def _workflow_start(
    arguments: dict[str, Any], call_tool: CallTool | None
) -> dict[str, Any]:
    response = await _run_workflow_compat(
        COMMAND_WORKFLOW_START,
        arguments,
        call_tool=call_tool,
        default_objective="Run the managed workflow compatibility path for this task.",
    )
    response["warnings"].append(
        "Final profile-selected workflow routing remains blocked on Task 026."
    )
    return response


async def _python_repl(
    arguments: dict[str, Any], call_tool: CallTool | None
) -> dict[str, Any]:
    try:
        require_gate(
            ESCAPE_HATCH_ENV,
            "python repl is disabled by default.",
        )
    except PermissionError as exc:
        return failed(COMMAND_PYTHON_REPL, str(exc))

    code = str(arguments.get("code") or "return None")
    namespace: dict[str, Any] = {"call_tool": call_tool}
    function_source = "async def __mem_graph_python_repl__():\n" + textwrap.indent(
        code, "    "
    )
    exec(function_source, namespace)  # nosemgrep
    result = await namespace["__mem_graph_python_repl__"]()
    return ok(COMMAND_PYTHON_REPL, {"result": result})


async def _run_workflow_compat(
    command: str,
    arguments: dict[str, Any],
    *,
    call_tool: CallTool | None,
    default_objective: str,
) -> dict[str, Any]:
    if call_tool is None:
        return failed(command, "call_tool bridge is required for workflow commands.")
    await call_tool("tools_activate", {"namespace": "audit"})
    required = [key for key in ("project_id", "target_files") if key not in arguments]
    if required:
        return failed(command, f"Missing required workflow args: {', '.join(required)}")
    result = await call_tool(
        "run_subagent_workflow",
        {
            "objective": arguments.get("objective", default_objective),
            "project_id": arguments["project_id"],
            "target_files": arguments["target_files"],
            "project_root": arguments.get("project_root", ""),
            "max_retries": int(arguments.get("max_retries") or 3),
            "model_overrides": arguments.get("model_overrides"),
        },
    )
    return ok(command, {"workflow": result})


_HANDLERS: dict[str, CommandHandler] = {
    COMMAND_TOOLCHAIN_GO: _toolchain_go,
    COMMAND_TOOLCHAIN_PYTHON: _toolchain_python,
    COMMAND_TOOLCHAIN_SECURITY: _toolchain_security,
    COMMAND_LINT_FIX: _lint_fix,
    COMMAND_SHELL_EXECUTE: _shell_execute,
    "db migrate": _db_migrate,
    "db inspect": _db_inspect,
    "db query-template": _db_query_template,
    "db cypher": _db_cypher,
    COMMAND_CODE_PARSE: _code_parse,
    COMMAND_CODE_STAGE: _code_stage,
    COMMAND_CODE_COMMIT_INDEX: _code_commit_index,
    COMMAND_CODE_WATCH: _code_watch,
    "embed documents": _embed_documents,
    "embed code": _embed_code,
    "eval gate": _eval_gate,
    COMMAND_AGENT_AUDIT: _agent_audit,
    COMMAND_AGENT_MAP: _agent_map,
    COMMAND_AGENT_FIX: _agent_fix,
    COMMAND_AGENT_VALIDATE: _agent_validate,
    COMMAND_AGENT_DOCUMENT: _agent_document,
    COMMAND_WORKFLOW_START: _workflow_start,
    COMMAND_PYTHON_REPL: _python_repl,
}


__all__ = [
    "COMMANDS",
    "build_command_snippet",
    "dispatch_command",
    "list_command_catalog",
    "list_templates",
]
