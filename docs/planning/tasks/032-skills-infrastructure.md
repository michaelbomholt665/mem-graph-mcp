# Task 032: Skills Infrastructure — Code-Based Domain Knowledge Bundles

**Status:** Planning
**Priority:** Medium
**Blocked by:** Task 029 (Base Agent Architecture), Task 031 (Prompt System)
**Blocks:** Task 036 (Evaluations)
**Complexity:** MEDIUM

## Problem Statement

Skills are currently read-only SKILL.md files passed as raw strings. The interface `skills_content: str` is stable, but there's no structured way to manage domain-knowledge bundles, trigger skills based on language/intent, or evaluate skill effectiveness independently.

The goal is to establish a code-based skill system where:
1. **Skills are structured objects** (`SkillBundle` dataclass) with prompt fragments, audit rules, and metadata.
2. **Named skills live in `providers/skills/`** alongside personas and prompts.
3. **Skills are discoverable and composable** via `load_skill(name)` and `skills_match(language, intent)`.
4. **Skills have their own eval suite** measuring precision/recall of findings.
5. **Skill resolution is explicit** in agent calls, not magic imports.

## Goals

1. **Define SkillBundle structure:** Prompt fragment, audit rules, tool allowlist, language/intent triggers.
2. **Create skill library:** Move four existing audit rule sets + create new domain-specific skills.
3. **Implement skill loader:** `load_skill(name) → SkillBundle`; `skills_match(language, intent) → SkillBundle`.
4. **Integrate with agents:** Update all agent calls to use `load_skill()` instead of raw strings.
5. **Add skill evals:** Create isolated test suites measuring each skill's performance.
6. **Document skill authoring:** Guide for creating new skills with testable claims.

## Non-Goals

- Building a visual skill builder UI.
- Dynamic skill generation (that's GEPA in Task 026).
- Skill versioning (future enhancement).

## Current State

### Raw String Interface (Current)

All agents receive `skills_content: str`:
```python
@dataclass
class AuditDependencies:
    skills_content: str = ""  # raw markdown string from caller
```

Caller reads a file:
```python
async def audit_package(package_path: str) -> dict:
    skills_content = (
        Path("skillz/python_quality.md").read_text()  # raw file read
    )
    deps = AuditDependencies(
        package_path=package_path,
        skills_content=skills_content,
    )
    result = await audit_agent.run(deps=deps)
```

### Audit Rule Sets (Proto-Skill, Implicit)

Four rule sets in `agents/audit/rules/`:
- `DEFAULT_RULES`
- `SECURITY_RULES`
- `BUG_RULES`
- `SMELL_RULES`

**Issues:**
- Implicit; no enum or registry mapping them.
- Mixed with agent code; hard to reuse.
- No metadata (language, domain, confidence).

### Missing Infrastructure

- No `SkillBundle` class.
- No named skill registry.
- No matcher (language + intent → skill).
- No way to discover available skills.

## Target Files

### New Files

```
src/mem_graph/providers/skills/__init__.py
  - Export SkillBundle, SkillRegistry, load_skill(), skills_match()

src/mem_graph/providers/skills/base.py
  - Define SkillBundle dataclass

src/mem_graph/providers/skills/registry.py
  - Define SkillRegistry class
  - Define load_skill() and skills_match() functions

src/mem_graph/providers/skills/python_quality.py
  - Python-specific audit rules + prompt fragment
  - SkillBundle: python_quality

src/mem_graph/providers/skills/security.py
  - Cross-language security rules + prompt fragment
  - SkillBundle: security

src/mem_graph/providers/skills/go_quality.py
  - Go-specific naming conventions + rules
  - SkillBundle: go_quality

src/mem_graph/providers/skills/typescript_quality.py
  - TypeScript-specific patterns + rules
  - SkillBundle: typescript_quality

src/mem_graph/providers/skills/documentation.py
  - Documentation best practices
  - SkillBundle: documentation

src/mem_graph/providers/skills/performance.py
  - Performance optimization patterns
  - SkillBundle: performance

evals/suites/skill_evals.py
  - Test suites for each skill
  - Measure precision, recall, coverage

docs/planning/design/skills/skill-authoring-guide.md
  - Template for creating new skills
  - Testing checklist
```

### Modifications

```
src/mem_graph/agents/audit/audit_agent.py
  - Update call pattern to use load_skill()

src/mem_graph/agents/audit/factory.py
  - Convert rule sets to SkillBundle objects
  - Update build_audit_agent_bundle() to use registry

src/mem_graph/agents/audit/rule_injector_agent.py
  - No changes; rule_injector already curates rules

src/mem_graph/tools/agents/audit.py
  - Update to use load_skill() in tool implementations

tests/test_skills.py
  - Add tests for SkillBundle, loader, matcher
```

## Implementation Phases

### Phase 1: Define SkillBundle and Registry (Sprint 1)

**Create `base.py`:**
[x] Define `SkillBundle` dataclass:
  ```python
  from dataclasses import dataclass, field
  from typing import Literal

  @dataclass
  class SkillBundle:
      """A bundle of domain expertise that activates for specific tasks."""
      name: str
      description: str
      prompt_fragment: str
      audit_rules: list[AuditRule] = field(default_factory=list)
      tool_allowlist: list[str] = field(default_factory=list)
      languages: list[str] = field(default_factory=list)  # ["python"], ["go"], ["any"]
      intents: list[str] = field(default_factory=list)  # ["audit"], ["fix"], ["any"]
      confidence: Literal["high", "medium", "low"] = "medium"
      metadata: dict = field(default_factory=dict)

      def to_prompt_fragment(self) -> str:
          """Get the prompt fragment for injection."""
          return self.prompt_fragment

      def matches(self, language: str, intent: str) -> float:
          """Return match score (0.0 to 1.0) for this language/intent."""
          lang_match = 1.0 if "any" in self.languages or language in self.languages else 0.5
          intent_match = 1.0 if "any" in self.intents or intent in self.intents else 0.5
          confidence_mult = {"high": 1.0, "medium": 0.8, "low": 0.6}[self.confidence]
          return (lang_match + intent_match) / 2.0 * confidence_mult
  ```

[x] Create `registry.py`:
  ```python
  from .base import SkillBundle

  class SkillRegistry:
      def __init__(self):
          self.skills: dict[str, SkillBundle] = {}

      def register(self, skill: SkillBundle) -> None:
          self.skills[skill.name] = skill

      def get(self, name: str) -> SkillBundle:
          if name not in self.skills:
              raise ValueError(f"Skill {name} not found")
          return self.skills[name]

      def list_all(self) -> list[str]:
          return list(self.skills.keys())

      def filter(self, language: str, intent: str) -> list[tuple[SkillBundle, float]]:
          """Return skills matching language/intent, sorted by match score."""
          matches = []
          for skill in self.skills.values():
              score = skill.matches(language, intent)
              if score > 0.0:
                  matches.append((skill, score))
          return sorted(matches, key=lambda x: x[1], reverse=True)

  SKILL_REGISTRY = SkillRegistry()

  def load_skill(name: str) -> SkillBundle:
      return SKILL_REGISTRY.get(name)

  def skills_match(language: str, intent: str) -> SkillBundle | None:
      """Return the best-matching skill for language/intent."""
      matches = SKILL_REGISTRY.filter(language, intent)
      return matches[0][0] if matches else None
  ```

### Phase 2: Migrate Audit Rules to Skills (Sprint 1–2)

**Convert rule sets to SkillBundle objects:**
[x] Create `python_quality.py`:
  ```python
  from .base import SkillBundle
  from src.mem_graph.models.audit import AuditRule, FindingCategory, Severity

  PYTHON_QUALITY_RULES = [
      AuditRule(
          rule_id="PY001",
          category=FindingCategory.STYLE,
          severity=Severity.MEDIUM,
          description="Use list comprehensions instead of map/filter.",
          examples=["❌ list(map(int, strings))", "✓ [int(s) for s in strings]"],
      ),
      # ... more rules
  ]

  python_quality = SkillBundle(
      name="python_quality",
      description="Python-specific code quality rules: naming, idioms, comprehensions.",
      prompt_fragment="""
      ## Python Quality Standards
      Apply these Python-specific rules:
      - Prefer list comprehensions over map/filter
      - Use snake_case for functions and variables
      - Use SCREAMING_SNAKE_CASE for module-level constants
      - ...
      """,
      audit_rules=PYTHON_QUALITY_RULES,
      languages=["python"],
      intents=["audit", "fix"],
      confidence="high",
  )
  ```

[x] Create `security.py`:
  ```python
  security = SkillBundle(
      name="security",
      description="Cross-language security rules: SQL injection, XSS, credential exposure.",
      prompt_fragment="""
      ## Security Audit Focus
      - Detect hardcoded credentials (API keys, passwords, tokens)
      - Flag SQL injection vectors (unparameterised queries)
      - Identify XSS vulnerabilities (unescaped user input)
      - Check for insecure deserialization
      - Verify TLS/SSL usage
      """,
      audit_rules=SECURITY_RULES,
      languages=["any"],
      intents=["audit", "security_hardening"],
      confidence="high",
  )
  ```

[x] Create `go_quality.py`, `typescript_quality.py`.

[x] Update `agents/audit/factory.py`:
  ```python
  async def build_audit_agent_bundle(rule_set: str = "default") -> AuditBundle:
      skill_name = {
          "default": "python_quality",
          "security": "security",
          "bug": "bug_detection",
          "smell": "code_smell",
      }.get(rule_set, "python_quality")

      skill = load_skill(skill_name)

      return AuditBundle(
          rules=skill.audit_rules,
          skills_content=skill.prompt_fragment,
      )
  ```

[x] Register all skills on module load:
  ```python
  # src/mem_graph/providers/skills/__init__.py
  from .base import SkillBundle
  from .registry import SkillRegistry, load_skill, skills_match, SKILL_REGISTRY
  from .python_quality import python_quality
  from .security import security
  from .go_quality import go_quality
  from .typescript_quality import typescript_quality

  SKILL_REGISTRY.register(python_quality)
  SKILL_REGISTRY.register(security)
  SKILL_REGISTRY.register(go_quality)
  SKILL_REGISTRY.register(typescript_quality)

  __all__ = ["SkillBundle", "SkillRegistry", "load_skill", "skills_match", "SKILL_REGISTRY"]
  ```

### Phase 3: Update Agent Call Patterns (Sprint 2)

**Update agent tools and callers:**
[x] Audit package tool:
  ```python
  @mcp.tool()
  async def audit_package(package_path: str, skill_name: str = "python_quality") -> dict:
      """Run a code audit on a package using the specified skill."""
      skill = load_skill(skill_name)

      deps = AuditDependencies(
          package_path=package_path,
          rules=skill.audit_rules,
          skills_content=skill.prompt_fragment,
      )

      result = await audit_agent.run(deps=deps)
      report = result.output

      await report_writer.write_audit_report(report, project_id=project_id)
      return report.model_dump(mode="json")
  ```

[x] Orchestrator agent:
  ```python
  async def orchestrator_agent.run(...):
      # Auto-select skill based on language
      language = deps.language or "python"
      intent = "audit"  # or from deps

      best_skill = skills_match(language, intent)
      deps.skills_content = best_skill.prompt_fragment if best_skill else ""

      # Continue with agent run
  ```

### Phase 4: Create Skill Evals (Sprint 2–3)

**Define skill test suites:**
[x] Create `evals/suites/skill_evals.py`:
  ```python
  from pydantic_evals import Evaluator, EvaluatorContext

  class SkillPrecisionRecallEval(Evaluator):
      """Measure precision and recall of a skill's audit findings."""

      async def evaluate(self, ctx: EvaluatorContext) -> EvaluationReason:
          # For a skill like python_quality:
          # - Run auditor on known-violation snippet
          # - Check that all expected violations are found (recall)
          # - Check that no false positives occur (precision)
          pass

  @dataclass
  class SkillEvalCase:
      skill_name: str
      code_snippet: str
      expected_violations: list[tuple[str, int]]  # (rule_id, count)
      should_find_all: bool = True

  # Test cases for python_quality skill
  PYTHON_QUALITY_CASES = [
      SkillEvalCase(
          skill_name="python_quality",
          code_snippet="""
          x = map(int, ["1", "2", "3"])  # Should trigger PY001
          """,
          expected_violations=[("PY001", 1)],
      ),
      SkillEvalCase(
          skill_name="python_quality",
          code_snippet="""
          result = [int(s) for s in ["1", "2", "3"]]  # Clean
          """,
          expected_violations=[],
      ),
      # ... more cases
  ]

  # Security skill test cases
  SECURITY_CASES = [
      SkillEvalCase(
          skill_name="security",
          code_snippet="""
          query = f"SELECT * FROM users WHERE id = {user_id}"  # SQL injection!
          """,
          expected_violations=[("SEC001", 1)],
      ),
      SkillEvalCase(
          skill_name="security",
          code_snippet="""
          query = "SELECT * FROM users WHERE id = ?"
          cursor.execute(query, (user_id,))  # Parameterised; safe
          """,
          expected_violations=[],
      ),
  ]
  ```

[x] Add fixture cases:
  ```python
  SKILL_FIXTURES = {
      "python_quality": PYTHON_QUALITY_CASES,
      "security": SECURITY_CASES,
      "go_quality": GO_QUALITY_CASES,
  }
  ```

[x] Create eval suite in test files:
  ```bash
  uv run mem-graph-evals skill_python_quality skill_security --mode fixture
  ```

### Phase 5: Documentation and Skill Authoring Guide (Sprint 3)

[x] Create `docs/planning/design/skills/skill-authoring-guide.md`:
  ```markdown
  # Skill Authoring Guide

  ## What Is a Skill?

  A skill is a bundle of domain expertise: rules, prompt guidance, and test cases. Skills activate based on language and intent.

  ## Anatomy of a Skill

  ```python
  @dataclass
  class MyNewSkill(SkillBundle):
      name = "my_new_skill"
      description = "Clear, one-line description"
      prompt_fragment = """
      ## Domain Knowledge
      When auditing this domain:
      - Key principle 1
      - Key principle 2
      """
      audit_rules = [
          AuditRule(
              rule_id="CUSTOM001",
              category=FindingCategory.BUG,
              severity=Severity.HIGH,
              description="Human-readable violation description",
              examples=["❌ Bad code", "✓ Good code"],
          ),
      ]
      languages = ["python"]  # or ["any"]
      intents = ["audit"]  # or ["audit", "fix"]
      confidence = "high"  # how much we trust this skill
  ```

  ## Testing Your Skill

  1. Write test cases in `evals/fixtures/skill_my_new_skill.json`
  2. Run: `uv run mem-graph-evals skill_my_new_skill --mode fixture`
  3. Target: 90%+ pass rate on fixture cases
  4. Then: Live test suite with hosted datasets
  ```

[x] Add checklist for new skills:
  [x] Skill name is unique and descriptive
  [x] Prompt fragment is clear and concise (< 300 words)
  [x] At least 5 audit rules with examples
  [x] Fixture test cases cover happy path + edge cases
  [x] Confidence score is honest (not all "high")
  [x] Skill is registered in `__init__.py`

## Acceptance Criteria

1. **SkillBundle defined:** Dataclass with prompt_fragment, audit_rules, languages, intents fields.
2. **SkillRegistry implemented:** `load_skill()` and `skills_match()` functions work.
3. **Six initial skills registered:** python_quality, security, go_quality, typescript_quality, documentation, performance.
4. **Agent call patterns updated:** `audit_agent`, orchestrator, and tools use `load_skill()` or `skills_match()`.
5. **Skill evals defined:** At least one eval case per skill; 80%+ fixture pass rate.
6. **Authoring guide complete:** Clear template and checklist for adding new skills.
7. **No regression:** Audit output unchanged after migration.

## Test Plan

```bash
# Test SkillBundle and registry
uv run pytest tests/resources/test_skills.py -q

# Test skill matching
uv run pytest tests/resources/test_skill_matcher.py -q

# Run skill evals
MEM_GRAPH_LOGFIRE_ENABLED=false OTEL_SDK_DISABLED=true \
  uv run mem-graph-evals skill_python_quality skill_security --mode fixture

# Regression on audit
MEM_GRAPH_LOGFIRE_ENABLED=false OTEL_SDK_DISABLED=true \
  uv run pytest tests/agents/test_audit_agent.py -q

# Broad gate
MEM_GRAPH_LOGFIRE_ENABLED=false OTEL_SDK_DISABLED=true \
  uv run pytest tests/ -q
```

## Dependencies

- Task 029 (Base Agent Architecture) — agent deps structure.
- Task 031 (Prompt System) — skills integrate as part of dynamic prompts.

## Notes

- Skills are designed to be independently testable; each skill has its own eval suite.
- Skill confidence scores should be validated empirically after deployment.
- Future: Dynamic skill generation via GEPA (Task 026) based on eval failures.
