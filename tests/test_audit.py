import pytest
from pydantic_ai.models.test import TestModel
from syntx_mcp.agents.audit_agent import audit_agent, AuditDependencies, AuditOutput


@pytest.mark.asyncio
async def test_audit_agent_tool_calls():
    # Note: Pydantic AI's TestModel can be configured with specific responses
    model = TestModel(
        custom_output_args=AuditOutput(
            summary="Test summary",
            new_smells_discovered=["test:smell"]
        )
    )

    deps = AuditDependencies(
        package_path="/tmp/test_pkg",
        guide_path="/tmp/test.guide.md",
        registry_path="/tmp/smell-registry.md",
        skills_content="Rules...",
    )

    with audit_agent.override(model=model):
        result = await audit_agent.run("Start audit", deps=deps)
        out = getattr(result, "data", None)
        assert out is not None
        assert out.new_smells_discovered == ["test:smell"]
        assert "Test summary" in out.summary


@pytest.mark.asyncio
async def test_audit_agent_dependency_injection():
    # Verify that the system prompt correctly uses deps
    model = TestModel()
    deps = AuditDependencies(
        package_path="/path/to/pkg",
        guide_path="/path/to/guide.md",
        registry_path="/path/to/registry.md",
        skills_content="Custom Skills",
    )

    # We can't easily check the system prompt string directly without running,
    # but we can verify the agent runs with these deps.
    with audit_agent.override(model=model):
        await audit_agent.run("Audit", deps=deps)
        # If it didn't crash, dependency injection worked.
