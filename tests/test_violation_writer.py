#!/usr/bin/env python3
# tests/test_violation_writer.py
"""
tests/test_violation_writer.py
"""
import pytest
from mem_graph.models.audit import AuditReport, AuditStats, AuditFinding, FileAuditResult, FindingCategory, Severity
from mem_graph.services.violation_writer import write_violations
from mem_graph.tools.work.projects import project_create
from mem_graph.tools.work.violations import violation_list

def _mock_report(rule_id: str, path: str) -> AuditReport:
    stats = AuditStats(
        total_files_analysed=1, total_files_skipped=0, total_findings=1,
        by_severity={"major": 1}, by_category={"bug": 1}, blocker_count=0, critical_count=0
    )
    finding = AuditFinding(
        rule_id=rule_id, category=FindingCategory.BUG, severity=Severity.MAJOR,
        file_path=path, line_start=10, line_end=12, description="test", suggested_fix="fix", code_snippet=None
    )
    result = FileAuditResult(file_path=path, findings=[finding])
    return AuditReport(
        package_path="/tmp", summary="Test", file_results=[result], stats=stats, rules_applied=[rule_id]
    )


@pytest.mark.asyncio
async def test_write_violations_creates_new(db):
    proj = await project_create(name="Proj", description="Desc")
    pid = proj["project_id"]

    report = _mock_report("rule1", "main.py")
    res = write_violations(report, pid)
    
    assert res.total == 1
    assert res.created == 1
    assert res.recurrences == 0

    vs = await violation_list(project_id=pid)
    assert len(vs["violations"]) == 1
    v = vs["violations"][0]
    assert v["rule"] == "rule1"
    assert v["file_path"] == "main.py"


@pytest.mark.asyncio
async def test_write_violations_deduplicates(db):
    proj = await project_create(name="Proj", description="Desc")
    pid = proj["project_id"]

    report = _mock_report("rule1", "main.py")
    write_violations(report, pid)
    
    # Run again, identical finding -> recurrence
    res2 = write_violations(report, pid)
    assert res2.total == 1
    assert res2.created == 0
    assert res2.recurrences == 1
    
    vs = await violation_list(project_id=pid, status="recurrence")
    assert len(vs["violations"]) == 1
