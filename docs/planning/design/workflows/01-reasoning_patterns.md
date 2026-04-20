# Reasoning Patterns — Visual Reference

This document provides example workflow diagrams for the four core reasoning patterns used across
the workflow registry. Each pattern is shown as a minimal, self-contained example first, then
mapped to real workflow usage.

> These patterns map to the two `ReasoningMode` values in the registry:  
> - `REACT_CHALLENGE` → ReAct 1 and ReAct 2  
> - `BOUNDED_TOT` → Tree-of-Thought and Chain-of-Thought

---

## ReAct 1 — Plan · Re-think · Design · Execute

The **default reasoning pattern**. Every major decision goes through a self-challenge step
("re-think") before design begins. If the re-think reveals a flaw, the plan is restarted.
This prevents acting on a bad first instinct.

```mermaid
---
config:
  theme: base
  look: classic
  themeVariables:
    primaryColor: "#1e40af"
    primaryTextColor: "#ffffff"
    primaryBorderColor: "#1d4ed8"
    secondaryColor: "#3b82f6"
    tertiaryColor: "#dbeafe"
    lineColor: "#64748b"
    edgeLabelBackground: "#eff6ff"
    clusterBkg: "#eff6ff"
    clusterBorder: "#3b82f6"
    fontFamily: "ui-monospace, monospace"
    fontSize: "13px"
---
flowchart LR
    Start(["Task\nreceived"]):::startEnd

    subgraph REACT1 ["ReAct 1 — Plan · Re-think · Design · Execute"]
        direction LR

        plan["① plan
        Observe all context.
        Form an initial hypothesis
        about what to do."]:::stageNode

        rethink{"② re-think
        Challenge the plan:
        What is wrong with it?
        Is there missing context?
        Is there a better approach?"}:::decisionNode

        design["③ design
        With the challenge resolved,
        produce the detailed design
        or implementation approach."]:::stageNode

        execute["④ execute
        Act on the design.
        Write code, create files,
        or produce the artifact."]:::stageNode

        plan --> rethink
        rethink -. "❌ flaw found\nrestart plan" .-> plan
        rethink -- "✅ challenge passed" --> design
        design --> execute
    end

    Result(["Artifact\nproduced"]):::startEnd

    Start --> plan
    execute --> Result

    classDef startEnd   fill:#1e3a8a,stroke:#1e40af,color:#fff,font-weight:bold,rx:20
    classDef stageNode  fill:#dbeafe,stroke:#3b82f6,color:#1e3a8a,text-align:left
    classDef decisionNode fill:#bfdbfe,stroke:#1d4ed8,color:#1e3a8a,font-weight:bold
    style REACT1 fill:#eff6ff,stroke:#3b82f6,stroke-width:2px,color:#1e3a8a,font-weight:bold
```

**Used by:** most MEDIUM and LARGE workflows (`feature_implementation`, `managed_workflow_graph`,
`autopilot_graph` guard stage, `adr_authoring`, `refactor`, etc.)

---

## ReAct 2 — Plan · Confirm/Improve/Drop · Design · Execute

An **extended variant** with an explicit decision gate *before* design: the previous decision or
draft is surfaced and the agent must actively choose to confirm it, improve it, or drop it
(start over). Forces conscious acknowledgment of prior work rather than silent continuation.

```mermaid
---
config:
  theme: base
  look: classic
  themeVariables:
    primaryColor: "#0e7490"
    primaryTextColor: "#ffffff"
    primaryBorderColor: "#0369a1"
    secondaryColor: "#22d3ee"
    tertiaryColor: "#cffafe"
    lineColor: "#64748b"
    edgeLabelBackground: "#ecfeff"
    clusterBkg: "#ecfeff"
    clusterBorder: "#06b6d4"
    fontFamily: "ui-monospace, monospace"
    fontSize: "13px"
---
flowchart LR
    Start(["Task received\n+ prior decision\nor draft context"]):::startEnd

    subgraph REACT2 ["ReAct 2 — Plan · Confirm / Improve / Drop · Design · Execute"]
        direction LR

        plan["① plan
        Observe context + prior draft.
        Re-read the original goal.
        Form an updated hypothesis."]:::stageNode

        gate{"② confirm / improve / drop
        Review the prior decision:
        ─ CONFIRM: it still holds, proceed
        ─ IMPROVE: adjust and continue
        ─ DROP: prior work is invalid,
          start from scratch"}:::decisionNode

        design["③ design
        Produce the refined design
        based on the confirmed or
        improved direction."]:::stageNode

        execute["④ execute
        Act on the final design."]:::stageNode

        plan --> gate
        gate -- "✅ CONFIRM\nor IMPROVE" --> design
        gate -. "🗑 DROP\nrestart from clean context" .-> plan
        design --> execute
    end

    Result(["Artifact\nproduced"]):::startEnd

    Start --> plan
    execute --> Result

    classDef startEnd    fill:#164e63,stroke:#0e7490,color:#fff,font-weight:bold,rx:20
    classDef stageNode   fill:#cffafe,stroke:#06b6d4,color:#164e63,text-align:left
    classDef decisionNode fill:#a5f3fc,stroke:#0e7490,color:#164e63,font-weight:bold
    style REACT2 fill:#ecfeff,stroke:#06b6d4,stroke-width:2px,color:#164e63,font-weight:bold
```

**Used by:** `implementation_planning` (reviewing the feature design before committing to a code
plan), `adr_authoring` (explicitly confirms or revises the previous decision), `requirements_elicitation`
(challenge-scope gate).

---

## Tree-of-Thought (ToT) — Branch · Prune · Select · Expand · Decide

**Bounded Tree-of-Thought** explores multiple candidate approaches simultaneously, scores them
against pruning criteria, eliminates the losers, and only *then* expands the winning branch into
a full solution. Width and depth are hard-capped (`width=3, depth=2, budget_cap=500`).

```mermaid
---
config:
  theme: base
  look: classic
  themeVariables:
    primaryColor: "#7e22ce"
    primaryTextColor: "#ffffff"
    primaryBorderColor: "#6d28d9"
    secondaryColor: "#a855f7"
    tertiaryColor: "#f3e8ff"
    lineColor: "#64748b"
    edgeLabelBackground: "#faf5ff"
    clusterBkg: "#faf5ff"
    clusterBorder: "#9333ea"
    fontFamily: "ui-monospace, monospace"
    fontSize: "12px"
---
flowchart TD
    Start(["Initial\nproblem state"]):::startEnd

    subgraph TOTW ["Tree-of-Thought — Branch Width ≤ 3, Depth ≤ 2"]

        subgraph LVL0 ["Level 0 — Observe"]
            observe["observe
            Review all context.
            Define the decision space."]:::stageNode
        end

        subgraph LVL1 ["Level 1 — Branch (width ≤ 3)"]
            direction LR
            d1["decision 1
            Approach A
            ─────────
            score: high"]:::branchKeep
            d2["decision 2
            Approach B
            ─────────
            score: medium"]:::branchKeep
            d3["decision 3
            Approach C
            ─────────
            score: ❌ pruned"]:::branchPrune
        end

        subgraph LVL2 ["Level 2 — Expand best branch (depth ≤ 2)"]
            direction LR
            d1a["decision 1a
            Step 1 of A
            ─────────
            score: high"]:::branchKeep
            d1b["decision 1b
            Step 2 of A
            ─────────
            score: medium"]:::branchKeep
            d1c["decision 1c
            Step 3 of A
            ─────────
            score: ❌ pruned"]:::branchPrune
        end

        subgraph LVL3 ["Level 3 — Select & Decide"]
            decide["decide
            Select highest-scoring
            surviving path.
            Execute chosen direction."]:::stageNode
        end

        observe --> d1 & d2 & d3
        d3 -. "pruned ✂" .-> decide
        d1 --> d1a & d1b & d1c
        d2 -. "pruned ✂" .-> decide
        d1c -. "pruned ✂" .-> decide
        d1a & d1b --> decide
    end

    Result(["Best path\nexecuted"]):::startEnd

    Start --> observe
    decide --> Result

    classDef startEnd   fill:#4c1d95,stroke:#7e22ce,color:#fff,font-weight:bold,rx:20
    classDef stageNode  fill:#f3e8ff,stroke:#9333ea,color:#4c1d95,font-weight:bold
    classDef branchKeep fill:#ede9fe,stroke:#7c3aed,color:#4c1d95
    classDef branchPrune fill:#fce7f3,stroke:#be185d,color:#831843,font-style:italic
    style TOTW fill:#faf5ff,stroke:#9333ea,stroke-width:2px,color:#4c1d95,font-weight:bold
    style LVL0 fill:#f5f3ff,stroke:#8b5cf6,stroke-dasharray:4 2
    style LVL1 fill:#f5f3ff,stroke:#8b5cf6,stroke-dasharray:4 2
    style LVL2 fill:#f5f3ff,stroke:#8b5cf6,stroke-dasharray:4 2
    style LVL3 fill:#f5f3ff,stroke:#8b5cf6,stroke-dasharray:4 2
```

**Pruning criteria** (from `BOUNDED_TOT_POLICY`):
1. Violates an active architectural decision
2. Requires more context than is available
3. Exceeds the tool budget for the current stage
4. Creates a circular dependency

**Used by:** `architecture_design`, `research`, `requirements_elicitation`, `schema_design`,
`disaster_recovery`, `security_hardening`, `codebase_migration`, `code_skeptic`

---

## Chain-of-Thought (CoT) — Parallel Paths · Step-wise Best-Pick · Converge

**Chain-of-Thought** runs multiple reasoning paths in parallel at each step, picks the best
candidate after each step, then carries only that candidate forward into the next step.
This prevents local optima by exploring width at every level, not just the first.

```mermaid
---
config:
  theme: base
  look: classic
  themeVariables:
    primaryColor: "#065f46"
    primaryTextColor: "#ffffff"
    primaryBorderColor: "#047857"
    secondaryColor: "#10b981"
    tertiaryColor: "#d1fae5"
    lineColor: "#64748b"
    edgeLabelBackground: "#f0fdf4"
    clusterBkg: "#f0fdf4"
    clusterBorder: "#059669"
    fontFamily: "ui-monospace, monospace"
    fontSize: "12px"
---
flowchart LR
    Start(["Initial\nproblem state"]):::startEnd

    subgraph COT ["Chain-of-Thought — 3 Parallel Paths per Step, 3 Steps"]

        subgraph STEP1 ["Step 1 — Generate 3 candidate answers"]
            direction TB
            s1a["decision 1
            Path A answer\nfor step 1"]:::pathNode
            s1b["decision 2
            Path B answer\nfor step 1"]:::pathNode
            s1c["decision 3
            Path C answer\nfor step 1"]:::pathNode
        end

        pick1{{"① pick best\nafter step 1"}}:::pickNode

        subgraph STEP2 ["Step 2 — Re-generate 3 candidates from best"]
            direction TB
            s2a["decision 1
            Path A answer\nfor step 2"]:::pathNode
            s2b["decision 2
            Path B answer\nfor step 2"]:::pathNode
            s2c["decision 3
            Path C answer\nfor step 2"]:::pathNode
        end

        pick2{{"② pick best\nafter step 2"}}:::pickNode

        subgraph STEP3 ["Step 3 — Final 3 candidates"]
            direction TB
            s3a["decision 1
            Path A answer\nfor step 3"]:::pathNode
            s3b["decision 2
            Path B answer\nfor step 3"]:::pathNode
            s3c["decision 3
            Path C answer\nfor step 3"]:::pathNode
        end

        decide{{"③ final\ndecision"}}:::pickNode

        s1a & s1b & s1c --> pick1
        pick1 --> s2a & s2b & s2c
        s2a & s2b & s2c --> pick2
        pick2 --> s3a & s3b & s3c
        s3a & s3b & s3c --> decide
    end

    Result(["Final answer\nchosen"]):::startEnd

    Start --> s1a & s1b & s1c
    decide --> Result

    classDef startEnd fill:#064e3b,stroke:#065f46,color:#fff,font-weight:bold,rx:20
    classDef pathNode fill:#d1fae5,stroke:#10b981,color:#064e3b
    classDef pickNode fill:#6ee7b7,stroke:#059669,color:#064e3b,font-weight:bold
    style COT fill:#ecfdf5,stroke:#059669,stroke-width:2px,color:#064e3b,font-weight:bold
    style STEP1 fill:#f0fdf4,stroke:#34d399,stroke-dasharray:4 2
    style STEP2 fill:#f0fdf4,stroke:#34d399,stroke-dasharray:4 2
    style STEP3 fill:#f0fdf4,stroke:#34d399,stroke-dasharray:4 2
```

**How CoT differs from ToT:**

| | Tree-of-Thought | Chain-of-Thought |
|-|----------------|-----------------|
| Structure | Tree: branches prune across levels | Chain: parallel choices at each step, best carries forward |
| Width | Fixed max at root, expands downward | Regenerated fresh at every step |
| Pruning | Happens at each level | Implicit: only the best candidate survives each round |
| Best for | Architecture decisions, threat modelling | Multi-step reasoning where each step reframes the next |
| Registry mapping | `BOUNDED_TOT_POLICY` | Can be modelled as a ToT variant with depth-per-step reset |

> **Current registry note:** `BOUNDED_TOT_POLICY` captures both ToT and CoT intent.
> A future `CHAIN_OF_THOUGHT` `ReasoningMode` variant could differentiate them explicitly.

---

## Pattern Selection Guide

```mermaid
---
config:
  theme: base
  look: classic
  themeVariables:
    primaryColor: "#1e293b"
    primaryTextColor: "#f8fafc"
    primaryBorderColor: "#334155"
    lineColor: "#64748b"
    fontFamily: "ui-monospace, monospace"
    fontSize: "12px"
---
flowchart TD
    Q1{"Is the task\nhigh-ambiguity?"}

    Q2{"Does the task require\nexploring multiple\nindependent approaches?"}
    Q3{"Do early decisions\nstrongly constrain\nlater ones?"}

    REACT1["Use ReAct 1
    plan → re-think → design → execute
    ─────────────────
    Best for: most tasks
    Risk: any
    Mode: REACT_CHALLENGE"]:::rNode

    REACT2["Use ReAct 2
    plan → confirm/improve/drop → design → execute
    ─────────────────
    Best for: iterating on prior work
    Risk: medium/high
    Mode: REACT_CHALLENGE"]:::rNode

    TOT["Use Tree-of-Thought
    branch → prune → expand → decide
    ─────────────────
    Best for: architectural decisions,
    threat modelling, migration strategy
    Mode: BOUNDED_TOT"]:::tNode

    COT["Use Chain-of-Thought
    parallel paths → pick best → repeat
    ─────────────────
    Best for: multi-step reasoning where
    each step reframes the next
    Mode: BOUNDED_TOT (variant)"]:::cNode

    Q1 -- "no → keep it simple" --> REACT1
    Q1 -- "yes" --> Q2
    Q2 -- "no, iterating on\nexisting draft" --> REACT2
    Q2 -- "yes, multiple\nindependent paths" --> Q3
    Q3 -- "yes → prune early,\nexpand one winner" --> TOT
    Q3 -- "no → re-evaluate\nat each step" --> COT

    classDef rNode fill:#dbeafe,stroke:#3b82f6,color:#1e3a8a,font-weight:bold
    classDef tNode fill:#f3e8ff,stroke:#9333ea,color:#4c1d95,font-weight:bold
    classDef cNode fill:#d1fae5,stroke:#059669,color:#064e3b,font-weight:bold
```
