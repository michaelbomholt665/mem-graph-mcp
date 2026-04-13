"""
Lightweight confirmation helper for FastMCP tools.

Provides `require_confirmation` which attempts to use `ctx.request_input()` when
available (FastMCP); otherwise it safely declines destructive operations to
avoid accidental data loss in non-interactive environments.

This module is intentionally small and pluggable so it can be swapped with a
more feature-rich implementation once `docs/planning/tasks/007-fastmcp-task.md`
is completed.
"""
from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import List, Optional, Any


@dataclass
class ConfirmationResponse:
    approved: bool
    reason: Optional[str] = None
    alternative_choice: Optional[str] = None


async def require_confirmation(
    ctx: Any,
    action: str,
    description: str,
    files_affected: List[str] | None = None,
    risk_level: str = "medium",
    alternatives: List[str] | None = None,
) -> ConfirmationResponse:
    """Request a user confirmation for a potentially destructive action.

    If `ctx.request_input` exists we call it and respect the user's choice.
    If not available (non-interactive environment) we return declined to
    avoid accidental destructive changes.

    Args:
        ctx: FastMCP Context (or any object exposing `request_input`).
        action: short action code (e.g., 'delete', 'apply_refactor').
        description: user-facing description of what will happen.
        files_affected: optional list of file paths affected.
        risk_level: low|medium|high|critical
        alternatives: optional alternatives to present.

    Returns:
        ConfirmationResponse with approved=True if user approved.
    """

    # Best-effort: if ctx has request_input, use it.
    request_fn = getattr(ctx, "request_input", None)

    prompt = _build_prompt(description, files_affected, risk_level)
    options = _build_options(alternatives)

    if not callable(request_fn):
        # Non-interactive environment: decline destructive actions.
        return ConfirmationResponse(approved=False, reason="non_interactive")

    return await _call_request_fn(request_fn, prompt, options)


def _build_prompt(description: str, files_affected: List[str] | None, risk_level: str) -> str:
    """Build the confirmation prompt."""
    prompt = f"{risk_level.upper()}: {description}"
    if files_affected:
        prompt += f"\nFiles affected: {len(files_affected)}"
    return prompt


def _build_options(alternatives: List[str] | None) -> List[str]:
    """Build the list of options."""
    options = ["approve", "decline"]
    if alternatives:
        options.extend(alternatives)
    return options


async def _call_request_fn(
    request_fn: Any, prompt: str, options: List[str]
) -> ConfirmationResponse:
    """Call the request function and normalize the response."""
    try:
        # FastMCP's ctx.request_input is async and returns the chosen option.
        # Some clients return dicts or structured answers; normalize to string.
        if inspect.iscoroutinefunction(request_fn):
            resp = await request_fn(prompt=prompt, options=options)
        else:
            resp = request_fn(prompt=prompt, options=options)

        return _normalize_response(resp)

    except Exception as e:
        return ConfirmationResponse(approved=False, reason=f"request_failed:{e}")


def _normalize_response(resp: Any) -> ConfirmationResponse:
    """Normalize the response from request_fn."""
    # Normalize response to string
    if isinstance(resp, dict):
        choice = resp.get("choice") or resp.get("value") or next(iter(resp.values()), None)
    else:
        choice = resp

    if choice is None:
        return ConfirmationResponse(approved=False, reason="no_response")

    choice = str(choice).lower()
    if choice == "approve":
        return ConfirmationResponse(approved=True)
    if choice in ("decline", "no", "cancel"):
        return ConfirmationResponse(approved=False, reason="user_declined")
    # Any other option selected is treated as an alternative choice
    return ConfirmationResponse(approved=False, alternative_choice=choice)
