"""Bugs and correctness audit rules."""

from __future__ import annotations

from ....models.audit import AuditRule, FindingCategory, Severity

CORRECTNESS_RULES: list[AuditRule] = [
    AuditRule(
        rule_id="impl:stub-in-production",
        category=FindingCategory.MISSING_IMPLEMENTATION,
        severity=Severity.MAJOR,
        description=(
            "Functions or methods that return zero values, empty structs, or nil "
            "without performing real work — stub implementations that were never "
            "completed. Includes panic('not implemented'), empty interface implementations."
        ),
        examples=["func (r *Repo) Save(x X) error { return nil }  // no actual write"],
    ),
    AuditRule(
        rule_id="impl:panic-in-library",
        category=FindingCategory.BUG,
        severity=Severity.CRITICAL,
        description=(
            "panic() calls in library or service code outside of main() and init(). "
            "Panics in non-main packages crash the entire process and cannot be "
            "handled by callers. Return errors instead."
        ),
        examples=["panic(fmt.Sprintf('unexpected state: %v', s))"],
    ),
]
