# Code Review — `src/mem_graph/evals/`

**Reviewer:** GitHub Copilot
**Package:** `src/mem_graph/evals/`
**Files reviewed:**
- `__init__.py`
- `evaluator.py`
- `scorers.py`
- `fixtures.py`
- `audit_evals.py`
- `document_evals.py`
- `fix_evals.py`
- `map_evals.py`
- `validate_evals.py`

---

## Summary

The evals package implements a well-structured stochastic eval harness: `Evaluator` runs cases across multiple repetitions, aggregates scores, and persists compact summaries to the graph. The four scorer types (exact, keywords, regex, semantic) cover the common LLM eval scenarios. (Note: Reliability and performance issues such as timeouts, parallelization, and fixture safety are now covered in 012-evals-review.md).

---

## Issues

### 1. `pass_threshold=0.67` and `default_runs=3` are unexplained magic numbers — LOW

**Location:** All five eval suite definitions

Every suite uses the same `pass_threshold=0.67` and `default_runs=3`. These values appear to be cargo-culted rather than deliberately chosen. There is no accompanying comment explaining why 67% is the right threshold or why 3 runs were chosen as the stochastic sample size.

**Suggested fix:** Define named constants in `evaluator.py` (or a dedicated `constants.py`):

```python
DEFAULT_PASS_THRESHOLD = 0.67  # Allow one miss in three runs
DEFAULT_RUNS = 3               # Minimum for reliable stochastic variance
```

---

### 2. `persist_report_summary` accepts `conn: Any` — INFO

**Location:** `evaluator.py` lines ~235–240

```python
def persist_report_summary(self, report: EvalReport, *, conn: Any, ...) -> str:
```

The `conn` parameter has type `Any`, abandoning static type checking. The function unconditionally calls `conn.execute(...)` with no isinstance guard. If the wrong connection object is passed, the error will be a confusing `AttributeError` at runtime.

**Suggested fix:** Type as `lb.Connection` (the Ladybug type used everywhere else) or extract to a protocol type.

---

### 3. `_normalize_text` does not handle Unicode — INFO

**Location:** `scorers.py` lines ~14–15

```python
def _normalize_text(value: str) -> str:
    return " ".join(value.strip().lower().split())
```

`"résumé"` and `"resume"` will not match even with `lower()`. If eval cases use French technical terms, accent-bearing identifiers, or curly quotes from an LLM response, scoring will silently under-count keyword matches.

**Suggested fix:** Add `unicodedata.normalize("NFKD", value)` followed by ASCII encoding with `errors="ignore"` for invariant comparison contexts.

---

## Positive Observations

- `Evaluator.run_case` captures `started_at` / `completed_at` timestamps for each run — enables wall-clock trend analysis.
- The stochastic aggregation logic (`pass_rate >= suite_pass_threshold`) correctly handles the run-count denominator and avoids division by zero with `if run_count else 0.0`.
- `@lru_cache(maxsize=1)` on `_load_sentence_model` correctly ensures the embedding model is loaded once per process.
- `semantic_similarity_score` gracefully degrades to token-overlap when `sentence_transformers` is not installed — evals work without the optional ML dependency.
- `scorecase_output` handles the scorer dispatch in a single flat function with no dynamic attribute lookup — easy to trace and test.
- All Cypher queries in `persist_report_summary` use parameterised values — no injection risk.
- `_excerpt` collapses whitespace before truncating — prevents misleading excerpts with embedded newlines.

---

## Verdict

**Approve with comments.** No security or correctness critical issues. The medium findings (eval hang, sequential execution) should be addressed before running evals in CI at scale; the low findings are maintenance improvements.

| # | Severity | Location | Finding |
|---|----------|----------|---------|
| 1 | Medium | `evaluator.run_case` | No timeout on live runner — evals can hang indefinitely |
| 2 | Medium | `evaluator.run_suite/run_report` | Fully sequential execution — slow at scale |
| 3 | Low | All `_FIXTURE_OUTPUTS` dicts | Missing key causes unguarded `KeyError` |
| 4 | Low | `scorers.regex_score` | Arbitrary regex — potential ReDoS from config files |
| 5 | Low | `fixtures.load_code_fixtures` | `runpy.run_path` executes fixture file with side-effects |
| 6 | Low | `fixtures._repo_root` | Fragile `parents[3]` — breaks on repo restructure |
| 7 | Low | All suite definitions | `0.67` / `3` are unexplained magic numbers |
| 8 | Info | `evaluator.persist_report_summary` | `conn: Any` loses static type checking |
| 9 | Info | `scorers._normalize_text` | No Unicode normalisation |
