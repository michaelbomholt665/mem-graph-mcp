"""Tests for PROMPT_REGISTRY expansion (Task 031)."""

from __future__ import annotations

import pytest

from mem_graph.resources.prompts import (
    PROMPT_REGISTRY,
    build_tool_names_for_prompt,
    get_reasoning_mode_guidance,
)


EXPECTED_REASONING_KEYS = [
    "reasoning.react_challenge",
    "reasoning.react_2",
    "reasoning.bounded_tot",
    "reasoning.cot",
]

EXPECTED_STAGE_KEYS = [
    "stage.feature_implementation.sentry",
    "stage.feature_implementation.logic_draft",
    "stage.feature_implementation.scribe",
    "stage.feature_implementation.validation",
    "stage.refactor.mapping",
    "stage.refactor.audit",
    "stage.refactor.scribe",
    "stage.refactor.validation",
    "stage.security_hardening.audit",
    "stage.security_hardening.fix",
    "stage.security_hardening.validation",
    "stage.dependency_audit.discovery",
    "stage.dependency_audit.triage",
    "stage.dependency_audit.validation",
    "stage.code_review.sentry",
    "stage.code_review.audit",
    "stage.code_review.scribe",
    "stage.package_audit.audit",
    "stage.package_audit.triage",
    "stage.package_audit.fix",
    "stage.package_audit.validation",
    "stage.documentation.decision_review",
    "stage.documentation.task_decompose",
    "stage.documentation.scribe",
    "stage.codebase_migration.mapping",
    "stage.codebase_migration.audit",
    "stage.codebase_migration.fix",
    "stage.codebase_migration.validation",
    "stage.sync_context.sync",
]

EXPECTED_LEGACY_KEYS = [
    "sync_context",
    "plan_feature",
    "run_audit",
    "close_session",
    "workflow_agent",
    "agent_builder_discovery",
    "agent_builder_update",
]


class TestPromptRegistryKeys:
    """Verify PROMPT_REGISTRY has all required entries."""

    @pytest.mark.parametrize("key", EXPECTED_REASONING_KEYS)
    def test_reasoning_key_present(self, key: str) -> None:
        assert key in PROMPT_REGISTRY, f"Missing reasoning key: '{key}'"

    @pytest.mark.parametrize("key", EXPECTED_STAGE_KEYS)
    def test_stage_key_present(self, key: str) -> None:
        assert key in PROMPT_REGISTRY, f"Missing stage key: '{key}'"

    @pytest.mark.parametrize("key", EXPECTED_LEGACY_KEYS)
    def test_legacy_key_present(self, key: str) -> None:
        assert key in PROMPT_REGISTRY, f"Missing legacy key: '{key}'"

    def test_total_stage_keys(self) -> None:
        stage_keys = [k for k in PROMPT_REGISTRY if k.startswith("stage.")]
        assert len(stage_keys) >= 29, (
            f"Expected at least 29 stage keys, found {len(stage_keys)}"
        )


class TestPromptRegistryValues:
    """Verify all PROMPT_REGISTRY values are non-empty strings."""

    def test_all_values_non_empty(self) -> None:
        for key, val in PROMPT_REGISTRY.items():
            assert isinstance(val, str), f"Key '{key}' has non-string value"
            assert val.strip(), f"Key '{key}' has empty value"


class TestGetReasoningModeGuidance:
    """Unit tests for get_reasoning_mode_guidance()."""

    @pytest.mark.parametrize("mode", ["react_challenge", "react_2", "bounded_tot", "cot"])
    def test_known_mode_returns_content(self, mode: str) -> None:
        result = get_reasoning_mode_guidance(mode)
        assert isinstance(result, str)
        assert len(result) > 10, f"Mode '{mode}' returned unexpectedly short guidance"

    def test_unknown_mode_returns_empty(self) -> None:
        result = get_reasoning_mode_guidance("nonexistent_mode")
        assert result == ""


class TestBuildToolNamesForPrompt:
    """Unit tests for build_tool_names_for_prompt()."""

    def test_empty_list_returns_empty(self) -> None:
        result = build_tool_names_for_prompt([])
        assert result == ""

    def test_single_tool(self) -> None:
        result = build_tool_names_for_prompt(["list_files"])
        assert "list_files" in result
        assert "## Tools" in result

    def test_multiple_tools(self) -> None:
        tools = ["list_files", "process_batch", "finalize_report"]
        result = build_tool_names_for_prompt(tools)
        for t in tools:
            assert t in result

    def test_returns_string(self) -> None:
        result = build_tool_names_for_prompt(["tool_a", "tool_b"])
        assert isinstance(result, str)
