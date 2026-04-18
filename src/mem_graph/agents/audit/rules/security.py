"""Security audit rules."""

from __future__ import annotations

from ....models.audit import AuditRule, FindingCategory, Severity

SECURITY_RULES: list[AuditRule] = [
    AuditRule(
        rule_id="security:hardcoded-secret",
        category=FindingCategory.SECURITY,
        severity=Severity.BLOCKER,
        description=(
            "Hardcoded credentials, API keys, tokens, passwords, or private keys "
            "in source code. Includes string literals assigned to variables named "
            "password, secret, key, token, apikey, or matching common secret patterns."
        ),
        examples=['password := "hunter2"', 'const APIKey = "sk-..."'],
    ),
    AuditRule(
        rule_id="security:sql-injection",
        category=FindingCategory.SECURITY,
        severity=Severity.BLOCKER,
        description=(
            "String concatenation or fmt.Sprintf used to build SQL query strings "
            "with user-controlled input. Parameterised queries must be used instead."
        ),
        examples=['query := "SELECT * FROM users WHERE id = " + userID'],
    ),
    AuditRule(
        rule_id="security:unsafe-deserialization",
        category=FindingCategory.SECURITY,
        severity=Severity.CRITICAL,
        description=(
            "Deserialisation of untrusted input into interface{} or any without "
            "schema validation. Includes gob.Decode, json.Unmarshal into interface{}, "
            "yaml.Unmarshal without struct target."
        ),
        examples=["json.Unmarshal(userInput, &interface{}{})"],
    ),
]
