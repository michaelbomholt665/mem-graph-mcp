"""Dashboard-safe agent and workflow discovery helpers."""

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
        agent_names: list[str] = []
        personas: list[str] = []
        models: list[str] = []
        roles: list[str] = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        if _looks_like_agent_assignment(target.id, node.value):
                            agent_names.append(target.id)
                        if target.id.endswith("_MODEL"):
                            models.append(target.id)
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                if _looks_like_agent_assignment(node.target.id, node.value):
                    agent_names.append(node.target.id)
                if node.target.id.endswith("_MODEL"):
                    models.append(node.target.id)
            elif isinstance(node, ast.Name):
                if node.id.endswith("_PERSONA"):
                    personas.append(node.id)
            elif isinstance(node, ast.ClassDef) and node.name.endswith("Dependencies"):
                roles.append(node.name.replace("Dependencies", "").lower())

        module_name = _module_name(relative)
        modules.append(
            {
                "module": module_name,
                "source_file": str(relative),
                "description": _first_doc_paragraph(doc),
                "agents": sorted(set(agent_names)),
                "personas": sorted(set(personas)),
                "models": sorted(set(models)),
                "roles": sorted(set(roles)),
            }
        )
    return modules


def workflow_definitions() -> list[dict[str, Any]]:
    """Return workflow metadata with Mermaid graph definitions."""
    return [definition.__dict__ for definition in _known_workflows()]


def _known_workflows() -> list[WorkflowDefinition]:
    autopilot_nodes = [
        "ContextGatherNode",
        "SentryNode",
        "LogicDraftNode",
        "StyleDraftNode",
        "GuardNode",
        "RefineNode",
        "MemorySyncNode",
    ]
    autopilot_edges = [
        {"source": "ContextGatherNode", "target": "SentryNode", "label": "context"},
        {"source": "SentryNode", "target": "LogicDraftNode", "label": "test plan"},
        {"source": "LogicDraftNode", "target": "StyleDraftNode", "label": "patches"},
        {"source": "StyleDraftNode", "target": "GuardNode", "label": "styled patches"},
        {"source": "GuardNode", "target": "RefineNode", "label": "retry on reject"},
        {"source": "RefineNode", "target": "LogicDraftNode", "label": "refine"},
        {"source": "GuardNode", "target": "MemorySyncNode", "label": "approved"},
    ]

    managed_nodes = [
        "ContextGatherNode",
        "PlanWorkflowNode",
        "ImplementationNode",
        "AuditNode",
        "DebugOrValidationNode",
        "DocumentationNode",
        "ContextMapUpdateNode",
        "MemoryBankSyncNode",
        "FinalReportNode",
    ]
    managed_edges = [
        {"source": "ContextGatherNode", "target": "PlanWorkflowNode", "label": "files"},
        {"source": "PlanWorkflowNode", "target": "ImplementationNode", "label": "plan"},
        {"source": "ImplementationNode", "target": "AuditNode", "label": "changes"},
        {"source": "AuditNode", "target": "DebugOrValidationNode", "label": "findings"},
        {
            "source": "DebugOrValidationNode",
            "target": "ImplementationNode",
            "label": "retry blockers",
        },
        {
            "source": "DebugOrValidationNode",
            "target": "DocumentationNode",
            "label": "ready",
        },
        {"source": "DocumentationNode", "target": "ContextMapUpdateNode", "label": "docs"},
        {
            "source": "ContextMapUpdateNode",
            "target": "MemoryBankSyncNode",
            "label": "map",
        },
        {"source": "MemoryBankSyncNode", "target": "FinalReportNode", "label": "sync"},
    ]

    return [
        WorkflowDefinition(
            key="autopilot_graph",
            display_name="Autopilot Remediation Graph",
            source_file="agents/orchestrator_graph.py",
            nodes=autopilot_nodes,
            edges=autopilot_edges,
            mermaid=_to_mermaid(autopilot_edges),
            description="Recursive remediation workflow with guard-driven retry.",
        ),
        WorkflowDefinition(
            key="managed_workflow_graph",
            display_name="Managed Sub-Agent Workflow",
            source_file="agents/workflow_graph.py",
            nodes=managed_nodes,
            edges=managed_edges,
            mermaid=_to_mermaid(managed_edges),
            description="Router-selected workflow with audit and validation retry control.",
        ),
    ]


def _to_mermaid(edges: list[dict[str, str]]) -> str:
    lines = ["graph TD"]
    for edge in edges:
        source = edge["source"]
        target = edge["target"]
        label = edge.get("label", "")
        if label:
            lines.append(f"  {source} -->|{label}| {target}")
        else:
            lines.append(f"  {source} --> {target}")
    return "\n".join(lines)


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
