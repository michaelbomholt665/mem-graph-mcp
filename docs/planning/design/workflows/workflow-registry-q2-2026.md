# Workflow Registry — Q2 2026

**Status:** Active  
**Created:** 2026-04-20  
**Owner:** Task 030 (Workflow Infrastructure)

## Overview

This document lists all registered workflows in the mem_graph `WorkflowRegistry`,
their agent rosters, reasoning modes, profile sizes, and lifecycle phase mapping.

The registry is the single source of truth for workflow metadata — dashboard,
selector, and runtime code all read from here.

---

## Built-in Workflows (3)

| Key | Display Name | Profile | Reasoning Mode | Risk | Source Module |
|-----|-------------|---------|----------------|------|---------------|
| `autopilot_graph` | Autopilot Remediation Graph | LARGE | REACT_CHALLENGE | high | `orchestrator_runtime` |
| `managed_workflow_graph` | Managed Sub-Agent Workflow | LARGE | REACT_CHALLENGE | medium | `managed_workflow_runtime` |
| `package_audit` | Iterative Package Audit | LARGE | REACT_CHALLENGE | low | `package_audit_runtime` |

### autopilot_graph

Six-node recursive fix pipeline: `ContextGather → Sentry → LogicDraft → StyleDraft → Guard → MemorySync`.
Used for violation-driven remediation with guard-based retry.

**Agents:** mapper, sentry, fixer, scribe  
**Entry-point:** `autopilot_graph_run_with_selection()`

### managed_workflow_graph

Nine-node general-purpose sub-agent workflow: `ContextGather → PlanWorkflow → Implementation → Audit → DebugOrValidation → Documentation → ContextMapUpdate → MemoryBankSync → FinalReport`.

**Agents:** fixer, auditor, scribe, mapper  
**Entry-point:** `run_managed_workflow_with_selection()`

### package_audit

Five-node FSM audit pipeline: `DiscoverNode → ChunkNode → AnalyzeNode → AggregateNode → End`.
Processes packages file-by-file in chunks of 4-5.

**Agents:** auditor  
**Entry-point:** `run_package_audit(deps)`

---

## Group A Workflows (24)

### Priority 1

| Key | Display Name | Profile | Reasoning Mode | Risk | Agents |
|-----|-------------|---------|----------------|------|--------|
| `feature_implementation` | Feature Implementation | LARGE | REACT_CHALLENGE | high | mapper, sentry, fixer, auditor, scribe |

**Lifecycle phases:** Feature Build (Phase 2), Integration (Phase 5)  
**Stages:** context_gather → sentry → implementation → audit → documentation → memory_sync

---

### Priority 2

| Key | Display Name | Profile | Reasoning Mode | Risk | Agents |
|-----|-------------|---------|----------------|------|--------|
| `refactor` | Refactor | LARGE | REACT_CHALLENGE | medium | mapper, fixer, auditor, scribe |

**Lifecycle phases:** Refactoring (Phase 4)  
**Stages:** context_gather → implementation → audit → documentation → memory_sync

---

### Priority 3

| Key | Display Name | Profile | Reasoning Mode | Risk | Agents |
|-----|-------------|---------|----------------|------|--------|
| `research` | Research | MEDIUM | BOUNDED_TOT | low | auditor, scribe |

**Lifecycle phases:** Cross-cutting — usable from any phase.  
**Stages:** context_gather → exploration → synthesis

---

### Priority 4

| Key | Display Name | Profile | Reasoning Mode | Risk | Agents |
|-----|-------------|---------|----------------|------|--------|
| `security_hardening` | Security Hardening | LARGE | BOUNDED_TOT | high | auditor, fixer, scribe |

**Lifecycle phases:** Hardening (Phase 7)  
**Stages:** threat_model → mitigation → validation → documentation

---

### Priority 5

| Key | Display Name | Profile | Reasoning Mode | Risk | Agents |
|-----|-------------|---------|----------------|------|--------|
| `performance_profiling` | Performance Profiling | MEDIUM | BOUNDED_TOT | medium | auditor, fixer, scribe |

**Lifecycle phases:** Optimization (Phase 6)  
**Stages:** profiling → optimization → verification → documentation

---

### Priority 6 — Design & Authoring

| Key | Display Name | Profile | Reasoning Mode | Risk | Agents |
|-----|-------------|---------|----------------|------|--------|
| `adr_authoring` | ADR Authoring | SMALL | REACT_CHALLENGE | low | scribe |
| `feature_design` | Feature Design | MEDIUM | REACT_CHALLENGE | low | auditor, scribe |
| `schema_design` | Schema Design | MEDIUM | BOUNDED_TOT | low | auditor, scribe |
| `api_contract_design` | API Contract Design | MEDIUM | REACT_CHALLENGE | low | auditor, scribe |
| `design_docs` | Design Documentation | SMALL | REACT_CHALLENGE | low | scribe |
| `runbook_authoring` | Runbook Authoring | SMALL | REACT_CHALLENGE | low | scribe |
| `disaster_recovery` | Disaster Recovery Planning | MEDIUM | BOUNDED_TOT | high | auditor, scribe |
| `command_design` | Command Design | SMALL | REACT_CHALLENGE | low | scribe, fixer |
| `error_logging_design` | Error & Logging Design | SMALL | REACT_CHALLENGE | low | auditor, scribe |

**Lifecycle phases:** Design & Planning (Phase 1)

---

### Priority 7

| Key | Display Name | Profile | Reasoning Mode | Risk | Agents |
|-----|-------------|---------|----------------|------|--------|
| `dependency_audit` | Dependency Audit | MEDIUM | REACT_CHALLENGE | medium | auditor, scribe |
| `ci_setup` | CI Setup | MEDIUM | REACT_CHALLENGE | medium | auditor, fixer |

**Lifecycle phases:** Infrastructure (Phase 3)

---

### Priority 8

| Key | Display Name | Profile | Reasoning Mode | Risk | Agents |
|-----|-------------|---------|----------------|------|--------|
| `docs_generation` | Documentation Generation | MEDIUM | REACT_CHALLENGE | low | scribe |
| `changelog_authoring` | Changelog Authoring | SMALL | REACT_CHALLENGE | low | scribe |
| `onboarding_docs` | Onboarding Documentation | MEDIUM | REACT_CHALLENGE | low | scribe |

**Lifecycle phases:** Documentation (Phase 8)

---

### Priority 9

| Key | Display Name | Profile | Reasoning Mode | Risk | Agents |
|-----|-------------|---------|----------------|------|--------|
| `release_preparation` | Release Preparation | MEDIUM | REACT_CHALLENGE | high | auditor, scribe |
| `deployment_validation` | Deployment Validation | MEDIUM | REACT_CHALLENGE | high | auditor |

**Lifecycle phases:** Release & Deploy (Phase 9)

---

### Priority 10

| Key | Display Name | Profile | Reasoning Mode | Risk | Agents |
|-----|-------------|---------|----------------|------|--------|
| `utility_extraction` | Utility Extraction | MEDIUM | REACT_CHALLENGE | medium | mapper, fixer, auditor |

**Lifecycle phases:** Refactoring (Phase 4), Integration (Phase 5)

---

### Priority 11

| Key | Display Name | Profile | Reasoning Mode | Risk | Agents |
|-----|-------------|---------|----------------|------|--------|
| `implementation_planning` | Implementation Planning | MEDIUM | REACT_2 | low | router, scribe |
| `project_scaffold` | Project Scaffold | MEDIUM | REACT_CHALLENGE | low | fixer, scribe |

**Lifecycle phases:** Planning (Phase 0), Project Bootstrap (Phase 0)

---

## Group B Workflows (Blocked)

The following workflows are defined in the registry plan but not yet registered.
They are blocked on agent completion.

| Key | Blocker |
|-----|---------|
| `idea_capture` | chat_agent incomplete |
| `requirements_elicitation` | chat_agent incomplete |
| `architecture_design` | diagram_agent incomplete |
| `codebase_migration` | Not yet in Group A |
| `code_skeptic` | Not yet in Group A |

---

## Reasoning Modes

| Mode | Enum Value | Use Case |
|------|-----------|----------|
| REACT_CHALLENGE | `react_challenge` | Default — plan → draft → challenge → decide |
| REACT_2 | `react_2` | Iteration on prior output — confirm / improve / drop |
| BOUNDED_TOT | `bounded_tot` | Architectural decisions, threat modelling (≤3 branches) |
| COT | `cot` | Multi-step chain reasoning, N candidates per step |

---

## Profile Sizes

| Size | Max Stages | Fan-out | Retry Cycles | Checkpoint Freq |
|------|-----------|---------|--------------|-----------------|
| SMALL | 3 | 1 | 0 | 0 |
| MEDIUM | 6 | 3 | 1 | 0 |
| LARGE | 10 | 6 | 3 | 3 |

---

## Notes

- Task 027 Phase 8 (workflow start) depends on this registry and selector being complete.
- Group B workflows unblock as `chat_agent` and `diagram_agent` complete.
- Workflow complexity scores should be validated empirically after the first 5 workflows
  run in production.
- `implementation_planning` uses `REACT_2` because it often iterates on a prior plan.
