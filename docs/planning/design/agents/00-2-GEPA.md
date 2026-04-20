# 00-2 — GEPA: Genetic-Pareto Prompt Evolution

> **Status:** Reference document — architectural pattern for future evaluation infrastructure
> **Source:** Session `6e0f4bf2` gap-fill research
> **See also:** `08-evals.md` (eval infrastructure), `00-1-report.md` (command mapping)

---

## Overview

**GEPA (Genetic-Pareto Prompt Evolution)** is an automated framework for prompt optimisation that
applies evolutionary algorithms to systematically improve AI agent instructions. It moves prompt
engineering from a manual, inconsistent "art" to a rigorous, data-driven "science" by having an
algorithm explore the prompt space based on structured feedback.

GEPA is the formal name for the pattern identified in `00-researcha-acomments.md` §3 — "an agent
to improve other agents based on evaluation data."

---

## 1. Core Concepts

### The Evolutionary Analogy

The core of GEPA is analogous to breeding racing pigeons:

| Step | Analogy | Technical Equivalent |
|------|---------|---------------------|
| Population | Starting flock | Seed prompts for each agent |
| Evaluation | Race day | Run prompts against test dataset |
| Crossover | Breeding | Combine successful prompt variants |
| Mutation | Selective pressure | LLM "proposer" analyses failures, suggests improvements |
| Selection | Keep the fastest | Pareto selection — keep best performers, discard rest |

### Why GEPA Over Manual Iteration

Unlike a human developer tweaking prompts after seeing a few failures, GEPA is **systematic and
scalable**:

- Captures all failure patterns across large datasets
- Avoids human biases and "anchoring" on prior prompt versions
- Optimises **multiple agents simultaneously**, accounting for complex cross-agent prompt interactions
- Builds a compounding improvement record across generations

---

## 2. The Iterative Optimisation Loop

A single GEPA iteration follows this sequence:

1. **Sample Mini-Batch** — Select a small group of cases from the training dataset
2. **Evaluate Candidates** — Run the current best prompt against the batch using `pydantic-evals`
3. **Capture Trajectories** — Record detailed execution data and OpenTelemetry traces (via Logfire)
4. **Build Reflective Dataset** — Compile structured feedback on failures and edge cases
5. **Propose Mutations** — A dedicated **proposer LLM** analyses failures and suggests prompt improvements
6. **Accept/Reject** — Accept the mutation only if it improves the dataset score; otherwise discard

---

## 3. Pareto Selection — How It Filters Candidates

Pareto selection is step 5 in the six-step GEPA cycle. It is the critical filter that maintains
quality across generations.

### Key Characteristics

- **Efficiency through sampling:** Evaluates candidates on mini-batches rather than the full
  dataset — exploring far more of the prompt space than manual iteration can afford.
- **Multi-module optimisation:** Identifies combinations of prompts across different agents that
  work best *together*, accounting for interactions a human would likely miss.
- **Systematic growth:** Ensures each generation is statistically more likely to be faster or
  more accurate than the previous one.
- **Regression prevention:** Mutations that reduce performance are automatically discarded via the
  accept/reject gate.

---

## 4. Technical Implementation with Pydantic AI

GEPA integrates with the Pydantic ecosystem through three key mechanisms:

### `Agent.override()`

Used to temporarily inject candidate prompts during optimisation. This allows thread-safe testing
of new instructions without modifying the underlying agent definition:

```python
with agent.override(system_prompt="Candidate prompt v2"):
    result = await agent.run(test_input, deps=test_deps)
```

### Parallel Evaluation

`pydantic-evals` runs test cases concurrently as the harness, significantly speeding up the
optimisation process:

```python
# Each candidate runs against the full mini-batch in parallel
report = await evaluator.run_report(
    registry=SUITE_REGISTRY,
    runs=3,
    concurrency=4
)
```

### Trace Analysis

Via Logfire, the proposer LLM sees the full internal reasoning path — including tool calls and
latency — to make more informed mutation suggestions. See `00-researcha-acomments.md` §5 for the
span-based implementation pattern.

---

## 5. Applications Beyond Prompt Optimisation

### 5.1 Optimising LLM-as-a-Judge Evaluators

GEPA can be applied to **the evaluators themselves**, not just agent prompts.

**Problem:** LLM judges (`HostedTextScorer`, `LLMJudge`) can have blind spots or exploit
inconsistent scoring rubrics.

**GEPA Solution:** Treat the evaluation rubric as a "prompt" that needs optimisation. Run an
experiment comparing the LLM judge against a "Golden Dataset" (manually verified by humans). GEPA
proposes mutations to the judge's instructions to align scoring with human intent.

### 5.2 Closing the Loop with the Agent Builder

The **Agent Builder** persona (`agents/builder/agent_builder.py`) is designed to use eval evidence
to update and improve existing agent specifications:

- **Evidence-Based Specs:** As evaluations identify regressions or successes, the
  `agent_builder_update` prompt can be triggered to analyse failure patterns and automatically
  adjust YAML/JSON agent specs.
- **Skill Refinement:** Future Skill-Level Evals (measuring precision and recall of specific domain
  knowledge) can feed an optimisation agent that prunes ineffective rules or adds missing ones to
  the `SkillBundle`.

### 5.3 Evolving from Fixtures to Live Traces

Evaluation reliability improves by shifting from static fixture inputs to dynamic data sourced from
Logfire production telemetry:

- **Production Feedback:** Production telemetry provides a continuous stream of real-world "live"
  cases representing actual user behaviour.
- **Automated Dataset Management:** Patterns like `SummarizationProcessor` can extract
  representative success and failure trajectories from production traces to automatically expand
  the evaluation dataset.

### 5.4 Validating Reasoning Integrity (Span-Based Evals)

Moving beyond output-only checks to span-based evals that analyse internal OTel traces:

- **Reasoning Path Validation:** Fetch the Logfire trace, assert the agent followed the correct
  internal logic (e.g., `sql_injection_scan` was called before patch approval).
- **Detecting "Lucky" Guesses:** Prevents "right answer, wrong path" regressions where an agent
  hallucinates a reasoning process that happens to land on the correct final result.

### 5.5 Scorer-Level Evals

Meta-tests verifying that the fundamental scoring tools are themselves accurate:

- `exact_score`: `"approved"` ≠ `"APPROVED"` → score `0.0`
- `keyword_score`: `"drift"` present in `"drifted"` → score ≥ `0.5`
- Unicode normalisation: `"résumé"` matches `"resume"` after NFKD normalisation
- ReDoS prevention: User-provided regex scorers are pre-compiled and validated at suite load time

---

## 6. The Virtuous Cycle

GEPA, the Agent Builder, and span-based evals create a self-reinforcing improvement loop:

```
Production runs → Logfire traces → Span-Based Evals
                                          ↓
                              Failure patterns identified
                                          ↓
                         Proposer LLM generates mutations
                                          ↓
                         Pareto selection keeps improvements
                                          ↓
                       Agent Builder updates agent/skill specs
                                          ↓
                              Better production runs →
```

Agents are optimised based on eval data, and evaluators are refined based on production evidence
and meta-evaluation — a permanent compound improvement loop.

---

## 7. Sub-Agent Hierarchy Guardrails

Related to GEPA's multi-agent coordination: sub-agent spawning is restricted to the Orchestrator
to prevent recursive delegation hazards.

- **Isolated context:** Sub-agents cannot see the parent's full todo list and cannot spawn their
  own sub-agents.
- **Orchestration role:** The Orchestrator is the central dispatcher for `SUBAGENT_REGISTRY`,
  ensuring a predictable hierarchy.
- **Clarification loops:** Sub-agents can use an `answer_subagent` pattern to ask the parent
  Orchestrator for clarification, enabling interactive recovery without breaking the hierarchy.

This complements GEPA by ensuring that the evolving agent population remains safely bounded within
the deterministic workflow graph — the LLM proposes improvements, Python controls execution.

---

## 8. Circular Import Prevention

The Ladybug SCC (Strongly Connected Components) extension detects circular dependencies — the
"architecture killer" for multi-module agent systems.

- **One-Way Dependency Graph:** The recommended structural prevention pattern.
- **Refactoring pattern:** Extract shared logic to a neutral third module (`common.py`, `models.py`)
  or use `TYPE_CHECKING` with quote notation when SCC flags a cycle.

This is especially important for GEPA infrastructure since the proposer, evaluator, and agent
modules must remain loosely coupled to avoid import cycles during testing and live optimisation
runs.
