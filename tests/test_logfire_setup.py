from __future__ import annotations

import importlib
from pathlib import Path
from unittest.mock import patch


def test_logfire_setup_uses_safe_defaults(monkeypatch) -> None:
    monkeypatch.delenv("LOGFIRE_TOKEN", raising=False)
    monkeypatch.setenv("MEM_GRAPH_LOGFIRE_ENABLED", "true")
    monkeypatch.delenv("MEM_GRAPH_LOGFIRE_INCLUDE_CONTENT", raising=False)
    monkeypatch.delenv("MEM_GRAPH_LOGFIRE_INSTRUMENT_HTTPX", raising=False)
    monkeypatch.delenv("MEM_GRAPH_LOGFIRE_CAPTURE_HTTPX", raising=False)

    import mem_graph.observability.logfire_setup as logfire_setup

    importlib.reload(logfire_setup)

    try:
        with (
            patch.object(logfire_setup.logfire, "configure") as configure,
            patch.object(
                logfire_setup.logfire, "instrument_pydantic_ai"
            ) as instrument_pydantic_ai,
            patch.object(logfire_setup.logfire, "instrument_mcp") as instrument_mcp,
            patch.object(logfire_setup.logfire, "instrument_httpx") as instrument_httpx,
            patch.object(logfire_setup.logging.getLogger(logfire_setup.__name__), "info") as logger_info,
        ):
            state = logfire_setup.setup_logfire(
                service_name="syntx-memory",
                service_version="0.2.0",
            )

        assert state.enabled is True
        assert state.send_to_logfire == "if-token-present"
        assert state.capture_content is False
        configure.assert_called_once()
        assert configure.call_args.kwargs["inspect_arguments"] is False
        instrument_pydantic_ai.assert_called_once()
        instrument_mcp.assert_called_once()
        assert instrument_pydantic_ai.call_args.kwargs["include_content"] is False
        assert instrument_pydantic_ai.call_args.kwargs["version"] == 3
        instrument_httpx.assert_called_once_with(capture_all=False)
        logger_info.assert_called_once_with("Logfire bootstrap ready (via stderr)")
    finally:
        logfire_setup._STATE = None


def test_server_bootstraps_observability_before_agent_imports() -> None:
    server_path = Path(__file__).resolve().parents[1] / "src/mem_graph/server.py"
    source = server_path.read_text()

    setup_index = source.index("setup_logfire(service_name=SERVER_NAME")
    fastmcp_import_index = source.index("from fastmcp import FastMCP")
    agents_import_index = source.index("from .tools.agents import")

    assert setup_index < fastmcp_import_index
    assert setup_index < agents_import_index
