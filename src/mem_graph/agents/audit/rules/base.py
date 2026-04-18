"""Base audit rules shared across languages."""

from __future__ import annotations

from ....models.audit import AuditRule, FindingCategory, Severity

BASE_RULES: list[AuditRule] = [
    AuditRule(
        rule_id="CWE-252",
        category=FindingCategory.BUG,
        severity=Severity.MAJOR,
        description=(
            "Unchecked return values from functions that signal failure via return "
            "value rather than panic. Includes fmt.Fprintf, json.Marshal, "
            "strconv.Atoi used without error check."
        ),
        examples=["json.Marshal(v)  // return value and error both discarded"],
    ),
    AuditRule(
        rule_id="CWE-400",
        category=FindingCategory.BUG,
        severity=Severity.MAJOR,
        description=(
            "Uncontrolled resource consumption — unbounded loops reading from "
            "external input, slices grown without capacity hints in hot paths, "
            "recursive functions without depth limits."
        ),
        examples=["for { data = append(data, readChunk()) }  // no size cap"],
    ),
]
