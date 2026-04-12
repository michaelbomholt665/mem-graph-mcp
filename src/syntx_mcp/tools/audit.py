import os
import logging
import anyio
from typing import Annotated
from fastmcp import FastMCP
from pydantic import Field

from ..agents.audit_agent import audit_agent, AuditDependencies

# Setup logging to see agent progress
logger = logging.getLogger(__name__)

mcp = FastMCP("audit", instructions="Perform package codebase audits.")


@mcp.tool(tags={"namespace:audit"})
async def audit_package(
    package_path: Annotated[
        str,
        Field(
            description="The directory path to the code package being audited (e.g. /home/michael/projects/go/lakehouse/internal/managers/database)"
        ),
    ],
    guide_file_path: Annotated[
        str, Field(description="The absolute path to the package's specific .guide.md file")
    ],
    registry_file_path: Annotated[
        str, Field(description="The absolute path to the smell-registry.md file")
    ],
) -> str:
    """
    Run an automated codebase audit on the given package using the AI Audit Agent.
    The agent will review the package structure, read source files, and iteratively
    suggest updates to both the guide file and the smell registry based on findings.
    The files on disk will be updated automatically via tools.
    """
    if not os.path.exists(package_path):
        return f"Error: package path {package_path} not found."

    # Load Skills from the FastMCP Skill Library location
    skills_path = os.path.join(os.getcwd(), "skills", "audit_agent", "SKILL.md")
    skills_content = ""
    if os.path.exists(skills_path):
        try:
            async with await anyio.open_file(skills_path, "r", encoding="utf-8") as f:
                skills_content = await f.read()
        except Exception as e:
            logger.warning(f"Failed to load skills from {skills_path}: {e}")

    deps = AuditDependencies(
        package_path=package_path,
        guide_path=guide_file_path,
        registry_path=registry_file_path,
        skills_content=skills_content,
    )

    prompt = "Audit the package now. Use your tools to list and read the source files, then identify any new smells. Use update_registry and update_guide to save your findings dynamically."

    try:
        # Use streaming to observe progress
        async with audit_agent.run_stream(prompt, deps=deps) as result:
            final_result = await result.get_output()

        added_smells = (
            ", ".join(final_result.new_smells_discovered)
            if final_result.new_smells_discovered
            else "none"
        )
        return (
            f"Audit complete. {final_result.summary}\nNew smells added: {added_smells}"
        )

    except Exception as e:
        return f"Audit execution failed: {e}"
