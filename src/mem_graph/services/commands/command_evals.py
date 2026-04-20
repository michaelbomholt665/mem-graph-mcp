"""Eval gate helpers for curated CLI commands."""

from __future__ import annotations

from typing import Any, Sequence

from ...db import db_get_connection
from ...evals.evaluator import (
    Evaluator,
    render_eval_report,
    run_named_eval_gate,
    write_json_report,
)
from .base import ok


async def eval_gate(
    gate: str,
    *,
    suites: Sequence[str] | None = None,
    suite_pass_threshold: float | None = None,
    runs_override: int | None = None,
    project_id: str | None = None,
    output_path: str | None = None,
) -> dict[str, Any]:
    """Run one of the maintained eval gates and optionally persist the summary."""
    report = await run_named_eval_gate(
        gate,
        selected_suites=suites,
        suite_pass_threshold=suite_pass_threshold,
        runs_override=runs_override,
    )
    summary = render_eval_report(report)
    written_path = write_json_report(report, output_path) if output_path else None
    eval_run_id: str | None = None
    if project_id:
        conn = db_get_connection()
        eval_run_id = Evaluator().persist_report_summary(
            report,
            conn=conn,
            project_id=project_id,
            trigger=f"command:{gate}",
            report_path=written_path,
            label=f"eval-gate:{gate}",
        )
    return ok(
        "eval gate",
        {
            "gate": gate,
            "summary": summary,
            "report": report.model_dump(mode="json"),
            "output_path": written_path,
            "eval_run_id": eval_run_id,
        },
    )
