"""Python-specific audit rules."""

from __future__ import annotations

from ....models.audit import AuditRule, FindingCategory, Severity

PYTHON_RULES: list[AuditRule] = [
    AuditRule(
        rule_id="python:bare-except",
        category=FindingCategory.SILENT_ERROR,
        severity=Severity.MAJOR,
        description=(
            "Bare except blocks or broad Exception handlers that swallow errors "
            "without logging, re-raising, or returning structured failure state."
        ),
        examples=["try:\n    work()\nexcept Exception:\n    pass"],
    ),
    AuditRule(
        rule_id="python:mutable-default",
        category=FindingCategory.BUG,
        severity=Severity.MAJOR,
        description=(
            "Mutable default arguments such as list, dict, or set that can leak "
            "state between calls."
        ),
        examples=["def add(item, cache=[]): ..."],
    ),
]
