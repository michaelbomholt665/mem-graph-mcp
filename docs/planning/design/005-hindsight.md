# Design: Hindsight Integration (Long-term Memory with Ladybug/Kuzu)

**Status:** Design Phase  
**Priority:** High (Core to agent learning)  
**Date:** 2026-04-13

---

## Overview

Hindsight is a persistent memory engine that connects agents to Ladybug (Kuzu). When agents complete tasks, Hindsight automatically extracts "facts" and "patterns" and stores them as graph nodes. Over time, agents "grow" with institutional knowledge.

This design ensures that:
1. **Facts are extracted automatically:** No manual memory management
2. **Patterns are learned:** Recurring solutions are captured
3. **Context is preserved:** Decisions include rationale
4. **Memory evolves:** Knowledge graph grows with usage

---

## Goals

1. **Automate Knowledge Extraction:** Agents don't consciously "save" to memory—Hindsight handles it
2. **Support Cross-Session Learning:** Agents use prior facts to inform new decisions
3. **Enable Pattern Recognition:** Recurring patterns are surfaced to users and agents
4. **Maintain Memory Quality:** Deduplication and confidence scoring prevent noise

---

## Scope

### In Scope
- Integrate Hindsight tools into all Core Five agents
- Define extraction rules (what counts as a "fact" or "pattern")
- Create Hindsight tools for memory recall + storage
- Build pattern detector that runs after task completion
- Implement memory decay (confidence scores lower over time)
- Create memory analytics dashboard (count facts, patterns, decay)

### Out of Scope
- Changing agent reasoning logic
- Creating a "memory agent" (Hindsight is automatic, not agentic)
- Manual fact curation (automation is key)

---

## Architecture

### 1. Hindsight Tool Integration

Hindsight provides tools that agents can use in two ways:

**Implicit (Automatic):**
```python
# At task end, Hindsight automatically extracts facts

# Example task: "Fix null pointer bug in parser"
# Hindsight extracts:
#   Fact: "Go parser null checks should use if x == nil pattern"
#   Fact: "Bug was caused by missing guard clause"
#   Pattern: "Parser errors often stem from missing nil checks"
```

**Explicit (Agent-Driven):**
```python
# Agent calls hindsight tools during execution

from hindsight_pydantic_ai import recall_facts, store_fact

# Recall facts related to current task
similar_fixes = await recall_facts(
    query="Go parser null checks",
    limit=3,
)

# Store a specific fact if it's important
await store_fact(
    content="Parser guard clauses must check both nil and length",
    tags=["pattern", "go", "safety"],
    confidence=0.95,
)
```

### 2. Hindsight Integration (Factory Pattern)

Add Hindsight at agent instantiation in the factory (`src/mem_graph/agents/__init__.py`):

```python
# src/mem_graph/agents/__init__.py

from hindsight_pydantic_ai import create_hindsight_tools
from .audit.audit_agent import create_audit_agent

class AgentFactory:
    """Factory wraps agents with Hindsight + Planning."""
    
    def __init__(self, graph_client: GraphClient, project_id: str):
        self.graph = graph_client
        self.project_id = project_id
        # Create once, shared across agents
        self.hindsight_tools = create_hindsight_tools(
            bank_id="mem-graph",
            default_tags=[f"project:{project_id}"],
        )
    
    async def audit_agent(self, tier: ModelTier = ModelTier.STANDARD) -> Agent:
        """Audit agent with Hindsight memory tools."""
        agent = create_audit_agent(tier)
        
        # Add Hindsight (all agents get memory)
        agent.tools.extend(self.hindsight_tools)
        
        # Wrap with planning for EXPERT tier
        if tier == ModelTier.EXPERT:
            agent = PlanningAgent(agent, self.graph, self.project_id, tier)
        
        return agent
```

**Pattern:** Agents are created in `/agents/{category}/{agent_name}.py`, factory wraps with Hindsight + Planning at instantiation.
```

### 3. Extraction Rules

Define what counts as a "fact" or "pattern":

```python
# src/mem_graph/memory/hindsight_rules.py

from dataclasses import dataclass
from typing import Callable

@dataclass
class ExtractionRule:
    """Rules for extracting facts from agent outputs."""
    name: str
    pattern: str  # Regex or semantic pattern
    fact_template: str  # Template for derived fact
    tags: list[str]
    confidence: float

# Rules for Fix agent
FIX_AGENT_RULES = [
    ExtractionRule(
        name="nil_check_pattern",
        pattern=r"nil check|nil guard|if .* == nil",
        fact_template="Go guard clause for {code_pattern}: {approach}",
        tags=["pattern", "go", "safety"],
        confidence=0.85,
    ),
    ExtractionRule(
        name="performance_fix",
        pattern=r"optimized|faster|performance|reduce.*allocation",
        fact_template="Performance optimization: {approach}",
        tags=["performance", "{language}"],
        confidence=0.80,
    ),
    ExtractionRule(
        name="style_fix",
        pattern=r"style|naming|convention|readable",
        fact_template="Style recommendation: {approach}",
        tags=["style", "{language}"],
        confidence=0.75,
    ),
]

# Rules for Audit agent
AUDIT_AGENT_RULES = [
    ExtractionRule(
        name="code_smell",
        pattern=r"duplicate code|god function|tight coupling|missing test",
        fact_template="Code smell: {smell_type} - {recommendation}",
        tags=["smell", "refactoring"],
        confidence=0.90,
    ),
    ExtractionRule(
        name="security_issue",
        pattern=r"security|injection|overflow|leak|vulnerability",
        fact_template="Security issue: {issue_type}",
        tags=["security", "critical"],
        confidence=0.95,
    ),
]

class FactExtractor:
    """Extract facts from agent outputs using rules."""
    
    def __init__(self, rules: list[ExtractionRule]):
        self.rules = rules
    
    async def extract(self, agent_output: str) -> list[dict]:
        """
        Extract facts from agent output.
        
        Returns list of dicts with keys:
          - content: The fact text
          - tags: List of tags
          - confidence: Confidence score (0-1)
        """
        facts = []
        
        for rule in self.rules:
            if re.search(rule.pattern, agent_output, re.IGNORECASE):
                # Pattern matched—extract fact
                fact = {
                    "content": rule.fact_template.format(
                        code_pattern="...",  # Parse from output
                        approach="...",      # Parse from output
                    ),
                    "tags": rule.tags,
                    "confidence": rule.confidence,
                }
                facts.append(fact)
        
        return facts
```

### 4. Memory Recall in Agents

Agents use Hindsight to recall facts:

```python
# Example: Fix agent recalls similar fixes before proposing changes

async def generate_patches(self, context: RunContext, state: AutopilotState) -> dict:
    """Generate code patches, informed by past fixes."""
    
    # Recall similar fixes from memory
    similar_facts = await self.hindsight.recall_facts(
        query=f"fix {state.language} {state.context_map}",
        limit=5,
    )
    
    # Include facts in prompt context
    context_text = "Similar fixes from prior runs:\n"
    for fact in similar_facts:
        context_text += f"- {fact.content} (confidence: {fact.confidence})\n"
    
    # Generate patches with historical context
    patches = await self.agent.run(
        f"Generate patches for: {state.file_contents}\n\n{context_text}"
    )
    
    return patches
```

### 5. Memory Decay

Older facts lose confidence over time:

```python
# src/mem_graph/memory/decay.py

from datetime import datetime, timedelta

def apply_decay(fact: FactNode, days_old: int, decay_rate: float = 0.05) -> FactNode:
    """
    Apply time-based decay to fact confidence.
    
    After 30 days of no verification, confidence drops by 30%.
    
    Example:
      fact.confidence = 0.90
      days_old = 30
      new_confidence = 0.90 * (1 - 0.05 * 30) = 0.90 * 0.85 = 0.765
    """
    
    if days_old == 0:
        return fact  # Fresh fact
    
    decayed_confidence = fact.confidence * max(0, 1 - decay_rate * min(days_old, 30))
    
    fact.confidence = decayed_confidence
    return fact

async def refresh_fact_confidence(fact_id: str, new_confidence: float) -> None:
    """
    Bump confidence when fact is re-verified.
    
    Called when an agent uses a recalled fact and it works.
    """
    
    fact = await graph.get_fact(fact_id)
    fact.confidence = min(1.0, fact.confidence + 0.05)  # +5% on verification
    fact.last_verified = datetime.now()
    await graph.update_fact(fact)
```

### 6. Pattern Detection

Identify recurring patterns after multiple similar fixes:

```python
# src/mem_graph/memory/pattern_detector.py

class PatternDetector:
    """Identify recurring patterns from facts."""
    
    async def detect_patterns(self) -> list[PatternNode]:
        """
        Run after each agent run.
        
        Looks for:
        - Same issue appearing in multiple files
        - Same fix applied multiple times
        - Style preference consistency
        """
        
        # Find facts with similar content/tags in past week
        recent_facts = await self.graph.query("""
            MATCH (f:Fact)
            WHERE f.created_at > datetime() - duration("P7D")
            RETURN f
            ORDER BY f.created_at DESC
            LIMIT 50
        """)
        
        # Cluster similar facts
        clusters = await self._cluster_facts(recent_facts)
        
        patterns = []
        for cluster in clusters:
            if len(cluster) >= 3:  # Pattern needs ≥3 instances
                pattern = PatternNode(
                    name=f"Recurring: {cluster[0].tags}",
                    facts=cluster,
                    confidence=min([f.confidence for f in cluster]),
                )
                patterns.append(pattern)
        
        return patterns
```

### 7. Graph Schema

```cypher
# Extend graph with Hindsight nodes

CREATE (:FactBank {
  bank_id: "mem-graph",
  created_at: datetime(),
  stats: {
    total_facts: 0,
    avg_confidence: 0.0,
    decay_rate: 0.05,
  }
})

# Facts
CREATE (:Fact {
  fact_id: "...",
  content: "Go guard clause pattern",
  tags: ["pattern", "go", "safety"],
  confidence: 0.90,
  created_at: datetime(),
  last_verified: datetime(),
  source_agent: "fix_agent",
  source_project: "project-1",
})

# Patterns (derived from facts)
CREATE (:Pattern {
  pattern_id: "...",
  name: "Recurring: nil checks in parser",
  description: "Found in 5+ fix runs",
  confidence: 0.85,
  created_at: datetime(),
  instances: ["fact-1", "fact-2", "fact-3", ...],
})

# Relationships
(fact:Fact)-[:IN_BANK]->(bank:FactBank)
(pattern:Pattern)-[:DERIVED_FROM]->(fact:Fact)
(fact:Fact)-[:TAGGED_AS]->(tag:Tag {name: "pattern"})
```

---

## Benefits

1. **No Manual Memory Management:** Hindsight handles extraction
2. **Cross-Session Learning:** Agents use facts from prior runs
3. **Pattern Recognition:** Recurring solutions surface
4. **Quality Improvement:** Agents run faster with memory (less exploration)
5. **Auditability:** All facts are timestamped and traceable

---

## Implementation Order

1. Create Hindsight rule definitions (extraction rules)
2. Integrate Hindsight tools into Core Five agents
3. Implement fact extraction at task completion
4. Add fact recall to agent prompts
5. Implement pattern detection
6. Add memory decay logic
7. Create memory analytics dashboard

---

## Implementation Checklist

- [ ] Define extraction rules for each agent (audit/, fix/, validate/, map/, document/)
- [ ] Update `src/mem_graph/agents/__init__.py` factory to add Hindsight tools
- [ ] Integrate Hindsight tools into agent instantiation (one factory method)
- [ ] Implement fact extraction at task end
- [ ] Add fact recall to agent decision-making
- [ ] Implement pattern detector
- [ ] Add memory decay to fact recall
- [ ] Create pattern refresh on verification
- [ ] Extend graph schema with Fact, Pattern nodes
- [ ] Test fact extraction for one agent
- [ ] Test fact recall improves decision quality
- [ ] Add memory analytics (fact count, confidence, patterns)

---

## Success Criteria

1. Facts are automatically extracted from agent outputs
2. Agents recall relevant facts during task execution
3. Patterns are identified after sufficient instances
4. Memory improves agent decision speed over time
5. Memory quality remains high (low noise via confidence scoring)
6. No regression in agent correctness

---

## Dependencies

- `hindsight-pydantic-ai>=0.4.19` (already in `pyproject.toml`)
- `real-ladybug>=0.15.3` (already in `pyproject.toml`) for graph storage
- Pydantic for fact + pattern validation
- Graph client (already exists)

---

## Notes

- Hindsight is "lazy"—facts are extracted automatically, not requested
- Confidence scores prevent bad facts from dominating decisions
- Decay ensures old facts gradually lose influence (no stale knowledge)
- Pattern detection is an opt-in, post-task analysis (doesn't block execution)
