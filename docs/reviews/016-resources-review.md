# Code Review — `src/mem_graph/resources/`

**Reviewer:** GitHub Copilot  
**Package:** `src/mem_graph/resources/`
**Files reviewed:**
- `architecture.py`
- `coding_standards.py`
- `personas.py`
- `prompts.py`

---

## Summary

This folder is prompt/config content rather than executable logic, so the main risks are contract drift and bad guidance rather than crashes. The most important issue is that some of the “guardrail” text conflicts with the repository’s actual conventions, which can push agents toward unnecessary churn. I also found a small but real ambiguity in persona naming.

---

## Issues

### 1. Several hard guardrails conflict with the repository’s actual conventions — MEDIUM

**Location:** `architecture.py:37-54`, `coding_standards.py:17-40`

The injected standards are written as mandatory universal rules:

- “ALL functions, methods, and public symbols MUST have 2 or 3 tokens”
- “Functions MUST be prefixed by their primary feature or manager name”
- “every .py file” must have a shebang, path header, and a fixed file-header layout

Those rules do not match the current codebase consistently. For example, the repository already contains many legitimate public symbols and modules that do not follow the 2–3 token naming rule, and many app-layer Python files do not carry the prescribed file header format.

Because these strings are injected into agent prompts as hard requirements, they can cause style-only churn and false-positive “violations” against existing repo code.

**Suggested fix:** Recast these as repository-specific preferences only where they are actually enforced, or narrow them to the agent families that truly depend on them.

---

### 2. Two distinct personas share the same display name, `Librarian` — LOW

**Location:** `personas.py:177-197`, `personas.py:291-313`

`RULE_INJECTOR_PERSONA` and `CHAT_PERSONA` both use `name="Librarian"`. Their roles are different, but the rendered system prompt begins with the persona name, so this creates avoidable ambiguity in logs, prompts, and debugging output.

**Suggested fix:** Give each persona a unique display name even if the underlying theme is similar.

---

### 3. Persona trait and LLM parameter containers accept out-of-range values without validation — LOW

**Location:** `personas.py:21-39`

`BigFiveTraits` and `LLMParams` are plain dataclasses with no bounds checking. Today the module constructs them with sane literals, but the types themselves would accept values like `temperature=-3`, `top_p=9`, or personality scores outside `0..1`.

That is mostly a future-proofing issue, especially if personas ever become configurable or generated.

**Suggested fix:** Add a validating constructor, switch to a small Pydantic model, or clamp values before use.

---

## Positive Observations

- The registries are simple and easy to consume from the rest of the app.
- `prompts.py` keeps workflow prompts centralized instead of scattering them across tools.
- The persona definitions are readable and make the intended agent behavior easy to inspect.

---

## Verdict

**Approve with comments.** The content is manageable, but I would align the injected “mandatory” rules with real repository practice before treating them as hard guardrails for autonomous agents.
