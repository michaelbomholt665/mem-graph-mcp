"""Evals registry and exports for the mem-graph agent suites."""

from __future__ import annotations

from ..models.evals import EvalMode, SuiteBinding
from .audit_evals import (
    AUDIT_EVAL_SUITE,
    build_audit_binding,
    push_audit_dataset,
    run_audit_eval,
)
from .document_evals import (
    DOCUMENT_EVAL_SUITE,
    build_document_binding,
    push_document_dataset,
    run_document_eval,
)
from .fix_evals import FIX_EVAL_SUITE, build_fix_binding, push_fix_dataset, run_fix_eval
from .map_evals import MAP_EVAL_SUITE, build_map_binding, push_map_dataset, run_map_eval
from .suites import (
    CHAT_EVAL_SUITE,
    GO_QUALITY_SKILL_EVAL_SUITE,
    ORCHESTRATOR_EVAL_SUITE,
    PYTHON_QUALITY_SKILL_EVAL_SUITE,
    ROUTER_EVAL_SUITE,
    RULE_INJECTOR_EVAL_SUITE,
    SECURITY_SKILL_EVAL_SUITE,
    SENTRY_EVAL_SUITE,
    TRIAGE_EVAL_SUITE,
    TYPESCRIPT_QUALITY_SKILL_EVAL_SUITE,
    WORKFLOW_AUTOPILOT_EVAL_SUITE,
    WORKFLOW_FEATURE_IMPLEMENTATION_EVAL_SUITE,
    WORKFLOW_PACKAGE_AUDIT_EVAL_SUITE,
    build_chat_binding,
    build_go_quality_skill_binding,
    build_orchestrator_binding,
    build_python_quality_skill_binding,
    build_router_binding,
    build_rule_injector_binding,
    build_security_skill_binding,
    build_sentry_binding,
    build_triage_binding,
    build_typescript_quality_skill_binding,
    build_workflow_autopilot_binding,
    build_workflow_feature_implementation_binding,
    build_workflow_package_audit_binding,
    push_chat_dataset,
    push_go_quality_skill_dataset,
    push_orchestrator_dataset,
    push_python_quality_skill_dataset,
    push_router_dataset,
    push_rule_injector_dataset,
    push_security_skill_dataset,
    push_sentry_dataset,
    push_triage_dataset,
    push_typescript_quality_skill_dataset,
    push_workflow_autopilot_dataset,
    push_workflow_feature_implementation_dataset,
    push_workflow_package_audit_dataset,
    run_chat_eval,
    run_go_quality_skill_eval,
    run_orchestrator_eval,
    run_python_quality_skill_eval,
    run_router_eval,
    run_rule_injector_eval,
    run_security_skill_eval,
    run_sentry_eval,
    run_triage_eval,
    run_typescript_quality_skill_eval,
    run_workflow_autopilot_eval,
    run_workflow_feature_implementation_eval,
    run_workflow_package_audit_eval,
)
from .validate_evals import (
    VALIDATE_EVAL_SUITE,
    build_validate_binding,
    push_validate_dataset,
    run_validate_eval,
)


def build_suite_registry(mode: EvalMode = "fixture") -> dict[str, SuiteBinding]:
    return {
        "audit": build_audit_binding(mode),
        "chat": build_chat_binding(mode),
        "document": build_document_binding(mode),
        "fix": build_fix_binding(mode),
        "orchestrator": build_orchestrator_binding(mode),
        "map": build_map_binding(mode),
        "router": build_router_binding(mode),
        "rule_injector": build_rule_injector_binding(mode),
        "sentry": build_sentry_binding(mode),
        "skill_go_quality": build_go_quality_skill_binding(mode),
        "skill_python_quality": build_python_quality_skill_binding(mode),
        "skill_security": build_security_skill_binding(mode),
        "skill_typescript_quality": build_typescript_quality_skill_binding(mode),
        "triage": build_triage_binding(mode),
        "validate": build_validate_binding(mode),
        "workflow_autopilot": build_workflow_autopilot_binding(mode),
        "workflow_feature_implementation": build_workflow_feature_implementation_binding(
            mode
        ),
        "workflow_package_audit": build_workflow_package_audit_binding(mode),
    }


def push_hosted_datasets(selected_suites: list[str] | None = None) -> dict[str, object]:
    pushers = {
        "audit": push_audit_dataset,
        "chat": push_chat_dataset,
        "document": push_document_dataset,
        "fix": push_fix_dataset,
        "map": push_map_dataset,
        "orchestrator": push_orchestrator_dataset,
        "router": push_router_dataset,
        "rule_injector": push_rule_injector_dataset,
        "sentry": push_sentry_dataset,
        "skill_go_quality": push_go_quality_skill_dataset,
        "skill_python_quality": push_python_quality_skill_dataset,
        "skill_security": push_security_skill_dataset,
        "skill_typescript_quality": push_typescript_quality_skill_dataset,
        "triage": push_triage_dataset,
        "validate": push_validate_dataset,
        "workflow_autopilot": push_workflow_autopilot_dataset,
        "workflow_feature_implementation": push_workflow_feature_implementation_dataset,
        "workflow_package_audit": push_workflow_package_audit_dataset,
    }
    suite_names = selected_suites or list(pushers)
    missing = [name for name in suite_names if name not in pushers]
    if missing:
        raise ValueError(
            f"Unknown eval suite(s): {', '.join(sorted(missing))}. "
            f"Available: {', '.join(sorted(pushers))}"
        )
    return {name: pushers[name]() for name in suite_names}


__all__ = [
    "AUDIT_EVAL_SUITE",
    "CHAT_EVAL_SUITE",
    "DOCUMENT_EVAL_SUITE",
    "FIX_EVAL_SUITE",
    "GO_QUALITY_SKILL_EVAL_SUITE",
    "MAP_EVAL_SUITE",
    "ORCHESTRATOR_EVAL_SUITE",
    "PYTHON_QUALITY_SKILL_EVAL_SUITE",
    "ROUTER_EVAL_SUITE",
    "RULE_INJECTOR_EVAL_SUITE",
    "SECURITY_SKILL_EVAL_SUITE",
    "SENTRY_EVAL_SUITE",
    "TRIAGE_EVAL_SUITE",
    "TYPESCRIPT_QUALITY_SKILL_EVAL_SUITE",
    "VALIDATE_EVAL_SUITE",
    "WORKFLOW_AUTOPILOT_EVAL_SUITE",
    "WORKFLOW_FEATURE_IMPLEMENTATION_EVAL_SUITE",
    "WORKFLOW_PACKAGE_AUDIT_EVAL_SUITE",
    "build_suite_registry",
    "push_hosted_datasets",
    "run_audit_eval",
    "run_chat_eval",
    "run_document_eval",
    "run_fix_eval",
    "run_go_quality_skill_eval",
    "run_map_eval",
    "run_orchestrator_eval",
    "run_python_quality_skill_eval",
    "run_router_eval",
    "run_rule_injector_eval",
    "run_security_skill_eval",
    "run_sentry_eval",
    "run_triage_eval",
    "run_typescript_quality_skill_eval",
    "run_validate_eval",
    "run_workflow_autopilot_eval",
    "run_workflow_feature_implementation_eval",
    "run_workflow_package_audit_eval",
]
