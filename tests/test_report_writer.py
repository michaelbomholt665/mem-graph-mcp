#!/usr/bin/env python3
# tests/test_report_writer.py
"""
tests/test_report_writer.py
"""
import os
from mem_graph.models.audit import AuditReport, AuditStats, AuditFinding, FileAuditResult, FindingCategory, Severity
from mem_graph.services.report_writer import render_markdown, write_report

def _mock_report() -> AuditReport:
    stats = AuditStats(
        total_files_analysed=1, total_files_skipped=0, total_findings=1,
        by_severity={"major": 1}, by_category={"bug": 1}, blocker_count=0, critical_count=0
    )
    finding = AuditFinding(
        rule_id="test-rule", category=FindingCategory.BUG, severity=Severity.MAJOR,
        file_path="src/main.py", line_start=1, line_end=2, description="test desc", suggested_fix="fix", code_snippet=None
    )
    result = FileAuditResult(file_path="src/main.py", findings=[finding])
    return AuditReport(
        package_path=".", summary="Test summary narrative.", file_results=[result], stats=stats, rules_applied=["test-rule"]
    )

def test_render_markdown_has_expected_sections():
    report = _mock_report()
    md = render_markdown(report)
    assert "# Audit Report" in md
    assert "Test summary narrative." in md
    assert "Major" in md
    assert "test-rule" in md
    assert "test desc" in md
    assert "src/main.py" in md

def test_render_markdown_buckets_recurring_findings():
    report = _mock_report()
    finding = report.file_results[0].findings[0]
    finding.fingerprint = "deadbeefdeadbeef"

    md = render_markdown(report, recurrence_fingerprints={"deadbeefdeadbeef"})

    assert "🔄 Recurring" in md
    assert "🆕 New" not in md

def test_write_report(tmp_path):
    report = _mock_report()
    out_path = os.path.join(tmp_path, "report.md")
    write_report(report, out_path)
    assert os.path.exists(out_path)
    with open(out_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "# Audit Report" in content
    assert "Test summary narrative." in content
