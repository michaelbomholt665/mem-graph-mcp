#!/usr/bin/env python3
# src/mem_graph/agents/builder/agent_builder.py
"""Validated project helper-agent spec creation and updates."""

from __future__ import annotations

from datetime import UTC, datetime
import os
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_ai import Agent, RunContext
import yaml  # type: ignore[import-untyped]

from ...config import DEFER_AGENT_MODEL_CHECK, config_get_model_for_workflow_stage
from ...models.evals import EvalReport
from ...resources.personas import PERSONA_REGISTRY
from ...resources.prompts import PROMPT_REGISTRY

HelperAgentType = Literal[
    "codebase-aware",
    "command-map",
    "memory-bank-builder",
]

_DEFAULT_HELPER_TYPES: tuple[HelperAgentType, ...] = (
    "codebase-aware",
    "command-map",
    "memory-bank-builder",
)
_MANIFEST_NAMES = {
    "pyproject.toml",
    "package.json",
    "Cargo.toml",
    "go.mod",
    "Makefile",
    "justfile",
    "Taskfile.yml",
}
_DOC_NAMES = {"README.md", "AGENTS.md", "CLAUDE.md", "LAST_SESSION.md"}
_DEFAULT_INITIAL_CHANGELOG = ["v1: Initial discovered helper-agent spec."]



class AgentEvalMetadata(BaseModel):
    """Eval suite/dataset metadata linked to a helper-agent spec."""

    suite: str | None = None
    dataset: str | None = None
    local_results_path: str | None = None
    hosted_dataset: str | None = None
    hosted_eval: str | None = None
    last_result_summary: str | None = None


class HelperAgentSpec(BaseModel):
    """Structured, reviewable project helper-agent specification."""

    name: str
    helper_type: HelperAgentType
    purpose: str
    persona_key: str
    prompt_key: str
    recommended_model: str
    allowed_tools: list[str] = Field(default_factory=list)
    system_prompt: str = ""
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    eval_metadata: AgentEvalMetadata = Field(default_factory=AgentEvalMetadata)
    version: int = 1
    last_updated: str = Field(default_factory=lambda: _utc_now())
    changelog: list[str] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("name cannot be empty")
        return value.strip()

    @model_validator(mode="after")
    def validate_registry_links(self) -> "HelperAgentSpec":
        if self.persona_key not in PERSONA_REGISTRY:
            raise ValueError(f"unknown persona_key: {self.persona_key}")
        if self.prompt_key not in PROMPT_REGISTRY:
            raise ValueError(f"unknown prompt_key: {self.prompt_key}")
        return self


class AgentBuilderReport(BaseModel):
    """Discovery or update report for helper-agent specs."""

    project_id: str
    project_root: str
    recommended_specs: list[HelperAgentSpec] = Field(default_factory=list)
    existing_specs: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class AgentBuilderDependencies(BaseModel):
    """Runtime dependencies for builder discovery/update agents."""

    project_root: str
    project_id: str
    requested_helper_types: list[HelperAgentType] = Field(default_factory=list)


class AgentBuilderUpdateProposal(BaseModel):
    """Reviewable proposed helper-agent spec changes from eval evidence."""

    spec_name: str
    current_version: int
    recommended_changes: dict[str, Any] = Field(default_factory=dict)
    failure_patterns: list[str] = Field(default_factory=list)
    rationale: str = ""
    should_update: bool = False


agent_builder_discovery_agent: Agent[
    AgentBuilderDependencies,
    AgentBuilderReport,
] = Agent(
    config_get_model_for_workflow_stage("planning"),
    name="agent-builder-discovery",
    deps_type=AgentBuilderDependencies,
    output_type=AgentBuilderReport,
    defer_model_check=DEFER_AGENT_MODEL_CHECK,
)


@agent_builder_discovery_agent.system_prompt
async def _builder_discovery_prompt(ctx: RunContext[AgentBuilderDependencies]) -> str:
    persona = PERSONA_REGISTRY["agent_builder"].get_system_instructions()
    return f"""{persona}

{PROMPT_REGISTRY["agent_builder_discovery"]}

Project ID: {ctx.deps.project_id}
Project root: {ctx.deps.project_root}

Call `agent_builder_discover_project` before returning your AgentBuilderReport.
"""


@agent_builder_discovery_agent.tool
async def agent_builder_discover_project(
    ctx: RunContext[AgentBuilderDependencies],
) -> AgentBuilderReport:
    """Run deterministic project helper-agent discovery."""
    return discover_helper_agent_specs(ctx.deps.project_root, ctx.deps.project_id)


def discover_helper_agent_specs(project_root: str | Path, project_id: str) -> AgentBuilderReport:
    """
    Inspect a project and recommend initial helper-agent specs.

    Discovery is deterministic and local: it reads file names and small command
    surfaces, then returns validated specs. Writing remains a separate explicit
    operation.
    """
    root = Path(project_root).resolve()
    discovered_files = _discover_project_files(root)
    existing_specs = [
        str(path)
        for path in sorted(_project_agent_dir(root, project_id).glob("*.yaml"))
    ]
    notes = _build_discovery_notes(discovered_files)
    specs = [
        _build_default_spec(helper_type, project_id, discovered_files)
        for helper_type in _DEFAULT_HELPER_TYPES
    ]
    return AgentBuilderReport(
        project_id=project_id,
        project_root=str(root),
        recommended_specs=specs,
        existing_specs=existing_specs,
        notes=notes,
    )


def write_helper_agent_spec(
    spec: HelperAgentSpec,
    project_root: str | Path,
    project_id: str,
    *,
    update_existing: bool = False,
) -> tuple[Path, Path]:
    """
    Write a helper-agent spec and project-local tracking YAML.

    Existing files are protected unless update_existing is true, which gives
    callers a deliberate update path.
    """
    root = Path(project_root).resolve()
    spec_path = _project_agent_path(root, project_id, spec.helper_type)
    tracking_path = _tracking_path(root, spec.helper_type)
    if not update_existing:
        for path in (spec_path, tracking_path):
            if path.exists():
                raise FileExistsError(f"Refusing to overwrite existing spec: {path}")

    spec_path.parent.mkdir(parents=True, exist_ok=True)
    tracking_path.parent.mkdir(parents=True, exist_ok=True)
    payload = _spec_to_yaml(spec)
    spec_path.write_text(payload, encoding="utf-8")
    tracking_path.write_text(payload, encoding="utf-8")
    return spec_path, tracking_path


def list_helper_agent_specs(
    project_root: str | Path,
    project_id: str,
) -> list[HelperAgentSpec]:
    """Load all helper-agent specs registered for a project."""
    root = Path(project_root).resolve()
    paths = sorted(_project_agent_dir(root, project_id).glob("*.yaml"))
    return [load_helper_agent_spec(path) for path in paths]


def find_helper_agent_spec(
    project_root: str | Path,
    project_id: str,
    name_or_type: str,
) -> HelperAgentSpec | None:
    """Find a project helper-agent spec by name or helper type."""
    for spec in list_helper_agent_specs(project_root, project_id):
        if spec.name == name_or_type or spec.helper_type == name_or_type:
            return spec
    return None


def load_helper_agent_spec(path: str | Path) -> HelperAgentSpec:
    """Load and validate one helper-agent YAML spec."""
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Invalid helper-agent spec payload: {path}")
    return HelperAgentSpec.model_validate(raw)


def update_helper_agent_spec(
    current: HelperAgentSpec,
    *,
    proposed_changes: dict[str, Any],
    reason: str,
) -> HelperAgentSpec:
    """
    Apply explicit, reviewable updates to a helper-agent spec.

    The caller decides whether to persist the returned spec.
    """
    protected = {"name", "helper_type", "version", "last_updated", "changelog"}
    update_data = {
        key: value
        for key, value in proposed_changes.items()
        if key not in protected
    }
    updated = current.model_copy(update=update_data)
    updated.version = current.version + 1
    updated.last_updated = _utc_now()
    updated.changelog = [
        *current.changelog,
        f"v{updated.version}: {reason}",
    ]
    return HelperAgentSpec.model_validate(updated.model_dump())


def load_eval_report_summary(path: str | Path) -> tuple[EvalReport, list[str]]:
    """Load a local eval JSON report and summarize failure patterns."""
    import json

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    report = EvalReport.model_validate(payload)
    patterns: list[str] = []
    for suite in report.suite_results:
        for case in suite.case_results:
            if case.passed:
                continue
            if case.failure_details:
                patterns.append(
                    f"{suite.suite_name}/{case.case_id}: {case.failure_details[-1].reason}"
                )
            else:
                patterns.append(
                    f"{suite.suite_name}/{case.case_id}: pass_rate {case.pass_rate:.0%}"
                )
    return report, patterns


def propose_helper_agent_update(
    spec: HelperAgentSpec,
    *,
    local_eval_report_path: str | Path | None = None,
    hosted_result_summary: str | None = None,
) -> AgentBuilderUpdateProposal:
    """
    Propose spec changes from eval evidence without writing them.

    This keeps eval-driven improvement reviewable; callers must explicitly
    pass the proposal into `update_helper_agent_spec` and then persist.
    """
    failure_patterns: list[str] = []
    result_summary = hosted_result_summary
    if local_eval_report_path is not None:
        _report, failure_patterns = load_eval_report_summary(local_eval_report_path)
        result_summary = (
            f"{len(failure_patterns)} failing eval pattern(s) from {local_eval_report_path}"
        )

    if not failure_patterns and not hosted_result_summary:
        return AgentBuilderUpdateProposal(
            spec_name=spec.name,
            current_version=spec.version,
            rationale="No eval failures or hosted result summary were provided.",
        )

    changes: dict[str, Any] = {
        "eval_metadata": spec.eval_metadata.model_copy(
            update={"last_result_summary": result_summary}
        ).model_dump(),
        "system_prompt": _append_eval_guidance(spec.system_prompt, failure_patterns),
    }
    return AgentBuilderUpdateProposal(
        spec_name=spec.name,
        current_version=spec.version,
        recommended_changes=changes,
        failure_patterns=failure_patterns,
        rationale="Eval evidence suggests tightening prompt guidance for recurring failures.",
        should_update=True,
    )


def _build_default_spec(
    helper_type: HelperAgentType,
    project_id: str,
    discovered_files: list[str],
) -> HelperAgentSpec:
    if helper_type == "codebase-aware":
        return HelperAgentSpec(
            name=f"{project_id}-codebase-aware",
            helper_type=helper_type,
            purpose="Maintain project architecture, conventions, and important-file context.",
            persona_key="architect",
            prompt_key="agent_builder_discovery",
            recommended_model=config_get_model_for_workflow_stage("context_gather"),
            allowed_tools=["file_read", "file_search", "file_grep"],
            system_prompt=PROMPT_REGISTRY["agent_builder_discovery"],
            inputs=["project_root", "manifest files", "docs", "context map"],
            outputs=["architecture summary", "important files", "project conventions"],
            eval_metadata=AgentEvalMetadata(suite="map", dataset="map-golden-set"),
            changelog=_DEFAULT_INITIAL_CHANGELOG,
        )

    if helper_type == "command-map":
        return HelperAgentSpec(
            name=f"{project_id}-command-map",
            helper_type=helper_type,
            purpose="Discover and maintain scripts, test, build, lint, typecheck, and operations commands.",
            persona_key="router",
            prompt_key="agent_builder_discovery",
            recommended_model=config_get_model_for_workflow_stage("planning"),
            allowed_tools=["file_read", "file_search", "file_grep"],
            system_prompt=_command_surface_prompt(discovered_files),
            inputs=["project manifests", "scripts", "CI config", "README command sections"],
            outputs=["command map", "quality gate commands", "operational entry points"],
            eval_metadata=AgentEvalMetadata(suite="validate", dataset="validate-golden-set"),
            changelog=_DEFAULT_INITIAL_CHANGELOG,
        )

    return HelperAgentSpec(
        name=f"{project_id}-memory-bank-builder",
        helper_type=helper_type,
        purpose="Build and refresh the project memory bank from codebase maps, decisions, and session notes.",
        persona_key="chat",
        prompt_key="sync_context",
        recommended_model=config_get_model_for_workflow_stage("memory_bank_sync"),
        allowed_tools=["file_read", "file_search", "file_grep", "file_write", "file_edit"],
        system_prompt=PROMPT_REGISTRY["sync_context"],
        inputs=["context map", "decisions", "tasks", "LAST_SESSION.md"],
        outputs=["memory bank update", "context summary", "stale-memory findings"],
        eval_metadata=AgentEvalMetadata(suite="document", dataset="document-golden-set"),
        changelog=_DEFAULT_INITIAL_CHANGELOG,
    )



def _discover_project_files(root: Path) -> list[str]:
    if not root.exists():
        return []
    results: list[str] = []
    for current_root, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in {".git", ".venv", "__pycache__"}]
        for filename in files:
            rel = Path(current_root, filename).relative_to(root).as_posix()
            if filename in _MANIFEST_NAMES or filename in _DOC_NAMES or rel.startswith(".github/"):
                results.append(rel)
            if len(results) >= 200:
                return sorted(results)
    return sorted(results)


def _build_discovery_notes(discovered_files: list[str]) -> list[str]:
    manifests = sorted(path for path in discovered_files if Path(path).name in _MANIFEST_NAMES)
    docs = sorted(path for path in discovered_files if Path(path).name in _DOC_NAMES)
    notes = [
        f"Detected manifests: {', '.join(manifests) if manifests else 'none'}",
        f"Detected docs/session files: {', '.join(docs) if docs else 'none'}",
    ]
    if any(path.startswith(".github/") for path in discovered_files):
        notes.append("Detected GitHub workflow files for command-map discovery.")
    return notes


def _command_surface_prompt(discovered_files: list[str]) -> str:
    files = "\n".join(f"- {path}" for path in discovered_files[:50])
    return (
        f"{PROMPT_REGISTRY['agent_builder_discovery']}\n\n"
        "Focus on commands and entry points discoverable from these files:\n"
        f"{files or '- No manifest or documentation files detected.'}"
    )


def _project_agent_dir(root: Path, project_id: str) -> Path:
    return root / "agents" / project_id


def _project_agent_path(root: Path, project_id: str, helper_type: HelperAgentType) -> Path:
    return _project_agent_dir(root, project_id) / f"{helper_type}.yaml"


def _tracking_path(root: Path, helper_type: HelperAgentType) -> Path:
    return root / "data" / "agents" / f"{helper_type}.yaml"


def _spec_to_yaml(spec: HelperAgentSpec) -> str:
    return yaml.safe_dump(spec.model_dump(mode="json"), sort_keys=False)


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _append_eval_guidance(system_prompt: str, failure_patterns: list[str]) -> str:
    if not failure_patterns:
        return system_prompt
    guidance = "\n".join(f"- {pattern}" for pattern in failure_patterns[:10])
    block = f"\n\n## Eval Failure Patterns To Address\n{guidance}"
    if "## Eval Failure Patterns To Address" in system_prompt:
        return system_prompt
    return f"{system_prompt.rstrip()}{block}"
