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

The evals package implements a well-structured stochastic eval harness: `Evaluator` runs cases across multiple repetitions, aggregates scores, and persists compact summaries to the graph. The four scorer types (exact, keywords, regex, semantic) cover the common LLM eval scenarios. Per-agent suite files follow a clean fixture/live runner pattern.

No security-critical issues were found. The primary concerns are reliability (unbounded eval hang time, silent `KeyError` on missing fixtures) and performance (fully sequential suite execution).

---

## Issues

### 1. No timeout on `await runner(case)` in `Evaluator.run_case` — MEDIUM

**Location:** `evaluator.py` lines ~65–70

```python
output = await runner(case)
```

If a live eval runner stalls (e.g. an LLM API call hangs or the agent enters a retry loop), `run_case` blocks indefinitely. In CI this will cause the entire eval run to hang until the process is killed externally. There is no `asyncio.wait_for` guard.

**Suggested fix:**

```python
output = await asyncio.wait_for(runner(case), timeout=120.0)
```

Consider making the timeout configurable via `EvalCase.timeout_s` or a `run_case` parameter.

---

### 2. Suite and case execution are fully sequential — MEDIUM

**Location:** `evaluator.run_suite` (~lines 135–165), `evaluator.run_report` (~lines 167–195)

Both `run_suite` (over cases) and `run_report` (over suites) use `for … await` loops. For a 5-suite eval with 3 cases each and 3 runs per case, that is 45 sequential LLM calls. Independent suites and independent cases within a suite could be parallelised with `asyncio.gather`.

**Suggested fix:** For suites in `run_report`:

```python
suite_results = await asyncio.gather(
    *[self.run_suite(registry[name], ...) for name in suite_names]
)
```

Within `run_suite`, cases can also be gathered if a concurrency cap is applied (e.g. `asyncio.Semaphore`).

---

### 3. Missing fixture key causes unguarded `KeyError` in fixture runners — LOW

**Location:** All `_FIXTURE_OUTPUTS` dicts in each eval file, e.g. `audit_evals.py` line ~20

```python
async def _run_fixture(case: EvalCase) -> str:
    await asyncio.sleep(0)
    return _FIXTURE_OUTPUTS[case.case_id]  # KeyError if case_id is not in the dict
```

If a new `EvalCase` is added to a suite without adding the corresponding entry to `_FIXTURE_OUTPUTS`, the fixture runner crashes with an undecorated `KeyError` rather than a meaningful eval failure. Similarly, `load_code_fixtures()[fixture_key]` in live runners will raise a `KeyError` if the key is absent from `sample_code.py`.

**Suggested fix:**

```python
return _FIXTURE_OUTPUTS.get(case.case_id, f"[no fixture for {case.case_id}]")
```

Or assert completeness at module load time:

```python
assert all(case.case_id in _FIXTURE_OUTPUTS for case in AUDIT_EVAL_SUITE.cases), \
    "Missing fixture outputs"
```

---

### 4. `regex_score` accepts arbitrary patterns — potential ReDoS — LOW

**Location:** `scorers.py` lines ~48–52

```python
def regex_score(output: str, pattern: str) -> float:
    return 1.0 if re.search(pattern, output, re.IGNORECASE | re.MULTILINE) else 0.0
```

The `pattern` comes from `EvalCase.expected_pattern`, which is developer-controlled. However, since `EvalCase` can be constructed from external config files or YAML, a pathological pattern such as `(a+)+$` could cause catastrophic backtracking.

**Suggested fix:** Wrap with a try/except and add a short `re.compile` pre-check, or use Python's `re.error` to validate patterns at suite load time.

---

### 5. `fixtures.py` uses `runpy.run_path` to load code fixtures — LOW

**Location:** `fixtures.py` lines ~15–23

```python
namespace = runpy.run_path(
    str(_repo_root() / "tests" / "fixtures" / "sample_code.py")
)
```

`runpy.run_path` executes the file in the current process. Any top-level side effects in `sample_code.py` (imports that trigger code, print statements, file I/O) will run at eval startup. Since the file is developer-controlled this is a LOW risk, but it is a non-obvious dependency.

**Suggested fix:** Parse the file with `ast.literal_eval` on top-level assignments, or use an actual module import via `importlib`.

---

### 6. `_repo_root` is brittle — LOW

**Location:** `fixtures.py` lines ~12–13

```python
def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]
```

`parents[3]` hard-codes `evals/` being exactly three levels below the repository root. If the package is ever moved (e.g. into a monorepo sub-path), this silently returns the wrong directory rather than failing visibly. It also does not verify that the resolved path is actually the repo root (e.g. by checking for a `pyproject.toml`).

**Suggested fix:**

```python
def _repo_root() -> Path:
    root = Path(__file__).resolve().parents[3]
    assert (root / "pyproject.toml").exists(), f"Unexpected repo root: {root}"
    return root
```

---

### 7. `pass_threshold=0.67` and `default_runs=3` are unexplained magic numbers — LOW

**Location:** All five eval suite definitions

Every suite uses the same `pass_threshold=0.67` and `default_runs=3`. These values appear to be cargo-culted rather than deliberately chosen. There is no accompanying comment explaining why 67% is the right threshold or why 3 runs were chosen as the stochastic sample size.

**Suggested fix:** Define named constants in `evaluator.py` (or a dedicated `constants.py`):

```python
DEFAULT_PASS_THRESHOLD = 0.67  # Allow one miss in three runs
DEFAULT_RUNS = 3               # Minimum for reliable stochastic variance
```

---

### 8. `persist_report_summary` accepts `conn: Any` — INFO

**Location:** `evaluator.py` lines ~235–240

```python
def persist_report_summary(self, report: EvalReport, *, conn: Any, ...) -> str:
```

The `conn` parameter has type `Any`, abandoning static type checking. The function unconditionally calls `conn.execute(...)` with no isinstance guard. If the wrong connection object is passed, the error will be a confusing `AttributeError` at runtime.

**Suggested fix:** Type as `lb.Connection` (the Ladybug type used everywhere else) or extract to a protocol type.

---

### 9. `_normalize_text` does not handle Unicode — INFO

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
