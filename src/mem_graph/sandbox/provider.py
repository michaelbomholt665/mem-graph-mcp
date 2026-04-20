"""FastMCP CodeMode sandbox provider backed by session containers."""

from __future__ import annotations

from typing import Annotated, Any, Callable
from uuid import uuid4

from fastmcp.exceptions import NotFoundError
from fastmcp.experimental.transforms.code_mode import CodeMode
from fastmcp.server.context import Context
from fastmcp.tools.base import Tool
from pydantic import Field

from .models.errors import SandboxError, SandboxNotFoundError
from .manager import SessionSandboxManager
from .models.models import SandboxExecutionRequest, SandboxExecutionResult, SandboxPolicy


class SessionSandboxProvider:
    """CodeMode provider that runs generated Python in a session sandbox."""

    def __init__(self, manager: SessionSandboxManager) -> None:
        self.manager = manager

    async def run(
        self,
        code: str,
        *,
        inputs: dict[str, Any] | None = None,
        external_functions: dict[str, Callable[..., Any]] | None = None,
    ) -> dict[str, Any]:
        del external_functions
        inputs = inputs or {}
        session_id = str(inputs.get("session_id") or "")
        if not session_id:
            raise SandboxNotFoundError("CodeMode sandbox execution requires session_id.")
        request = SandboxExecutionRequest(
            code=code,
            timeout_seconds=int(inputs.get("timeout_seconds") or 0) or None,
        )
        result = await self.manager.run_in_session(session_id, request)
        return result.model_dump(mode="json")

    async def run_structured(
        self,
        session_id: str,
        request: SandboxExecutionRequest,
    ) -> SandboxExecutionResult:
        return await self.manager.run_in_session(session_id, request)


class SessionCodeMode(CodeMode):
    """CodeMode variant that passes FastMCP request session_id to the provider."""

    def __init__(
        self,
        *,
        sandbox_provider: SessionSandboxProvider,
        default_policy: SandboxPolicy | None = None,
    ) -> None:
        super().__init__(sandbox_provider=sandbox_provider)
        self.session_sandbox_provider = sandbox_provider
        self.default_policy = default_policy

    def _make_execute_tool(self) -> Tool:
        transform = self

        async def execute(
            code: Annotated[
                str,
                Field(
                    description=(
                        "Python async code to execute tool calls via call_tool(name, arguments)"
                    )
                ),
            ],
            session_id: Annotated[
                str | None,
                Field(description="Optional sandbox session id. Defaults to ctx.session_id."),
            ] = None,
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Any:
            async def call_tool(tool_name: str, params: dict[str, Any]) -> Any:
                backend_tools = await transform.get_tool_catalog(ctx)
                tool = transform._find_tool(tool_name, backend_tools)
                if tool is None:
                    raise NotFoundError(f"Unknown tool: {tool_name}")
                result = await ctx.fastmcp.call_tool(tool.name, params)
                return _unwrap_tool_result(result)

            effective_session_id = session_id or getattr(ctx, "session_id", None)
            if effective_session_id is None:
                effective_session_id = str(uuid4())
                transform.session_sandbox_provider.manager.create_session(
                    effective_session_id,
                    policy=transform.default_policy,
                )
            try:
                return await transform.sandbox_provider.run(
                    code,
                    inputs={"session_id": effective_session_id},
                    external_functions={"call_tool": call_tool},
                )
            except SandboxError as exc:
                return {
                    "stdout": "",
                    "stderr": str(exc),
                    "exit_code": 1,
                    "timed_out": False,
                    "artifacts": [],
                    "session_id": effective_session_id,
                }

        return Tool.from_function(
            fn=execute,
            name=self.execute_tool_name,
            description=self._build_execute_description(),
        )


def build_session_code_mode(manager: SessionSandboxManager) -> SessionCodeMode:
    return SessionCodeMode(sandbox_provider=SessionSandboxProvider(manager))


def _unwrap_tool_result(result: Any) -> dict[str, Any] | str:
    if getattr(result, "structured_content", None) is not None:
        return result.structured_content
    parts: list[str] = []
    for content in getattr(result, "content", []):
        text = getattr(content, "text", None)
        parts.append(text if text is not None else str(content))
    return "\n".join(parts)
