# Design: Phase 5b - Jina Code Embedder

**Status:** Design Phase  
**Priority:** Low-Medium (Advanced integration)  
**Date:** 2026-04-13

---

## Overview

Phase 5b adds semantic linking between Jina tickets and code. A "Jina Code Embedder" service uses embeddings to find code that "belongs" to a Jina ticket:

- **Input:** Jina issue (title + description)
- **Process:** Embed ticket description + code files, find semantic matches
- **Output:** Code references in graph as `MENTIONS` or `IMPLEMENTS` edges

This enables traceability: agents can see which code implements which ticket, and which tickets are affected by which violations.

---

## Goals

1. **Semantic Traceability:** Link Jina tickets to relevant code without manual mapping
2. **Bidirectional:** Agents know what code implements a decision (Jina ticket)
3. **Lazy Loading:** Embedder runs on-demand, doesn't block server startup
4. **VRAM Efficient:** Model is unloaded after use (TTL 5 min)

---

## Scope

### In Scope
- Implement Jina embedder service (embeddings + semantic search)
- Add Jina API integration to fetch tickets
- Create graph entities for Jina issues
- Implement lazy model loading (TTL-based unload)
- Build search tool: find code for a ticket
- Build reverse search: find tickets for code

### Out of Scope
- Two-way Jina sync (write back to Jina) - read-only for now
- Jina webhook handling (polling is sufficient)
- Figuring out which Jina project to use (user specifies in env)

---

## Architecture

### 1. Jina Code Embedder Service

```python
# src/mem_graph/services/jina_embedder.py

from datetime import datetime, timedelta
from typing import Optional
import httpx
from sentence_transformers import SentenceTransformer
from pydantic import BaseModel

class JinaIssue(BaseModel):
    """Jina issue from API."""
    key: str
    title: str
    description: str
    status: str  # "Open", "In Progress", "Done"
    assignee: str | None
    created_at: str
    url: str

class CodeMatch(BaseModel):
    """Match between code and Jina issue."""
    file_path: str
    score: float  # 0-1 semantic similarity
    context: str  # Code snippet

class JinaCodeEmbedder:
    """
    Embeds Jina issues and code together, finds semantic matches.
    
    Uses Ollama with jinaai embeddings for efficient inference.
    Model is loaded lazily and unloaded after TTL expires.
    """
    
    MODEL_NAME = "hf.co/jinaai/jina-embeddings-v4-text-code-GGUF:Q5_K_M"
    UNLOAD_AFTER_MINUTES = 5
    
    def __init__(self, jina_url: str, jina_token: str):
        self.jina_url = jina_url
        self.jina_token = jina_token
        self.model: Optional[SentenceTransformer] = None
        self._model_loaded_at: Optional[datetime] = None
    
    async def _ensure_model_loaded(self) -> SentenceTransformer:
        """Load model if not already loaded (lazy loading)."""
        
        # Check if model has expired
        if self.model and self._model_loaded_at:
            age = datetime.now() - self._model_loaded_at
            if age > timedelta(minutes=self.UNLOAD_AFTER_MINUTES):
                logger.info(f"Unloading embedder model (expired after {age.total_seconds():.0f}s)")
                del self.model
                self.model = None
        
        # Load if needed
        if not self.model:
            logger.info(f"Loading embedder model {self.MODEL_NAME}")
            # Use Ollama for efficient inference
            self.model = SentenceTransformer(
                self.MODEL_NAME,
                model_kwargs={"trust_remote_code": True},
                cache_folder="/path/to/cache",  # Persist downloaded model
            )
            self._model_loaded_at = datetime.now()
        
        return self.model
    
    async def fetch_jina_issues(self, jql: str = "project = PROJ") -> list[JinaIssue]:
        """Fetch issues from Jina."""
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.jina_url}/rest/api/3/search",
                params={"jql": jql, "maxResults": 100},
                headers={"Authorization": f"Bearer {self.jina_token}"},
            )
            response.raise_for_status()
            
            issues = []
            for issue in response.json()["issues"]:
                issues.append(JinaIssue(
                    key=issue["key"],
                    title=issue["fields"]["summary"],
                    description=issue["fields"]["description"] or "",
                    status=issue["fields"]["status"]["name"],
                    assignee=issue["fields"].get("assignee", {}).get("displayName"),
                    created_at=issue["fields"]["created"],
                    url=f"{self.jina_url}/browse/{issue['key']}",
                ))
            
            return issues
    
    async def find_code_for_issue(
        self,
        issue: JinaIssue,
        code_files: list[tuple[str, str]],  # [(file_path, content), ...]
        threshold: float = 0.7,
    ) -> list[CodeMatch]:
        """
        Find code files related to a Jina issue.
        
        Uses semantic similarity to match issue description to code.
        """
        
        model = await self._ensure_model_loaded()
        
        # Embed issue
        issue_text = f"{issue.title}\n{issue.description}"
        issue_embedding = model.encode(issue_text)
        
        matches = []
        
        for file_path, content in code_files:
            # Embed code file
            code_embedding = model.encode(content[:512])  # Limit to 512 chars per file
            
            # Calculate similarity
            similarity = float((issue_embedding @ code_embedding) / (
                (issue_embedding ** 2).sum() ** 0.5 * (code_embedding ** 2).sum() ** 0.5
            ))
            
            if similarity > threshold:
                # Extract relevant snippet
                snippet = self._find_relevant_snippet(issue_text, content)
                
                matches.append(CodeMatch(
                    file_path=file_path,
                    score=similarity,
                    context=snippet,
                ))
        
        # Sort by score
        return sorted(matches, key=lambda m: m.score, reverse=True)
    
    def _find_relevant_snippet(self, issue_text: str, code: str, context_lines: int = 3) -> str:
        """Extract code snippet relevant to issue."""
        
        # Simple approach: find lines containing issue keywords
        issue_keywords = set(issue_text.lower().split())
        lines = code.split('\n')
        
        for i, line in enumerate(lines):
            if any(keyword in line.lower() for keyword in issue_keywords):
                start = max(0, i - context_lines)
                end = min(len(lines), i + context_lines + 1)
                return '\n'.join(lines[start:end])
        
        # Fallback: return first 5 lines
        return '\n'.join(lines[:5])

# Global instance
jina_embedder: Optional[JinaCodeEmbedder] = None

def get_jina_embedder() -> JinaCodeEmbedder:
    """Get or create embedder."""
    global jina_embedder
    
    if not jina_embedder:
        jina_url = os.getenv("JINA_URL", "https://jina.example.com")
        jina_token = os.getenv("JINA_TOKEN", "")
        
        jina_embedder = JinaCodeEmbedder(jina_url, jina_token)
    
    return jina_embedder
```

### 2. Graph Integration

Store Jina issues and code matches in graph:

```python
# Cypher schema extensions

CREATE (:JinaIssue {
  issue_key: "PROJ-123",
  title: "Fix null pointer bug in parser",
  description: "...",
  status: "Open",
  url: "https://jina.example.com/browse/PROJ-123",
  created_at: datetime(),
})

(jina:JinaIssue)-[:MENTIONS]->(file:File)  # Jina issue mentions this code file
(violation:Violation)-[:RESOLVES]->(jina:JinaIssue)  # Fix resolves this ticket
(decision:Decision)-[:IMPLEMENTS]->(jina:JinaIssue)  # Decision is about this ticket
```

### 3. Tools for Jina Integration

```python
# src/mem_graph/tools/integrations/jina.py

from ..services.jina_embedder import get_jina_embedder

@mcp.tool()
async def fetch_jina_issues(
    jql: str = "project = MEM",
    limit: int = 50,
) -> dict:
    """
    Fetch Jina issues and link to code.
    
    Args:
        jql: JQL query (e.g., "assignee = currentUser()")
        limit: Max issues to fetch
    
    Returns:
        List of issues with related code files
    """
    
    embedder = get_jina_embedder()
    issues = await embedder.fetch_jina_issues(jql)
    
    # Enumerate code files
    code_files = await enumerate_code_files()
    
    results = []
    
    for issue in issues[:limit]:
        # Find matching code
        matches = await embedder.find_code_for_issue(issue, code_files, threshold=0.7)
        
        # Store in graph
        await store_jina_issue_to_graph(issue)
        
        for match in matches:
            await store_jina_code_mention(issue.key, match.file_path, match.score)
        
        results.append({
            "key": issue.key,
            "title": issue.title,
            "status": issue.status,
            "matched_files": [
                {"path": m.file_path, "score": m.score}
                for m in matches
            ],
        })
    
    return {"issues": results, "total": len(issues)}

@mcp.tool()
async def find_code_for_ticket(ticket_key: str) -> dict:
    """Find code that implements a specific Jina ticket."""
    
    # Get issue from Jina
    embedder = get_jina_embedder()
    issues = await embedder.fetch_jina_issues(f"key = {ticket_key}")
    
    if not issues:
        return {"error": f"Ticket {ticket_key} not found"}
    
    issue = issues[0]
    code_files = await enumerate_code_files()
    
    # Find matching code
    matches = await embedder.find_code_for_issue(issue, code_files, threshold=0.6)
    
    return {
        "ticket": ticket_key,
        "title": issue.title,
        "matches": [
            {
                "file": m.file_path,
                "score": m.score,
                "context": m.context[:100],
            }
            for m in matches
        ],
    }

@mcp.tool()
async def find_tickets_for_code(file_path: str) -> dict:
    """Find Jina tickets related to a code file."""
    
    # Read file
    content = await asyncio.to_thread(read_file, file_path)
    
    # Fetch all Jina issues
    embedder = get_jina_embedder()
    query = "status IN (Open, 'In Progress')"  # Only active tickets
    issues = await embedder.fetch_jina_issues(query)
    
    # Find matching issues
    matches = []
    model = await embedder._ensure_model_loaded()
    
    code_embedding = model.encode(content[:512])
    
    for issue in issues:
        issue_text = f"{issue.title}\n{issue.description}"
        issue_embedding = model.encode(issue_text)
        
        similarity = float((code_embedding @ issue_embedding) / (
            (code_embedding ** 2).sum() ** 0.5 * (issue_embedding ** 2).sum() ** 0.5
        ))
        
        if similarity > 0.6:
            matches.append({
                "ticket": issue.key,
                "title": issue.title,
                "score": similarity,
                "url": issue.url,
            })
    
    return {
        "file": file_path,
        "related_tickets": sorted(matches, key=lambda m: m["score"], reverse=True),
    }
```

### 4. Server Integration

```python
# src/mem_graph/server.py

# On startup, preload Jina issues (optional)
@mcp.lifespan
async def startup():
    # Fetch Jina issues on startup (can be slow)
    if os.getenv("JINA_PRELOAD", "false").lower() == "true":
        embedder = get_jina_embedder()
        logger.info("Preloading Jina issues...")
        issues = await embedder.fetch_jina_issues()
        logger.info(f"Loaded {len(issues)} Jina issues")
    
    yield
    
    # Cleanup (unload embedder model if loaded)
    pass
```

---

## Benefits

1. **Traceability:** See which code implements which ticket
2. **Bidirectional:** Query from ticket to code OR code to ticket
3. **Semantic:** Works without manual mappings
4. **Efficient:** Model is unloaded after use (low memory overhead)
5. **Real-Time:** Can be run on-demand during agent execution

---

## Configuration

```bash
# .env

JINA_URL=https://jina.example.com
JINA_TOKEN=<your-jina-token>
JINA_PRELOAD=false  # Whether to load issues on server startup
JINA_THRESHOLD=0.7  # Similarity threshold for matches
```

---

## Performance Considerations

1. **Model Size:** Jinaai embeddings are ~100MB (downloaded once, cached)
2. **Inference Time:** ~100ms per issue + code (fast on 32GB system)
3. **TTL Unloading:** Model stays in VRAM for 5 min after use, then freed
4. **Lazy Loading:** Model only loads when first query runs

---

## Implementation Checklist

- [ ] Implement `JinaCodeEmbedder` service
- [ ] Add Jina API client for fetching issues
- [ ] Implement embedding inference (jina model + Ollama)
- [ ] Add lazy model loading with TTL
- [ ] Create `fetch_jina_issues` tool
- [ ] Create `find_code_for_ticket` tool
- [ ] Create `find_tickets_for_code` tool
- [ ] Extend graph schema for JinaIssue nodes
- [ ] Store embeddings for future use (optional)
- [ ] Test with sample Jina instance

---

## Success Criteria

1. Jina issues are fetched and embedded
2. Code files are matched to issues semantically
3. Graph stores Jina nodes and edges
4. Tools return relevant code matches
5. Model is unloaded after TTL expires
6. No VRAM regression after model unload

---

## Dependencies

- `sentence-transformers>=5.4.0` (already in `pyproject.toml`)
- Ollama (docker or local) for efficient inference
- Jina API access (token or user:pass)
- jinaai/jina-embeddings-v4-text-code model (~100MB)

---

## Notes

- Jinaai embeddings are optimized for text + code, unlike general-purpose models
- Q5_K_M quantization keeps model size reasonable (~50MB)
- Inference is CPU-based (no GPU needed) but still fast (~100ms)
- VRAM savings come from unloading after use, not model size
