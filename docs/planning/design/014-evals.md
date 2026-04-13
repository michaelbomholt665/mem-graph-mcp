# Design: Pydantic-Evals (Agent Benchmarking)

**Status:** Design Phase  
**Priority:** CRITICAL (Quality validation)  
**Date:** 2026-04-13

---

## Overview

Pydantic-Evals is a stochastic testing framework that benchmarks agents against expected outputs. Instead of manual testing, you:

1. **Define Test Cases:** Input + expected output pairs for each agent
2. **Run Agent:** Feed input through agent (may produce different outputs due to LLM variability)
3. **Score Output:** Does agent output match expected behavior?
4. **Aggregate:** Get pass rate, confidence intervals, failure patterns

This is **critical** because LLMs are non-deterministic—we need statistical proof agents work correctly.

---

## Goals

1. **Validate Agent Behavior:** Ensure agents produce correct outputs consistently
2. **Detect Regression:** Catch when agent quality drops after changes
3. **Measure Tier Differences:** Verify EXPERT tier agents outperform QUICK tier
4. **Identify Failure Patterns:** Where do agents systematically fail?

---

## Scope

### In Scope
- Define test suites for each Core Five agent (audit, map, fix, validate, document)
- Implement scoring logic (exact match, semantic similarity, custom validators)
- Run evals on CI/CD pipeline
- Generate eval reports (pass rates, failure breakdown)
- Track eval scores over time (regression detection)
- Compare tier performance (QUICK vs STANDARD vs EXPERT)

### Out of Scope
- Running evals in production (only dev/staging)
- Auto-tuning prompts based on eval results (manual refinement)
- Distributed eval execution (sequential is fine)

---

## Architecture

### 1. Test Case Definition

```python
# src/mem_graph/evals/audit_evals.py

from pydantic import BaseModel, Field
from typing import Callable

class EvalTestCase(BaseModel):
    """Single test case for an eval."""
    id: str
    input: str = Field(description="What to feed the agent")
    expected_output: str = Field(description="What we expect")
    description: str = Field(description="Why this test matters")
    tags: list[str] = Field(default_factory=list)  # e.g., ["critical", "performance"]

class EvalSuite(BaseModel):
    """Collection of test cases for an agent."""
    agent_name: str
    description: str
    test_cases: list[EvalTestCase]
    scorer: Callable[[str, str], float]  # (output, expected) → score 0-1

# Audit Agent Test Cases
AUDIT_EVALS = EvalSuite(
    agent_name="audit",
    description="Audit agent identifies code smells and issues",
    test_cases=[
        EvalTestCase(
            id="audit-001",
            input="""
def process_data(data):
    result = []
    for item in data:
        if item:
            if item.valid:
                temp = item.value * 2
                result.append(temp)
    return result
            """,
            expected_output="nested if statements (low readability), consider early return pattern",
            description="Should detect deeply nested control flow",
            tags=["critical", "code_smell"],
        ),
        EvalTestCase(
            id="audit-002",
            input="""
def fetch_user(user_id):
    try:
        user = db.query(user_id)
        return user
    except:
        pass
            """,
            expected_output="bare except clause (dangerous), missing error handling, performance issue",
            description="Should catch broad exception handling",
            tags=["critical", "safety"],
        ),
        EvalTestCase(
            id="audit-003",
            input="def simple_function():\n    x = 1\n    return x",
            expected_output="no issues found",
            description="Clean code should pass without warnings",
            tags=["sanity"],
        ),
    ],
    scorer=semantic_similarity_scorer,  # See below
)

# Fix Agent Test Cases
FIX_EVALS = EvalSuite(
    agent_name="fix",
    description="Fix agent proposes code refactorings",
    test_cases=[
        EvalTestCase(
            id="fix-001",
            input="Refactor this deeply nested function using early returns",
            expected_output="function uses early returns at start to guard against conditions",
            description="Should apply early return pattern",
            tags=["pattern"],
        ),
    ],
    scorer=semantic_similarity_scorer,
)

# Validate Agent Test Cases
VALIDATE_EVALS = EvalSuite(
    agent_name="validate",
    description="Validate agent checks if code changes work correctly",
    test_cases=[
        EvalTestCase(
            id="validate-001",
            input="Check if these edits introduce new issues: [patch code]",
            expected_output="no new safety issues, no performance regression",
            description="Should verify proposed changes",
            tags=["safety"],
        ),
    ],
    scorer=exact_match_scorer,
)

# All evals
ALL_EVALS = [AUDIT_EVALS, FIX_EVALS, VALIDATE_EVALS]
```

### 2. Scoring Functions

```python
# src/mem_graph/evals/scorers.py

from sentence_transformers import util

def semantic_similarity_scorer(output: str, expected: str) -> float:
    """
    Score based on semantic similarity (0-1).
    
    Uses embeddings to check if output means the same thing as expected,
    even if wording differs.
    
    Example:
      output = "fix nested if statements"
      expected = "reduce nesting depth using early returns"
      score = 0.85  # semantically similar
    """
    
    from sentence_transformers import SentenceTransformer
    
    model = SentenceTransformer('all-MiniLM-L6-v2')
    
    output_embedding = model.encode(output, convert_to_tensor=True)
    expected_embedding = model.encode(expected, convert_to_tensor=True)
    
    similarity = float(util.pytorch_cos_sim(output_embedding, expected_embedding)[0][0])
    
    # Require high confidence (75%+)
    return max(0, (similarity - 0.75) / 0.25)

def exact_match_scorer(output: str, expected: str) -> float:
    """
    Score based on exact match (0 or 1).
    
    Used when output is very specific (e.g., JSON structure).
    
    Example:
      output = '{"status": "approved"}'
      expected = '{"status": "approved"}'
      score = 1.0
    """
    
    import json
    
    try:
        output_json = json.loads(output)
        expected_json = json.loads(expected)
        return 1.0 if output_json == expected_json else 0.0
    except:
        # Fallback to string comparison
        return 1.0 if output.strip() == expected.strip() else 0.0

def contains_keywords_scorer(output: str, expected_keywords: list[str]) -> float:
    """
    Score based on presence of expected keywords.
    
    Used for flexible outputs that should contain certain concepts.
    
    Example:
      output = "This function has deeply nested loops and uses broad exception handling"
      expected_keywords = ["nested", "exception"]
      score = 1.0  # Both keywords present
    """
    
    output_lower = output.lower()
    found = sum(1 for keyword in expected_keywords if keyword.lower() in output_lower)
    
    return found / len(expected_keywords) if expected_keywords else 0.0

def regex_match_scorer(output: str, pattern: str) -> float:
    """
    Score based on regex pattern match.
    
    Used for outputs with expected structure/format.
    """
    
    import re
    
    if re.search(pattern, output, re.IGNORECASE):
        return 1.0
    return 0.0
```

### 3. Evaluator Runner

```python
# src/mem_graph/evals/evaluator.py

from dataclasses import dataclass
from typing import Optional
import asyncio
from datetime import datetime

@dataclass
class EvalResult:
    """Result of a single test case eval."""
    test_id: str
    passed: bool
    score: float  # 0-1
    output: str  # What agent actually produced
    expected: str
    error: Optional[str] = None
    duration_ms: float = 0.0

@dataclass
class EvalReport:
    """Results from running an entire eval suite."""
    suite_name: str
    timestamp: datetime
    total_tests: int
    passed_tests: int
    failed_tests: int
    pass_rate: float
    results: list[EvalResult]
    errors: list[str] = None
    
    def summary(self) -> str:
        """Human-readable summary."""
        return f"{self.suite_name}: {self.pass_rate*100:.1f}% ({self.passed_tests}/{self.total_tests})"

class Evaluator:
    """Run evals against agents."""
    
    def __init__(self, graph_client):
        self.graph = graph_client
    
    async def run_eval_suite(
        self,
        suite: EvalSuite,
        agent,
        tier: ModelTier = ModelTier.STANDARD,
        num_runs: int = 3,  # Run each test multiple times (stochastic)
    ) -> EvalReport:
        """
        Run entire eval suite against an agent.
        
        Runs each test case multiple times to account for LLM variability.
        """
        
        results = []
        
        for test_case in suite.test_cases:
            # Run test multiple times
            scores = []
            
            for run in range(num_runs):
                try:
                    start = time.time()
                    
                    # Call agent
                    output = await agent.run(test_case.input)
                    
                    duration = (time.time() - start) * 1000
                    
                    # Score output
                    score = suite.scorer(output.data, test_case.expected_output)
                    scores.append(score)
                    
                    logger.info(f"Test {test_case.id} run {run+1}: {score:.2f}")
                
                except Exception as e:
                    logger.error(f"Test {test_case.id} failed: {e}")
                    scores.append(0.0)
            
            # Average score across runs
            avg_score = sum(scores) / len(scores)
            passed = avg_score > 0.7  # 70%+ is pass
            
            results.append(EvalResult(
                test_id=test_case.id,
                passed=passed,
                score=avg_score,
                output=output.data if output else "",
                expected=test_case.expected_output,
                duration_ms=duration,
            ))
        
        # Build report
        passed_count = sum(1 for r in results if r.passed)
        
        report = EvalReport(
            suite_name=suite.agent_name,
            timestamp=datetime.now(),
            total_tests=len(suite.test_cases),
            passed_tests=passed_count,
            failed_tests=len(results) - passed_count,
            pass_rate=passed_count / len(results) if results else 0.0,
            results=results,
        )
        
        return report
    
    async def run_all_evals(self) -> dict[str, EvalReport]:
        """Run all eval suites and return results."""
        
        reports = {}
        
        for suite in ALL_EVALS:
            # Get agent
            match suite.agent_name:
                case "audit":
                    agent = create_audit_agent(ModelTier.STANDARD)
                case "fix":
                    agent = create_fix_agent(ModelTier.STANDARD)
                case "validate":
                    agent = create_validate_agent(ModelTier.STANDARD)
                case _:
                    continue
            
            # Run eval
            report = await self.run_eval_suite(suite, agent)
            reports[suite.agent_name] = report
        
        return reports
```

### 4. CI/CD Integration

```python
# tests/test_evals.py

import pytest
from mem_graph.evals import Evaluator, AUDIT_EVALS, FIX_EVALS
from mem_graph.agents import create_audit_agent, create_fix_agent
from mem_graph.config import ModelTier

@pytest.mark.asyncio
async def test_audit_agent_evals():
    """Audit agent must pass 80%+ of tests."""
    
    agent = create_audit_agent(ModelTier.STANDARD)
    evaluator = Evaluator(None)
    
    report = await evaluator.run_eval_suite(AUDIT_EVALS, agent)
    
    print(f"\n{report.summary()}")
    for result in report.results:
        status = "✓" if result.passed else "✗"
        print(f"  {status} {result.test_id}: {result.score:.2f}")
    
    # Assert pass rate
    assert report.pass_rate >= 0.80, f"Audit agent pass rate too low: {report.pass_rate:.2f}"

@pytest.mark.asyncio
async def test_expert_tier_outperforms_quick():
    """EXPERT tier should outperform QUICK tier."""
    
    agent_quick = create_audit_agent(ModelTier.QUICK)
    agent_expert = create_audit_agent(ModelTier.EXPERT)
    evaluator = Evaluator(None)
    
    report_quick = await evaluator.run_eval_suite(AUDIT_EVALS, agent_quick)
    report_expert = await evaluator.run_eval_suite(AUDIT_EVALS, agent_expert)
    
    assert report_expert.pass_rate > report_quick.pass_rate, \
        f"Expert ({report_expert.pass_rate:.2f}) should beat Quick ({report_quick.pass_rate:.2f})"

# Run evals before deployment
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

### 5. Eval Report Tracking

Store eval results in graph for historical comparison:

```python
# Cypher schema

CREATE (:EvalRun {
  id: "...",
  timestamp: datetime(),
  agent: "audit",
  tier: "STANDARD",
  pass_rate: 0.85,
  total_tests: 10,
  passed_tests: 8,
})

(eval_run:EvalRun)-[:TESTED]->(agent:Agent)
(eval_run:EvalRun)-[:INCLUDES]->(result:EvalResult {
  test_id: "audit-001",
  score: 0.92,
  passed: true,
})
```

---

## Example: Running Evals

```bash
# Run all evals before merge
pytest tests/test_evals.py -v

# Output:
# test_audit_agent_evals PASSED ✓
#   ✓ audit-001: 0.95
#   ✓ audit-002: 0.88
#   ✓ audit-003: 1.00
# pass_rate: 94%

# test_expert_tier_outperforms_quick PASSED ✓
# EXPERT (92%) > QUICK (78%)
```

---

## Benefits

1. **Statistical Proof:** Know agent quality with confidence intervals
2. **Regression Detection:** Early warning if agent quality drops
3. **Tier Validation:** Verify EXPERT > STANDARD > QUICK
4. **Debugging:** Identify systematic failure patterns
5. **CI/CD Gate:** Block merges if agent evals fail

---

## When Evals Are Run

| Context | Frequency | Required? |
|---------|-----------|-----------|
| Local dev | Before commit | No (optional) |
| PR merge | Before merge | **YES** |
| Release | Before deploy | **YES** |
| Nightly | 1x per night | **YES** (tracking) |

---

## Implementation Checklist

- [ ] Define test cases for each Core Five agent
- [ ] Implement scoring functions (semantic, exact, keywords, regex)
- [ ] Create Evaluator runner
- [ ] Add eval suite definitions to each agent file
- [ ] Integrate evals into pytest
- [ ] Add CI/CD gate (block merge if pass_rate < 80%)
- [ ] Setup eval result tracking in graph
- [ ] Create eval dashboard (pass rate over time)
- [ ] Document eval maintenance (how to add new tests)

---

## Success Criteria

1. All agent evals pass at 80%+ rate
2. EXPERT tier outperforms QUICK tier by 10%+
3. No regression in pass rate across releases
4. Can identify which specific tests fail systematically
5. Evals block PR merge if score drops

---

## Dependencies

- `pydantic-evals>=1.80.0` (already in `pyproject.toml`)
- `sentence-transformers>=5.4.0` (already in `pyproject.toml`) for semantic scoring
- pytest for test runner

---

## Notes

- Evals must run against real LLMs (not mocks)—stochastic, expensive, but necessary
- Each test case should run multiple times (3+) to account for variability
- Semantic similarity scorer is most useful for agents with fuzzy outputs
- Exact match scorer only works for deterministic outputs (JSON, status codes)
- Consider timeout per test (30s max) to catch hung agents
