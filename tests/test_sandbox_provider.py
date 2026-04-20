from __future__ import annotations

import anyio
import pytest

from mem_graph.sandbox.models.errors import SandboxNotFoundError
from mem_graph.sandbox.models.models import SandboxExecutionResult
from mem_graph.sandbox.provider import SessionSandboxProvider


class FakeManager:
    async def run_in_session(self, session_id, request):
        await anyio.sleep(0)
        return SandboxExecutionResult(stdout="ran", exit_code=0, session_id=session_id)


@pytest.mark.asyncio
async def test_provider_requires_session_id():
    provider = SessionSandboxProvider(FakeManager())  # type: ignore[arg-type]

    with pytest.raises(SandboxNotFoundError):
        await provider.run("print('x')")


@pytest.mark.asyncio
async def test_provider_returns_structured_execution_result():
    provider = SessionSandboxProvider(FakeManager())  # type: ignore[arg-type]

    result = await provider.run("print('x')", inputs={"session_id": "s1"})

    assert result["stdout"] == "ran"
    assert result["exit_code"] == 0
    assert result["timed_out"] is False
