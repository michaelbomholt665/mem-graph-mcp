# Code Review — `src/mem_graph/evals/`

**Reviewer:** GitHub Copilot  
**Package:** `src/mem_graph/evals/`
**Files reviewed:**
- `__init__.py`
- `audit_evals.py`
- `document_evals.py`
- `evaluator.py`
- `fixtures.py`
- `fix_evals.py`
- `logfire_client.py`
- `map_evals.py`
- `scorers.py`
- `validate_evals.py`

---

## Summary

The eval harness is clean and easy to follow: suite definitions are readable, the runner model is simple, and the hosted-dataset path mirrors the fixture path well. The biggest operational risk is that live evals can hang indefinitely because case execution has no timeout. The next tier is mostly reliability debt: sequential execution, fragile fixture lookups, and helpers that silently execute or assume repository-local files.

---

## Issues

### 1. Live eval case execution has no timeout — MEDIUM

**Location:** `evaluator.py:94-100`

`Evaluator.run_case()` awaits `runner(case)` directly. If a live agent run stalls on model I/O, retries, or a dependency deadlock, the entire eval run blocks until something external kills it.

**Suggested fix:** Wrap the awaited runner in a timeout, ideally configurable per case or suite.

---

### 2. Suite and report execution are fully sequential — MEDIUM

**Location:** `evaluator.py:174-184`, `evaluator.py:227-234`

Cases within a suite and suites within a report are processed strictly one after another. That keeps the implementation simple, but it scales poorly once live evals involve multiple remote model calls.

This is not wrong for tiny fixture runs, but it becomes an avoidable throughput bottleneck in CI or release gates.

**Suggested fix:** Add bounded concurrency at the suite and/or case level.

---

### 3. Fixture-backed runners and metadata access fail with raw `KeyError`s — LOW

**Location:**  
- `audit_evals.py:114-126, 141-149`  
- `document_evals.py:121-147`  
- `fix_evals.py:93-107, 121-130`  
- `map_evals.py:104-116`  
- `validate_evals.py:88-100, 115-123`

The suite modules index `_FIXTURE_OUTPUTS[...]`, `_CODE_FIXTURES[...]`, `_VIOLATION_FIXTURES[...]`, and `case.metadata[...]` directly. If a case is renamed or a fixture entry is missed, the suite crashes with an undecorated `KeyError` instead of a clear eval failure.

**Suggested fix:** Validate fixture completeness at import time or raise explicit errors with the missing case/fixture key.

---

### 4. `fixtures.py` executes a Python fixture file at import time — LOW

**Location:** `fixtures.py:16-25`

`load_code_fixtures()` uses `runpy.run_path()` to execute `tests/fixtures/sample_code.py`. That means any top-level side effects in the fixture file run inside the eval process.

Because the fixture is repo-controlled this is not a direct security issue, but it is a non-obvious coupling and makes the loader less predictable than a pure data read.

**Suggested fix:** Prefer a data-only format or extract top-level constants through a safer parser.

---

### 5. Repository root discovery is brittle — LOW

**Location:** `fixtures.py:12-13`, `logfire_client.py:25-26`

Both modules derive the repo root with `Path(__file__).resolve().parents[3]`. That works in the current layout, but it will silently break if the package is moved in a monorepo or restructured.

**Suggested fix:** Verify the derived root contains an expected sentinel such as `pyproject.toml`, or centralize repo-root discovery in one helper.

---

### 6. `regex_score()` accepts arbitrary patterns with no validation — LOW

**Location:** `scorers.py:51-55`

The regex scorer feeds `pattern` directly to `re.search()`. Today the patterns are developer-authored, but malformed or catastrophically backtracking patterns still turn into runtime surprises.

**Suggested fix:** Pre-compile patterns when suites are defined and fail fast on invalid regexes.

---

### 7. `run_fix_eval()` uses filename heuristics to recover missing case IDs — LOW

**Location:** `fix_evals.py:171-176`

The hosted fixer path derives `case_id` from the filename and then falls back to `"fix-hardcoded-secret"` or `"fix-bare-except"` based on whether `"payment"` appears in the path. That is clever, but it is also easy to break if fixture names change.

**Suggested fix:** Carry the eval case ID explicitly in the hosted input or metadata instead of reverse-engineering it from the file path.

---

## Positive Observations

- The split between fixture-mode and live-mode bindings is consistent across all suites.
- `Evaluator.run_case()` records per-run timing, pass/fail state, output, and failure details, which is useful for trend analysis.
- Hosted dataset support is separated cleanly into `logfire_client.py` and per-suite dataset builders.
- The semantic scorer has a graceful fallback path when `sentence_transformers` is unavailable.

---

## Verdict

**Approve with comments.** The eval harness is structurally solid, but I would add timeout protection and improve fixture validation before leaning on it as a hard CI gate.
