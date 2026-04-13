# Pydantic Upgrade & FastMCP 3.0 Completion - Design Index

**Date:** April 13, 2026  
**Status:** Design Phase Complete  
**Total Features:** 15 (13 Base + 2 Critical Quality)  

This directory contains comprehensive design documents for implementing the "2026 Pydantic AI God Stack" upgrade and completing FastMCP 3.0.

---

## Quick Navigation

### Pydantic-AI Upgrades (Foundation)
1. [**001-pydantic-ai-slim.md**](001-pydantic-ai-slim.md) — Lightweight dispatcher, provider factory
2. [**002-pydantic-graph.md**](002-pydantic-graph.md) — Type-safe ReAct workflows with resumability
3. [**003-pydantic-deep.md**](003-pydantic-deep.md) — Planning & self-correction for high-stakes operations
4. [**004-pydantic-ai-skills.md**](004-pydantic-ai-skills.md) — Python-native programmatic skills (replaces Markdown)
5. [**005-hindsight.md**](005-hindsight.md) — Persistent memory integration with Ladybug/Kuzu

### FastMCP 3.0 Completion (UI & Operations)
6. [**006-phase3-interactivity.md**](006-phase3-interactivity.md) — User elicitation, destructive operation confirmations
7. [**007-phase4a-icons.md**](007-phase4a-icons.md) — Icons, rich content, progress reporting
8. [**008-phase4b-tasks.md**](008-phase4b-tasks.md) — Background tasks with poll-based progress
9. [**009-phase5a-dashboard.md**](009-phase5a-dashboard.md) — Interactive ForceGraph 3D visualization
10. [**010-phase5b-jira.md**](010-phase5b-jira.md) — Semantic Jira-to-code linking via embeddings
11. [**011-phase5c-files.md**](011-phase5c-files.md) — File explorer with violation markers

### Quality Control & Observability (CRITICAL)
12. [**014-evals.md**](014-evals.md) — Stochastic agent testing, pass rate benchmarks, tier comparison
13. [**015-logfire.md**](015-logfire.md) — Real-time monitoring, flight recorder, anomaly detection

### Polish & Infrastructure
14. [**012-otel.md**](012-otel.md) — OpenTelemetry tracing, metrics, structured logging
15. [**013-versioning.md**](013-versioning.md) — Semantic versioning and website URL

---

## Architecture Overview

### Stack Layers (Bottom → Top)

```
┌─────────────────────────────────────────────────────────────────┐
│  **Presentation (Phase 5)**                                      │
│  - Dashboard (ForceGraph 3D)                                     │
│  - File Explorer (TreeView)                                      │
│  - Jira Integration (Semantic Linking)                           │
└─────────────────────────────────────────────────────────────────┘
                              ▲
┌─────────────────────────────────────────────────────────────────┐
│  **Interaction (Phases 3-4)**                                    │
│  - User Elicitation (ctx.request_input)                          │
│  - Background Tasks (task=True)                                  │
│  - Rich Content (Tables, Diagrams, Progress)                     │
│  - Icons & Badges                                                │
└─────────────────────────────────────────────────────────────────┘
                              ▲
┌─────────────────────────────────────────────────────────────────┐
│  **Agent Core (Pydantic-AI + Extensions)**                       │
│  - Slim: Lightweight dispatcher (openai, google)                 │
│  - Graph: Type-safe ReAct workflows                              │
│  - Deep: Planning & self-correction                              │
│  - Skills: Python-native tool organization                       │
│  - Hindsight: Long-term memory (Ladybug)                         │
└─────────────────────────────────────────────────────────────────┘
                              ▲
┌─────────────────────────────────────────────────────────────────┐
│  **Infrastructure**                                              │
│  - FastMCP 3.0 (CodeMode, StaticTokenVerifier, Middleware)       │
│  - OpenTelemetry (Tracing, Metrics, Logging)                     │
│  - Versioning                                                    │
└─────────────────────────────────────────────────────────────────┘
```

---

## Implementation Roadmap

### Phase 1: Foundation (Weeks 1-2)
- [x] **001:** Pydantic-AI-Slim integration
- [x] **002:** Pydantic-Graph (ReAct workflows)
- [x] **003:** Pydantic-Deep (Planning)
- [x] **004:** Pydantic-AI-Skills (Python skills)
- [x] **005:** Hindsight (Memory)

**Outcome:** Core Five agents run on upgraded Pydantic stack with memory.

### Phase 2: Interaction (Weeks 3-4)
- [x] **006:** Phase 3 interactivity (confirmations)
- [x] **007:** Phase 4a (icons, rich content)
- [x] **008:** Phase 4b (background tasks)

**Outcome:** Server is responsive with visual polish and no timeouts.

### Phase 3: Knowledge Visualization (Weeks 5-6)
- [x] **009:** Phase 5a dashboard (ForceGraph)
- [x] **010:** Phase 5b Jira embedder
- [x] **011:** Phase 5c file explorer

**Outcome:** Users can visualize and navigate the knowledge graph.

### Phase 4: Quality & Operations (Weeks 7-8)
- [x] **014:** Pydantic-Evals (agent benchmarking - CRITICAL)
- [x] **015:** Logfire (real-time monitoring - CRITICAL)
- [x] **012:** OpenTelemetry (infrastructure tracing)
- [x] **013:** Versioning (polish)

**Outcome:** Agents are validated & observable. System is properly versioned.

---

## Key Dependencies & Relationships

### Critical Path (Minimum Viable - BLOCKS EVERYTHING)
```
001 (Slim) → 002 (Graph) → 003 (Deep) → 004 (Skills) → 005 (Hindsight)
                ↓
           **014 (Evals: Validate agents work)**
           **015 (Logfire: Monitor production)**          
           All agents updated & tested
```

**Note:** Features 014 & 015 are not optional—without evals, you have no proof agents work. Without Logfire, you can't debug issues in production.

### Interactivity Dependency
```
006 (Confirmations) → 007 (Icons) → 008 (Tasks)
        ↓
   Requires context updated in server.py
```

### Dashboard Dependency
```
009 (ForceGraph) → 010 (Jira) → 011 (Files)
        ↓
   All require graph query APIs
```

### Cross-Feature Dependencies
```
012 (OpenTelemetry) spans ALL features
013 (Versioning) is independent
```

---

## Feature Matrix

| Feature | Pydantic | FastMCP | Graph | Agents | UI | Quality |
|---------|----------|---------|-------|--------|----|----|
| 001 Slim | ✓ | — | — | ✓ | — | — |
| 002 Graph | ✓ | — | ✓ | ✓ | — | — |
| 003 Deep | ✓ | — | ✓ | ✓ | — | — |
| 004 Skills | ✓ | ✓ | — | ✓ | — | — |
| 005 Hindsight | ✓ | — | ✓ | ✓ | — | — |
| 006 Phase3 | — | ✓ | ✓ | ✓ | — | — |
| 007 Phase4a | — | ✓ | — | — | ✓ | — |
| 008 Phase4b | — | ✓ | — | — | ✓ | — |
| 009 Phase5a | — | ✓ | ✓ | — | ✓ | — |
| 010 Phase5b | ✓ | ✓ | ✓ | ✓ | ✓ | — |
| 011 Phase5c | — | ✓ | ✓ | — | ✓ | — |
| **014 Evals** | **✓** | **—** | **—** | **✓** | **—** | **✓** |
| **015 Logfire** | **—** | **—** | **—** | **✓** | **—** | **✓** |
| 012 OTel | — | — | — | ✓ | — | ✓ |
| 013 Version | — | ✓ | — | — | — | — |

---

## Success Criteria by Phase

### Phase 1: Foundation ✓
- [ ] Agents use pydantic-ai-slim without errors
- [ ] All agents implement Pydantic-Graph workflows  
- [ ] EXPERT tier agents have planning enabled
- [ ] Skills are Python modules (no .md files)
- [ ] Hindsight auto-extracts and recalls facts

### Phase 2: Interaction ✓
- [ ] Destructive ops require confirmation
- [ ] Heavy tools run as background tasks
- [ ] Tools return rich content (tables, diagrams)
- [ ] All tools have icons

### Phase 3: Visualization ✓
- [ ] Dashboard displays graph with 3D layout
- [ ] Nodes are interactive and queryable
- [ ] File tree shows violations
- [ ] Jira tickets link to code

### Phase 4: Quality ✓
- [ ] All operations emit OpenTelemetry spans
- [ ] Metrics dashboard is operational
- [ ] System versioning is clear

---

## Next Steps After Design

1. **Review & Feedback:** Get team review on all designs
2. **Dependency Planning:** Order implementation to minimize blocking
3. **Task Breakdown:** Convert each design into concrete implementation tasks
4. **Testing Strategy:** Plan unit, integration, and E2E tests per feature
5. **Timeline Refinement:** Estimate actual implementation time

---

## Critical Implementation Notes

### Order of Operations (Strict)
1. **001-002:** Do Slim + Graph first (blocks all agents)
2. **003-005:** Deep + Skills + Hindsight (independent, do in parallel)
3. **006-008:** Phase 3-4 (depends on agents, should be parallel)
4. **009-011:** Phase 5 (depends on graph APIs, can start after 002)
5. **012-013:** OTel + Versioning (independent, low priority)

### Testing Strategy
- **Unit Tests:** Test each component in isolation (e.g., PlanningAgent wrapper)
- **Integration Tests:** Test agent + graph + hindsight together
- **E2E Tests:** Test full flow (e.g., agent run → memory stored → recalled)
- **Performance Tests:** Benchmark agent speed per tier

### Rollout Strategy
- **A/B Test:** Run new stack alongside old (via feature flags)
- **Gradual Migration:** Migrate agents one by one
- **Canary:** Deploy to staging first, validate before production
- **Rollback Plan:** Keep old implementation available until proven stable

---

## Links to Related Documents

- **Task Details:** See `docs/planning/tasks/007-fastmcp-task.md`
- **Proposal (Original):** See `docs/planning/design/proposals/pydantic-upgrade.md`
- **Previous Plans:** See `docs/planning/tasks/archived/`

---

## Questions for User Review

### Quality Control (Evals - CRITICAL)
1. What's the minimum pass rate for merging? (Recommend 80%)
2. Should evals run per-tier comparison on every merge?
3. How many test cases per agent is sufficient? (Recommend 10-20 per agent)
4. For non-deterministic outputs (like plans), is semantic similarity good enough?

### Observability (Logfire - CRITICAL)
1. Should Logfire be mandatory before production deploy?
2. What's the alerting strategy (email, Slack, PagerDuty)?
3. Should we log PII (user code)? Need to mask sensitive data?
4. How long to retain logs (30 days default is ok)?

### Implementation Priority
1. Features 014-015 should block all other work until stable, agreed?
2. Can foundation (001-005) and evals (014) happen in parallel?
3. Should Phase 5 (dashboard) wait until Logfire is working?

---

## Version History

| Date | Version | Status | Author |
|------|---------|--------|--------|
| 2026-04-13 | 0.1.0 | Design Complete | Claude |
| TBD | 1.0.0 | Implementation Complete | Team |

---

**Next:** Wait for user review, then begin implementation tasks.
