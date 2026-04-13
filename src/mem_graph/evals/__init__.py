"""Evals registry and exports for the mem-graph agent suites."""

from __future__ import annotations

from ..models.evals import EvalMode, SuiteBinding
from .audit_evals import AUDIT_EVAL_SUITE, build_audit_binding
from .fix_evals import FIX_EVAL_SUITE, build_fix_binding
from .validate_evals import VALIDATE_EVAL_SUITE, build_validate_binding


def build_suite_registry(mode: EvalMode = "fixture") -> dict[str, SuiteBinding]:
    return {
        "audit": build_audit_binding(mode),
        "fix": build_fix_binding(mode),
        "validate": build_validate_binding(mode),
    }


__all__ = [
    "AUDIT_EVAL_SUITE",
    "FIX_EVAL_SUITE",
    "VALIDATE_EVAL_SUITE",
    "build_suite_registry",
]