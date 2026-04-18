"""Maintainability and code-smell audit rules."""

from __future__ import annotations

from ....models.audit import AuditRule, FindingCategory, Severity

MAINTAINABILITY_RULES: list[AuditRule] = [
    AuditRule(
        rule_id="impl:missing-error-context",
        category=FindingCategory.BUG,
        severity=Severity.MINOR,
        description=(
            "Errors returned without wrapping or context. Raw sentinel errors or "
            "bare `return err` that lose the call site context needed for debugging. "
            "Should use fmt.Errorf with %w or a structured error type."
        ),
        examples=["if err != nil { return err }  // no context added"],
    ),
]
