"""FastMCP CodeMode provider backed by session sandboxes or a local bridge."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import textwrap
from collections.abc import Sequence
from pathlib import Path
from time import perf_counter
from typing import Annotated, Any, Callable, Protocol
from uuid import uuid4

from fastmcp.exceptions import NotFoundError
from fastmcp.experimental.transforms.code_mode import CodeMode
from fastmcp.server.context import Context
from fastmcp.tools.base import Tool
from pydantic import Field

from .manager import SessionSandboxManager
from .models.errors import SandboxError, SandboxNotFoundError
from .models.models import (
    SandboxExecutionRequest,
    SandboxExecutionResult,
    SandboxPolicy,
    SandboxSession,
)


class SandboxSessionRunner(Protocol):
    async def run_in_session(
        self,
        session_id: str,
        request: SandboxExecutionRequest,
    ) -> SandboxExecutionResult: ...

    def create_session(
        self,
        session_id: str | None = None,
        *,
        repo_ref: str | None = None,
        policy: SandboxPolicy | None = None,
    ) -> SandboxSession: ...


class SessionSandboxProvider:
    """CodeMode provider that runs generated Python in a sandbox or local bridge."""

    def __init__(
        self,
        manager: SandboxSessionRunner,
        *,
        repo_root: Path | None = None,
        python_executable: str | None = None,
        output_limit_bytes: int = 16_384,
    ) -> None:
        self.manager = manager
        self.repo_root = (repo_root or Path.cwd()).resolve()
        self.python_executable = python_executable or sys.executable
        self.output_limit_bytes = output_limit_bytes

    async def run(
        self,
        code: str,
        *,
        inputs: dict[str, Any] | None = None,
        external_functions: dict[str, Callable[..., Any]] | None = None,
    ) -> dict[str, Any]:
        inputs = inputs or {}
        session_id = str(inputs.get("session_id") or "")
        if not session_id:
            raise SandboxNotFoundError(
                "CodeMode sandbox execution requires session_id."
            )
        if external_functions:
            return await self._run_local_bridge(
                code,
                session_id=session_id,
                timeout_seconds=int(inputs.get("timeout_seconds") or 0) or None,
                external_functions=external_functions,
            )
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

    async def _run_local_bridge(
        self,
        code: str,
        *,
        session_id: str,
        timeout_seconds: int | None,
        external_functions: dict[str, Callable[..., Any]],
    ) -> dict[str, Any]:
        started_at = perf_counter()
        with tempfile.TemporaryDirectory(prefix="mem-graph-execute-") as tmp_dir:
            ipc_dir = Path(tmp_dir)
            command = [self.python_executable, "-c", "<mem-graph execute>"]
            process = await asyncio.create_subprocess_exec(
                self.python_executable,
                "-c",
                _build_wrapped_program(code, ipc_dir),
                cwd=str(self.repo_root),
                env=_build_child_env(self.repo_root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            bridge_task = asyncio.create_task(
                _serve_external_functions(process, ipc_dir, external_functions)
            )
            timed_out = False
            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout_seconds,
                )
            except asyncio.TimeoutError:
                timed_out = True
                process.kill()
                stdout_bytes, stderr_bytes = await process.communicate()
            finally:
                if not bridge_task.done():
                    bridge_task.cancel()
                await asyncio.gather(bridge_task, return_exceptions=True)

            result_payload = _read_result_payload(ipc_dir)
            duration_seconds = perf_counter() - started_at
            return {
                "stdout": _trim_output(stdout_bytes.decode("utf-8", errors="replace")),
                "stderr": _trim_output(stderr_bytes.decode("utf-8", errors="replace")),
                "exit_code": process.returncode or 0,
                "timed_out": timed_out,
                "artifacts": [],
                "command": command,
                "duration_seconds": round(duration_seconds, 4),
                "session_id": session_id,
                "container_id": None,
                "result": result_payload.get("result"),
            }


class SessionCodeMode(CodeMode):
    """CodeMode variant that passes FastMCP request session_id to the provider."""

    VISIBLE_BACKEND_TOOLS = (
        "list_agents",
        "list_task_types",
        "system_inspect",
    )

    def __init__(
        self,
        *,
        sandbox_provider: SessionSandboxProvider,
        default_policy: SandboxPolicy | None = None,
    ) -> None:
        super().__init__(sandbox_provider=sandbox_provider)
        self.session_sandbox_provider = sandbox_provider
        self.default_policy = default_policy

    async def transform_tools(self, tools: Sequence[Tool]) -> Sequence[Tool]:
        visible = [
            tool
            for tool_name in self.VISIBLE_BACKEND_TOOLS
            for tool in tools
            if tool.name == tool_name
        ]
        return [*visible, *self._build_discovery_tools(), self._get_execute_tool()]

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
                Field(
                    description="Optional sandbox session id. Defaults to ctx.session_id."
                ),
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
                    "result": None,
                }

        return Tool.from_function(
            fn=execute,
            name=self.execute_tool_name,
            description=self._build_execute_description(),
        )


def build_session_code_mode(
    manager: SessionSandboxManager,
    *,
    repo_root: Path | None = None,
) -> SessionCodeMode:
    return SessionCodeMode(
        sandbox_provider=SessionSandboxProvider(manager, repo_root=repo_root)
    )


def _unwrap_tool_result(result: Any) -> dict[str, Any] | str:
    if getattr(result, "structured_content", None) is not None:
        return result.structured_content
    parts: list[str] = []
    for content in getattr(result, "content", []):
        text = getattr(content, "text", None)
        parts.append(text if text is not None else str(content))
    return "\n".join(parts)


def _build_child_env(repo_root: Path) -> dict[str, str]:
    env = os.environ.copy()
    python_path_entries: list[str] = []
    src_path = repo_root / "src"
    if src_path.exists():
        python_path_entries.append(str(src_path))
    existing = env.get("PYTHONPATH")
    if existing:
        python_path_entries.append(existing)
    if python_path_entries:
        env["PYTHONPATH"] = os.pathsep.join(python_path_entries)
    return env


def _build_wrapped_program(code: str, ipc_dir: Path) -> str:
    body = textwrap.indent(code if code.strip() else "return None", "    ")
    lines = [
        "import asyncio",
        "import json",
        "import pathlib",
        "import traceback",
        "import uuid",
        "",
        f"_IPC_DIR = pathlib.Path({str(ipc_dir)!r})",
        '_RESULT_PATH = _IPC_DIR / "result.json"',
        "",
        "async def call_tool(tool_name, arguments):",
        "    request_id = uuid.uuid4().hex",
        '    request_path = _IPC_DIR / f"request-{request_id}.json"',
        '    response_path = _IPC_DIR / f"response-{request_id}.json"',
        "    request_path.write_text(",
        "        json.dumps(",
        '            {"function": "call_tool", "arguments": [tool_name, arguments], "request_id": request_id}',
        "        ),",
        '        encoding="utf-8",',
        "    )",
        "    while not response_path.exists():",
        "        await asyncio.sleep(0.01)",
        '    payload = json.loads(response_path.read_text(encoding="utf-8"))',
        '    if payload.get("ok"):',
        '        return payload.get("result")',
        '    raise RuntimeError(payload.get("error", "Tool call failed."))',
        "",
        "async def __mem_graph_main__():",
        body,
        "",
        'if __name__ == "__main__":',
        "    try:",
        "        result = asyncio.run(__mem_graph_main__())",
        "    except Exception:",
        "        traceback.print_exc()",
        "        raise",
        "    else:",
        "        _RESULT_PATH.write_text(",
        '            json.dumps({"result": result}, default=str),',
        '            encoding="utf-8",',
        "        )",
    ]
    return "\n".join(lines)


async def _handle_external_request(
    request_path: Path,
    response_path: Path,
    external_functions: dict[str, Callable[..., Any]],
) -> None:
    payload = json.loads(request_path.read_text(encoding="utf-8"))
    function_name = str(payload.get("function") or "")
    arguments = payload.get("arguments", [])
    function = external_functions.get(function_name)
    if function is None:
        response = {
            "ok": False,
            "error": f"Unknown bridge function: {function_name}",
        }
    else:
        try:
            result = function(*arguments)
            if asyncio.iscoroutine(result):
                result = await result
            response = {"ok": True, "result": result}
        except Exception as exc:  # noqa: BLE001
            response = {"ok": False, "error": str(exc)}
    response_path.write_text(
        json.dumps(response, default=str), encoding="utf-8"
    )

async def _serve_external_functions(
    process: asyncio.subprocess.Process,
    ipc_dir: Path,
    external_functions: dict[str, Callable[..., Any]],
) -> None:
    while True:
        handled_request = False
        for request_path in sorted(ipc_dir.glob("request-*.json")):
            response_path = request_path.with_name(
                request_path.name.replace("request-", "response-", 1)
            )
            if response_path.exists():
                continue
            handled_request = True
            await _handle_external_request(request_path, response_path, external_functions)

        if process.returncode is not None and not handled_request:
            has_pending = any(
                not path.with_name(path.name.replace("request-", "response-", 1)).exists()
                for path in ipc_dir.glob("request-*.json")
            )
            if not has_pending:
                return
        await asyncio.sleep(0.01)


def _read_result_payload(ipc_dir: Path) -> dict[str, Any]:
    result_path = ipc_dir / "result.json"
    if not result_path.exists():
        return {}
    try:
        payload = json.loads(result_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _trim_output(value: str, *, limit: int = 16_384) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."
