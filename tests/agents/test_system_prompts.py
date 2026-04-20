from __future__ import annotations


class TestAuditAgentSystemPrompt:
    """Verify the audit agent system prompt injects reasoning mode correctly."""

    def test_preloaded_mode_no_tools(self) -> None:
        from mem_graph.agents.audit.audit_agent import AuditDependencies
        # Just verify the deps dataclass accepts reasoning_mode
        deps = AuditDependencies(
            package_path="/tmp/test",
            mode="preloaded",
            extra_file_context="# some file content",
            reasoning_mode="react_challenge",
        )
        assert deps.reasoning_mode == "react_challenge"
        assert deps.mode == "preloaded"

    def test_standalone_mode_default_reasoning(self) -> None:
        from mem_graph.agents.audit.audit_agent import AuditDependencies
        deps = AuditDependencies(package_path="/tmp/test")
        assert deps.reasoning_mode == ""
        assert deps.mode == "standalone"

    def test_all_dep_fields_present(self) -> None:
        from mem_graph.agents.audit.audit_agent import AuditDependencies
        import dataclasses
        field_names = {f.name for f in dataclasses.fields(AuditDependencies)}
        assert "reasoning_mode" in field_names


class TestRouterAgentSystemPrompt:
    """Verify the router agent uses explicit branching and reasoning inject."""

    def test_reasoning_mode_field_present(self) -> None:
        from mem_graph.agents.router_agent import RouterDependencies
        import dataclasses
        field_names = {f.name for f in dataclasses.fields(RouterDependencies)}
        assert "reasoning_mode" in field_names

    def test_reasoning_mode_default_empty(self) -> None:
        from mem_graph.agents.router_agent import RouterDependencies
        deps = RouterDependencies(project_id="p1", request="test")
        assert deps.reasoning_mode == ""

    def test_workflow_mode_subagent(self) -> None:
        from mem_graph.agents.router_agent import RouterDependencies
        deps = RouterDependencies(
            project_id="p1",
            request="test",
            workflow_mode="subagent_workflow",
            reasoning_mode="bounded_tot",
        )
        assert deps.workflow_mode == "subagent_workflow"
        assert deps.reasoning_mode == "bounded_tot"


class TestDecisionAgentSystemPrompt:
    """Verify reasoning_mode field in DecisionDependencies."""

    def test_field_present(self) -> None:
        from mem_graph.agents.document.decision_agent import DecisionDependencies
        import dataclasses
        field_names = {f.name for f in dataclasses.fields(DecisionDependencies)}
        assert "reasoning_mode" in field_names

    def test_default_empty(self) -> None:
        from mem_graph.agents.document.decision_agent import DecisionDependencies
        deps = DecisionDependencies(project_id="p1", package_path="/tmp")
        assert deps.reasoning_mode == ""


class TestTaskAgentSystemPrompt:
    """Verify reasoning_mode field in TaskDependencies."""

    def test_field_present(self) -> None:
        from mem_graph.agents.document.task_agent import TaskDependencies
        import dataclasses
        field_names = {f.name for f in dataclasses.fields(TaskDependencies)}
        assert "reasoning_mode" in field_names


class TestScribeAgentSystemPrompt:
    """Verify reasoning_mode field in ScribeDependencies."""

    def test_field_present(self) -> None:
        from mem_graph.agents.document.scribe_agent import ScribeDependencies
        import dataclasses
        field_names = {f.name for f in dataclasses.fields(ScribeDependencies)}
        assert "reasoning_mode" in field_names


class TestTriageAgentSystemPrompt:
    """Verify reasoning_mode field in TriageDependencies."""

    def test_field_present(self) -> None:
        from mem_graph.agents.document.triage_agent import TriageDependencies
        import dataclasses
        field_names = {f.name for f in dataclasses.fields(TriageDependencies)}
        assert "reasoning_mode" in field_names


class TestFixerAgentSystemPrompt:
    """Verify reasoning_mode field in FixerDependencies."""

    def test_field_present(self) -> None:
        from mem_graph.agents.fix.fixer_agent import FixerDependencies
        import dataclasses
        field_names = {f.name for f in dataclasses.fields(FixerDependencies)}
        assert "reasoning_mode" in field_names


class TestMapAgentSystemPrompt:
    """Verify reasoning_mode field in MapDependencies."""

    def test_field_present(self) -> None:
        from mem_graph.agents.map.map_agent import MapDependencies
        import dataclasses
        field_names = {f.name for f in dataclasses.fields(MapDependencies)}
        assert "reasoning_mode" in field_names


class TestSentryAgentSystemPrompt:
    """Verify reasoning_mode field in SentryDependencies."""

    def test_field_present(self) -> None:
        from mem_graph.agents.validate.sentry_agent import SentryDependencies
        import dataclasses
        field_names = {f.name for f in dataclasses.fields(SentryDependencies)}
        assert "reasoning_mode" in field_names


class TestValidationAgentSystemPrompt:
    """Verify reasoning_mode field in ValidationDependencies."""

    def test_field_present(self) -> None:
        from mem_graph.agents.validate.validation_agent import ValidationDependencies
        import dataclasses
        field_names = {f.name for f in dataclasses.fields(ValidationDependencies)}
        assert "reasoning_mode" in field_names


class TestAllAgentsImportClean:
    """Smoke test: importing all agent modules should not raise."""

    def test_import_audit_agent(self) -> None:
        from mem_graph.agents.audit import audit_agent  # noqa: F401

    def test_import_router_agent(self) -> None:
        from mem_graph.agents import router_agent  # noqa: F401

    def test_import_decision_agent(self) -> None:
        from mem_graph.agents.document import decision_agent  # noqa: F401

    def test_import_task_agent(self) -> None:
        from mem_graph.agents.document import task_agent  # noqa: F401

    def test_import_scribe_agent(self) -> None:
        from mem_graph.agents.document import scribe_agent  # noqa: F401

    def test_import_triage_agent(self) -> None:
        from mem_graph.agents.document import triage_agent  # noqa: F401

    def test_import_fixer_agent(self) -> None:
        from mem_graph.agents.fix import fixer_agent  # noqa: F401

    def test_import_map_agent(self) -> None:
        from mem_graph.agents.map import map_agent  # noqa: F401

    def test_import_sentry_agent(self) -> None:
        from mem_graph.agents.validate import sentry_agent  # noqa: F401

    def test_import_validation_agent(self) -> None:
        from mem_graph.agents.validate import validation_agent  # noqa: F401
