# Design: Phase 3 - Interactivity (User Elicitation)

**Status:** Design Phase  
**Priority:** Medium (Safety feature)  
**Date:** 2026-04-13

---

## Overview

Phase 3 adds interactive confirmations for destructive operations. Instead of silently executing deletion or major refactoring, agents ask the user for explicit approval via FastMCP's `ctx.request_input()` API.

This design ensures:
1. **Deletion Confirmations:** Users approve before code is deleted
2. **Critical Decision Review:** Users review high-risk decisions
3. **Graceful Degradation:** If user declines, agent proposes alternatives

---

## Goals

1. **Prevent Accidental Damage:** Require confirmation for destructive ops
2. **Maintain User Agency:** Users stay involved in important decisions
3. **Support Async UX:** Request-response model works with MCP clients
4. **Audit Trail:** Confirmations are tracked in graph

---

## Scope

### In Scope
- Add `ctx.request_input()` to memory management tools (deletion)
- Add confirmations to audit agent (critical findings)
- Add confirmations to fix agent (major refactors)
- Extend FastMCP server with confirmation handlers
- Track confirmations in graph for audit

### Out of Scope
- Changing agent logic (confirmations wrap tools)
- Custom UI (use FastMCP's native confirmation dialogs)
- Blocking vs. non-blocking modes (always async)

---

## Architecture

### 1. Confirmation Wrapper for Tools

Create wrapper functions that confirm before executing:

```python
# src/mem_graph/tools/confirmations.py

from fastmcp.server.context import Context
from pydantic import BaseModel

class ConfirmationRequest(BaseModel):
    """A confirmation request sent to the client."""
    action: str  # "delete", "refactor", "override"
    description: str  # What will happen
    files_affected: list[str]  # Paths being changed
    risk_level: str  # "low", "medium", "high", "critical"
    alternatives: list[str]  # If user declines, what instead?

class ConfirmationResponse(BaseModel):
    """User's response to confirmation."""
    approved: bool
    reason: str | None  # Why they declined
    alternative_choice: str | None  # Which alternative they chose

async def require_confirmation(
    ctx: Context,
    action: str,
    description: str,
    files_affected: list[str],
    risk_level: str = "medium",
    alternatives: list[str] | None = None,
) -> ConfirmationResponse:
    """
    Request user confirmation for a destructive action.
    
    Blocks until user responds via MCP client.
    """
    
    request = ConfirmationRequest(
        action=action,
        description=description,
        files_affected=files_affected,
        risk_level=risk_level,
        alternatives=alternatives or [],
    )
    
    # Send confirmation request to client
    # Client displays dialog and returns user's choice
    response = await ctx.request_input(
        prompt=f"{risk_level.upper()}: {description}",
        options=["approve", "decline"],
    )
    
    # Map response to ConfirmationResponse
    return ConfirmationResponse(
        approved=response == "approve",
        reason="User declined" if response != "approve" else None,
    )
```

### 2. Deletion Confirmations (Memory Manage Tool)

```python
# src/mem_graph/tools/memory/memory.py

from ..confirmations import require_confirmation

@mcp.tool()
async def memory_manage(
    ctx: Context,
    action: str,  # "delete", "merge", "archive"
    target_ids: list[str],
    recursive: bool = False,
) -> dict:
    """
    Manage memory nodes (delete, merge, archive).
    
    For destructive operations, user must confirm.
    """
    
    if action == "delete":
        # Require confirmation for deletion
        confirmation = await require_confirmation(
            ctx=ctx,
            action="delete",
            description=f"Delete {len(target_ids)} memory facts permanently?",
            files_affected=target_ids,
            risk_level="high",
            alternatives=[
                "Archive instead (keeps for reference)",
                "Mark as deprecated (visible but unused)",
            ],
        )
        
        if not confirmation.approved:
            return {
                "status": "cancelled",
                "reason": confirmation.reason,
                "suggestion": "Consider archiving instead of deleting",
            }
        
        # User approved—execute deletion
        for fact_id in target_ids:
            await graph.delete_fact(fact_id)
        
        return {
            "status": "success",
            "deleted": len(target_ids),
            "timestamp": datetime.now().isoformat(),
        }
    
    elif action == "merge":
        # Merging is lower risk
        logger.info(f"Merging {len(target_ids)} facts")
        merged_id = await graph.merge_facts(target_ids)
        return {"status": "success", "merged_into": merged_id}
    
    elif action == "archive":
        # Archiving is safe
        logger.info(f"Archiving {len(target_ids)} facts")
        for fact_id in target_ids:
            await graph.archive_fact(fact_id)
        return {"status": "success", "archived": len(target_ids)}
```

### 3. Critical Decision Confirmations (Audit Agent)

```python
# src/mem_graph/tools/agents/audit.py

@mcp.tool()
async def audit_package(
    ctx: Context,
    package_path: str,
    severity: str = "all",  # "critical", "high", "all"
) -> dict:
    """
    Audit a package for code smells and issues.
    
    For critical findings, user reviews before proposing fixes.
    """
    
    # Run audit
    findings = await run_audit_agent(package_path, severity)
    
    # Separate critical findings
    critical = [f for f in findings if f["severity"] == "critical"]
    
    if critical:
        # Require review of critical findings
        confirmation = await require_confirmation(
            ctx=ctx,
            action="review_critical_findings",
            description=f"Found {len(critical)} critical issues in {package_path}. Review them?",
            files_affected=[f["file"] for f in critical],
            risk_level="critical",
            alternatives=[
                "Ignore critical for now",
                "Defer to next sprint",
            ],
        )
        
        if not confirmation.approved:
            # User declined review—return findings but don't propose fixes
            return {
                "status": "review_declined",
                "findings": [f for f in findings if f["severity"] != "critical"],
                "critical_deferred": len(critical),
            }
    
    # User approved—continue with full audit
    return {
        "status": "complete",
        "total_findings": len(findings),
        "critical": len(critical),
        "findings": findings,
    }
```

### 4. Major Refactor Confirmations (Fix Agent)

```python
# src/mem_graph/tools/agents/orchestrator.py

@mcp.tool()
async def orchestrate_codebase(
    ctx: Context,
    package_path: str,
    operation: str,  # "refactor", "optimize", "modernize"
    dry_run: bool = False,
) -> dict:
    """
    Run orchestrator on a package.
    
    For major refactors, user reviews changes before applying.
    """
    
    # If dry_run, don't require confirmation (just show diff)
    if dry_run:
        result = await run_orchestrator(package_path, operation, dry_run=True)
        return {
            "status": "dry_run",
            "changes_preview": result["patches"],
            "total_files": len(result["patches"]),
        }
    
    # For actual runs, preview changes and get confirmation
    preview = await run_orchestrator(package_path, operation, dry_run=True)
    
    if len(preview["patches"]) > 10:
        # Large refactor—require approval
        confirmation = await require_confirmation(
            ctx=ctx,
            action="apply_refactor",
            description=f"Apply {operation} to {len(preview['patches'])} files?",
            files_affected=list(preview["patches"].keys()),
            risk_level="high",
            alternatives=[
                "Show diff and decide",
                "Cancel refactor",
            ],
        )
        
        if not confirmation.approved:
            return {
                "status": "cancelled",
                "reason": confirmation.reason,
                "diff_available": True,
            }
    
    # User approved—run actual orchestrator
    result = await run_orchestrator(package_path, operation, dry_run=False)
    return {
        "status": "complete",
        "patched_files": len(result["patches"]),
        "summary": result["summary"],
    }
```

### 5. Tracking Confirmations in Graph

Store confirmation history for auditing:

```python
# Cypher schema extension

CREATE (:ConfirmationRecord {
  id: "...",
  action: "delete",
  target_ids: ["fact-1", "fact-2"],
  user_id: "...",
  approved: true,
  timestamp: datetime(),
  reason: "User approved deletion",
  reverted: false,  # Was decision later reversed?
})

(confirmation:ConfirmationRecord)-[:ON]->(fact:Fact)
(confirmation:ConfirmationRecord)-[:IN_SESSION]->(session:Session)
```

### 6. FastMCP Server Confirmation Handler

Update the server to handle confirmation requests:

```python
# src/mem_graph/server.py

from fastmcp.server.context import Context

class ConfirmationMiddleware(Middleware):
    """Middleware to handle confirmation requests."""
    
    async def __call__(self, context: MiddlewareContext, call_next: CallNext):
        # Wrap tool execution to catch confirmation requests
        try:
            return await call_next()
        except ConfirmationRequired as e:
            # Send confirmation request to client
            # Client responds with approval/decline
            response = await context.request_input(
                prompt=str(e),
                options=e.options,
            )
            
            # Store in graph
            await store_confirmation(context, response)
            
            # Return result based on user's choice
            return response

mcp = FastMCP(name="memory")
mcp.use_middleware(ConfirmationMiddleware)
```

---

## Benefits

1. **Safety:** Prevents accidental deletion or major changes
2. **User Control:** Users stay informed and involved
3. **Audit Trail:** All confirmations are tracked
4. **Graceful Alternatives:** User can choose safer options
5. **Non-Blocking:** Async request-response works with all MCP clients

---

## When to Require Confirmation

| Operation | Risk Level | Confirm? | Rationale |
|-----------|-----------|----------|-----------|
| Delete fact | High | YES | Can't undo easily |
| Archive fact | Low | NO | Reversible |
| Merge facts | Low | NO | Reversible |
| Critical audit findings | Critical | YES | User should review |
| Large refactor (10+ files) | High | YES | Major change |
| Small style fix (1-2 files) | Low | NO | Low risk |
| Override decision | High | YES | Shouldn't bypass approval |

---

## Implementation Checklist

- [ ] Create `confirmations.py` with confirmation wrapper
- [ ] Add confirmation to `memory_manage` tool (delete)
- [ ] Add confirmation to `audit_package` tool
- [ ] Add confirmation to `orchestrate_codebase` tool
- [ ] Create `ConfirmationMiddleware` for FastMCP server
- [ ] Extend graph schema for confirmation records
- [ ] Test confirmation dialog in MCP inspector
- [ ] Test confirmation with actual MCP client
- [ ] Add confirmation tracking to audit log

---

## Success Criteria

1. Destructive operations require user confirmation
2. Confirmations appear in MCP client UI
3. User can approve/decline/choose alternative
4. All confirmations are tracked in graph
5. No regression in agent functionality

---

## Dependencies

- FastMCP 3.0+ with `ctx.request_input()`
- Graph client (already exists)
- MCP clients that support confirmation dialogs

---

## Notes

- `ctx.request_input()` is async—agent blocks until user responds
- Timeouts should be implemented per MCP spec (typically 30s)
- If user doesn't respond, operation times out (fails safely)
- Confirmations are opaque to agents—they get approved/declined and continue
