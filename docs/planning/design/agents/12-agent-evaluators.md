# Agent Evaluators in Pydantic AI

Evaluation is the cornerstone of building reliable AI systems. Pydantic AI provides a native framework for measuring agent performance through various evaluator types and concurrency controls.

## 1. LLM Judges

An **LLM Judge** uses a high-capability model (e.g., GPT-4o) to evaluate the output of another model. It is particularly useful for grading qualitative aspects like reasoning, tone, and adherence to complex rubrics.

### Implementation Pattern

```python
from pydantic_ai.evals import LLMJudge, ScoringRubric

# Define a rubric for the judge
rubric = ScoringRubric(
    criteria={
        "accuracy": "Is the information factually correct?",
        "conciseness": "Is the answer brief and to the point?",
    },
    grading_scale="1-5"
)

# Initialize the judge
judge = LLMJudge(model='openai:gpt-4o', rubric=rubric)

# Use in an evaluation suite
# (Assuming an evaluation framework that consumes this)
```

### Best Practices
- **Rubrics**: Provide clear, unambiguous instructions to the judge.
- **Model Choice**: Use the strongest model available for the judge, even if the agent uses a smaller model.
- **Justification**: Ask the judge to provide reasoning for its score to help debug failures.

---

## 2. Custom Evaluators

**Custom Evaluators** allow for programmatic validation of agent runs. They have access to the `EvaluatorContext`, which includes the input, output, and the entire OpenTelemetry/Logfire span tree.

### Implementation Pattern

```python
from pydantic_ai.evals import Evaluator, EvaluatorContext, EvaluationReason

class SafetyEvaluator(Evaluator):
    """Checks that the agent did not output any prohibited keywords."""

    async def evaluate(self, ctx: EvaluatorContext) -> EvaluationReason:
        prohibited = ["password", "secret", "private_key"]
        output_text = str(ctx.output).lower()
        
        found = [word for word in prohibited if word in output_text]
        if found:
            return EvaluationReason(
                result=False, 
                reason=f"Found prohibited terms: {', '.join(found)}"
            )
        
        return EvaluationReason(result=True, reason="No prohibited terms found.")
```

### Span-Based Evaluation
You can inspect `ctx.span_tree` to verify internal logic (e.g., "Check that the `database_query` tool was called before answering").

---

## 3. Report Evaluators

**Report Evaluators** operate on the aggregate results of multiple evaluation runs. They are used to generate high-level metrics, comparisons between models, or trend analysis.

- **Purpose**: Moving from "pass/fail" on individual cases to "performance summaries" across a whole suite.
- **Use Case**: Comparing Model A vs Model B across 100 test cases and calculating median latency or cost-per-success.

---

## 4. Concurrency & Performance

Running evaluations can be slow and expensive. Pydantic AI allows configuring concurrency to balance speed with rate limits.

### Configuration

```python
from pydantic_ai.evals import EvalRunner

# Configure a runner with concurrency limits
runner = EvalRunner(
    max_concurrency=10,  # Run 10 tests in parallel
    retry_limit=3        # Retry individual failures
)
```

### Performance Tuning
- **Rate Limits**: Match `max_concurrency` to your model provider's Tier-level rate limits.
- **Async Execution**: Ensure all evaluators and agents are async-capable to benefit from concurrency.
- **Progress Tracking**: Use built-in hooks to report progress during long-running eval batches.

---

## 5. Integration with `mem_graph`

For the `mem_graph` project:
1. **Tool Usage Enforcement**: Use Custom Evaluators to inspect `span_tree` and ensure agents are using the `audit` or `search` tools when required.
2. **Deterministic-First**: Prefer regex and keyword scorers for speed, falling back to LLM Judges only for semantic/open-ended reasoning.
3. **CI Integration**: Bind `EvalRunner(max_concurrency=...)` to the `eval gate` command to keep local developer tests fast while staying within CI rate limits.

---

## References
- [LLM Judges | Pydantic AI Docs](https://pydantic.dev/docs/ai/evals/evaluators/llm-judge/)
- [Custom Evaluators](https://pydantic.dev/docs/ai/evals/evaluators/custom/)
- [Report Evaluators](https://pydantic.dev/docs/ai/evals/evaluators/report-evaluators/)
- [Concurrency & Performance](https://pydantic.dev/docs/ai/evals/how-to/concurrency/)
