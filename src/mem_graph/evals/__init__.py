"""Evals registry and exports for the mem-graph agent suites."""

from __future__ import annotations

from ..models.evals import EvalMode, SuiteBinding
from .audit_evals import (
    AUDIT_EVAL_SUITE,
    build_audit_binding,
    push_audit_dataset,
    run_audit_eval,
)
from .document_evals import DOCUMENT_EVAL_SUITE, build_document_binding
from .document_evals import push_document_dataset, run_document_eval
from .fix_evals import FIX_EVAL_SUITE, build_fix_binding
from .fix_evals import push_fix_dataset, run_fix_eval
from .map_evals import MAP_EVAL_SUITE, build_map_binding, push_map_dataset, run_map_eval
from .validate_evals import VALIDATE_EVAL_SUITE, build_validate_binding
from .validate_evals import push_validate_dataset, run_validate_eval


def build_suite_registry(mode: EvalMode = "fixture") -> dict[str, SuiteBinding]:
    return {
        "audit": build_audit_binding(mode),
        "document": build_document_binding(mode),
        "fix": build_fix_binding(mode),
        "map": build_map_binding(mode),
        "validate": build_validate_binding(mode),
    }


def push_hosted_datasets(selected_suites: list[str] | None = None) -> dict[str, object]:
    pushers = {
        "audit": push_audit_dataset,
        "document": push_document_dataset,
        "fix": push_fix_dataset,
        "map": push_map_dataset,
        "validate": push_validate_dataset,
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
    "DOCUMENT_EVAL_SUITE",
    "FIX_EVAL_SUITE",
    "MAP_EVAL_SUITE",
    "VALIDATE_EVAL_SUITE",
    "build_suite_registry",
    "push_hosted_datasets",
    "run_audit_eval",
    "run_document_eval",
    "run_fix_eval",
    "run_map_eval",
    "run_validate_eval",
]
