"""Go-specific audit rules."""

from __future__ import annotations

from ....models.audit import AuditRule, FindingCategory, Severity

GO_RULES: list[AuditRule] = [
    AuditRule(
        rule_id="go:ignored-error",
        category=FindingCategory.SILENT_ERROR,
        severity=Severity.MAJOR,
        description=(
            "Error return values assigned to blank identifier `_` or not checked at all. "
            "Includes ignored os.File.Close(), sql.Rows.Close(), io.Writer.Write(), "
            "and any function returning (T, error) where the error is discarded."
        ),
        examples=["f, _ := os.Open(path)", "rows.Close()  // return value dropped"],
    ),
    AuditRule(
        rule_id="go:context-not-propagated",
        category=FindingCategory.LEAK,
        severity=Severity.MAJOR,
        description=(
            "Functions accepting context.Context that do not pass it to downstream "
            "calls (DB queries, HTTP requests, goroutines). Results in ungraceful "
            "shutdown and leaked goroutines on cancellation."
        ),
        examples=["db.Query(sql) instead of db.QueryContext(ctx, sql)"],
    ),
    AuditRule(
        rule_id="go:goroutine-leak",
        category=FindingCategory.LEAK,
        severity=Severity.CRITICAL,
        description=(
            "Goroutines launched with `go func()` that have no guaranteed termination "
            "path — missing done channel, WaitGroup, or context cancellation handling. "
            "Also covers goroutines blocked on unbuffered channels with no sender."
        ),
        examples=["go func() { for { work() } }()  // no exit condition"],
    ),
    AuditRule(
        rule_id="go:deferred-in-loop",
        category=FindingCategory.LEAK,
        severity=Severity.MAJOR,
        description=(
            "defer statements inside for loops. Deferred calls execute at function "
            "return, not loop iteration end — file handles and locks accumulate until "
            "the enclosing function exits."
        ),
        examples=["for _, f := range files { defer f.Close() }"],
    ),
]
