"""Dashboard-safe agent and workflow discovery helpers.

Workflow metadata is now registry-driven via
``mem_graph.resources.workflows.visualization``. The ``workflow_definitions``
function returns metadata from the live Python registry instead of the
previously duplicated static declarations.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_AGENTS_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class WorkflowDefinition:
    """Static workflow metadata rendered by the dashboard."""

    key: str
    display_name: str
    source_file: str
    nodes: list[str]
    edges: list[dict[str, str]]
    mermaid: str
    description: str


def discover_agent_modules(base_dir: Path | None = None) -> list[dict[str, Any]]:
    """
    Return dashboard metadata for checked-in Python agent modules.

    The discovery pass is intentionally AST-only. It does not import project-local
    helper YAML specs or execute module-level agent construction.
    """
    root = base_dir or _AGENTS_DIR
    modules: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*.py")):
        if path.name == "__init__.py":
            continue
        relative = path.relative_to(root.parent)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError) as exc:
            modules.append(
                {
                    "module": _module_name(relative),
                    "source_file": str(relative),
                    "description": f"Unable to parse: {exc}",
                    "agents": [],
                    "personas": [],
                    "models": [],
                    "roles": [],
                }
            )
            continue

        doc = ast.get_docstring(tree) or ""
        module_name = _module_name(relative)
        modules.append(_build_module_info(module_name, str(relative), doc, tree))
    return modules


def _build_module_info(
    module_name: str, source_file: str, doc: str, tree: ast.AST
) -> dict[str, Any]:
    """Extract metadata and build the module info dictionary."""
    agent_names: list[str] = []
    personas: list[str] = []
    models: list[str] = []
    roles: list[str] = []

    for node in ast.walk(tree):
        _process_ast_node(node, agent_names, personas, models, roles)

    return {
        "module": module_name,
        "source_file": source_file,
        "description": _first_doc_paragraph(doc),
        "agents": sorted(set(agent_names)),
        "personas": sorted(set(personas)),
        "models": sorted(set(models)),
        "roles": sorted(set(roles)),
    }


def _process_ast_node(
    node: ast.AST,
    agent_names: list[str],
    personas: list[str],
    models: list[str],
    roles: list[str],
) -> None:
    """Process a single AST node to extract metadata."""
    if isinstance(node, ast.Assign):
        for target in node.targets:
            if isinstance(target, ast.Name):
                _check_assignment(target.id, node.value, agent_names, models)
    elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        _check_assignment(node.target.id, node.value, agent_names, models)
    elif isinstance(node, ast.Name):
        if node.id.endswith("_PERSONA"):
            personas.append(node.id)
    elif isinstance(node, ast.ClassDef) and node.name.endswith("Dependencies"):
        roles.append(node.name.replace("Dependencies", "").lower())


def _check_assignment(
    target_id: str,
    value: ast.AST | None,
    agent_names: list[str],
    models: list[str],
) -> None:
    """Check an assignment target for agent or model patterns."""
    if _looks_like_agent_assignment(target_id, value):
        agent_names.append(target_id)
    if target_id.endswith("_MODEL"):
        models.append(target_id)


def workflow_definitions() -> list[dict[str, Any]]:
    """Return registry-driven workflow metadata with Mermaid graph definitions.

    Metadata is sourced from the Python workflow registry in
    ``mem_graph.resources.workflows.visualization`` — no duplicated static
    workflow declarations.
    """
    from ..resources.workflows.visualization import all_workflow_metadata

    raw = all_workflow_metadata()
    results: list[dict[str, Any]] = []
    for item in raw:
        results.append(
            {
                "key": item["key"],
                "display_name": item["display_name"],
                "source_file": item.get("source_module", ""),
                "nodes": item["nodes"],
                "edges": item["edges"],
                "mermaid": item["mermaid"],
                "description": item["description"],
            }
        )
    return results


def _module_name(relative: Path) -> str:
    return ".".join(relative.with_suffix("").parts)


def _looks_like_agent_assignment(name: str, value: ast.AST | None) -> bool:
    if not name.endswith("_agent"):
        return False
    if value is None:
        return True
    if isinstance(value, ast.Call):
        func = value.func
        return (
            isinstance(func, ast.Name)
            and func.id == "Agent"
            or isinstance(func, ast.Attribute)
            and func.attr == "Agent"
        )
    return True


def _first_doc_paragraph(doc: str) -> str:
    if not doc:
        return "No module description available."
    paragraph = doc.strip().split("\n\n", maxsplit=1)[0]
    return " ".join(line.strip() for line in paragraph.splitlines()).strip()
