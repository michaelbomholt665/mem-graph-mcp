import os
import anyio
from dataclasses import dataclass
from typing import List

from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext


class AuditOutput(BaseModel):
    summary: str = Field(
        description="A brief human-readable summary of the audit findings and actions taken."
    )
    new_smells_discovered: List[str] = Field(
        description="List of new smell IDs that were added to the registry."
    )


@dataclass
class AuditDependencies:
    package_path: str
    guide_path: str
    registry_path: str
    skills_content: str


audit_agent = Agent(
    "openai:gpt-4o",
    deps_type=AuditDependencies,
    output_type=AuditOutput,
)


@audit_agent.system_prompt
async def add_context_prompt(ctx: RunContext[AuditDependencies]) -> str:
    # Read the current contents of the guide and registry
    try:
        guide_content = await anyio.Path(ctx.deps.guide_path).read_text(encoding="utf-8")
    except Exception as e:
        guide_content = f"Error reading guide: {e}"

    try:
        registry_content = await anyio.Path(ctx.deps.registry_path).read_text(encoding="utf-8")
    except Exception as e:
        registry_content = f"Error reading registry: {e}"

    return f"""You are an Audit Agent. Your goal is to audit a software package against its current coding guidelines.

## Domain Knowledge / Skills
{ctx.deps.skills_content}

## Context
- Auditing Package Path: {ctx.deps.package_path}
- Package Guide Path: {ctx.deps.guide_path}
- Smell Registry Path: {ctx.deps.registry_path}

## Current Guidelines (Guide Content)
---
{guide_content}
---

## Current Smell Registry (Registry Content)
---
{registry_content}
---

## Objective
1. Actively browse the source code in {ctx.deps.package_path}.
2. Identify recurring violation classes (not one-off bugs).
3. If a new smell is found, use `update_registry` to add it.
4. Use `update_guide` to evolve the package-specific guidelines with the new smell.
5. Finally, return a summary of your actions.

Prefer one stable `smell_id` per normalized violation class (e.g. `go:ImportBoundaryViolation`).
"""


@audit_agent.tool
async def list_package_files(
    ctx: RunContext[AuditDependencies], extension: str = ".go"
) -> List[str]:
    """List all files in the package directory with the given extension."""
    import glob

    pattern = os.path.join(ctx.deps.package_path, f"**/*{extension}")
    return glob.glob(pattern, recursive=True)


@audit_agent.tool
async def read_file(ctx: RunContext[AuditDependencies], file_path: str) -> str:
    """Read the contents of a specific file."""
    if not os.path.exists(file_path):
        return f"Error: File not found at {file_path}"
    try:
        return await anyio.Path(file_path).read_text(encoding="utf-8")
    except Exception as e:
        return f"Error reading file: {e}"


@audit_agent.tool
async def update_guide(ctx: RunContext[AuditDependencies], new_content: str) -> str:
    """Update the package guide with revised content. Use this to add new guidelines or refine existing ones."""
    try:
        await anyio.Path(ctx.deps.guide_path).write_text(new_content, encoding="utf-8")
        return f"Successfully updated guide at {ctx.deps.guide_path}"
    except Exception as e:
        return f"Failed to update guide: {e}"


@audit_agent.tool
async def update_registry(ctx: RunContext[AuditDependencies], new_content: str) -> str:
    """Update the smell registry with revised content. Use this to add new smell definitions."""
    try:
        await anyio.Path(ctx.deps.registry_path).write_text(new_content, encoding="utf-8")
        return f"Successfully updated registry at {ctx.deps.registry_path}"
    except Exception as e:
        return f"Failed to update registry: {e}"
