# Design: Phase 4a - Polish (Icons & Rich Content)

**Status:** Design Phase  
**Priority:** Medium (UX improvement)  
**Date:** 2026-04-13

---

## Overview

Phase 4a enhances FastMCP communication with visual richness:

1. **Icons:** Every tool and server gets a visual icon
2. **Rich Content:** Tools can return multi-part responses (text + images/tables)
3. **Progress Display:** Long-running operations show progress bars
4. **Data Visualization:** Diagrams and structured tables for complex data

This makes the MCP experience more visually coherent and informative.

---

## Goals

1. **Visual Clarity:** Icons help users quickly identify tool categories
2. **Information Density:** Tables and diagrams convey data more clearly
3. **Operation Feedback:** Progress bars show long ops are still running
4. **Professional Polish:** Visual consistency across tools

---

## Scope

### In Scope
- Add Icon definitions for all tools and server
- Implement rich content rendering (text + images)
- Add progress reporting for long operations
- Create diagram rendering for graph visualizations
- Add table formatting for structured data

### Out of Scope
- Custom UI (use FastMCP's native rich content)
- Animated icons (static icons only)
- Client-side rendering (MCP clients handle rendering)

---

## Architecture

### 1. Icon Definitions

```python
# src/mem_graph/resources/icons.py

from enum import Enum
from pathlib import Path

class IconRegistry(Enum):
    """Icons for tools, servers, and operations."""
    
    # Brain/memory
    BRAIN = "🧠"
    MEMORY = "💾"
    RECALL = "📖"
    
    # Code operations
    CODE = "💻"
    AUDIT = "🔍"
    FIX = "🔧"
    VALIDATE = "✓"
    REFACTOR = "🔄"
    
    # Work tracking
    TASK = "✅"
    DECISION = "🎯"
    VIOLATION = "⚠️"
    PROJECT = "📦"
    
    # Filesystem
    FILE = "📄"
    FOLDER = "📁"
    LINK = "🔗"
    
    # Graph operations
    GRAPH = "🕸️"
    NODE = "⚫"
    EDGE = "—"
    
    # System
    SERVER = "🌐"
    SETTINGS = "⚙️"
    LOG = "📝"

# FastMCP Icon objects for server
from fastmcp import Image

TOOL_ICONS = {
    "memory_store": Image(url="data:image/svg+xml;base64,..."),  # Brain icon
    "memory_recall": Image(url="data:image/svg+xml;base64,..."),  # Search icon
    "audit_package": Image(url="data:image/svg+xml;base64,..."),  # Magnifying glass
    "execute_fix": Image(url="data:image/svg+xml;base64,..."),   # Wrench
    "orchestrate_codebase": Image(url="data:image/svg+xml;base64,..."),  # Gears
}

# Server icon
SERVER_ICON = Image(
    url="data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMzIiIGhlaWdodD0iMzIiPi4uLjwvc3ZnPg=="
)
```

### 2. Rich Content Tools

Tools return structured data that clients render as tables/diagrams:

```python
# src/mem_graph/tools/agents/decorators.py

from fastmcp import Text, Image, Table
from typing import Union

class RichResponse:
    """Multi-part response with text, images, and tables."""
    
    def __init__(self, text: str = ""):
        self.parts: list[Union[Text, Image, Table]] = []
        if text:
            self.parts.append(Text(text))
    
    def add_text(self, text: str) -> "RichResponse":
        """Add text part."""
        self.parts.append(Text(text))
        return self
    
    def add_image(self, url: str, description: str = "") -> "RichResponse":
        """Add image (e.g., diagram)."""
        self.parts.append(Image(url=url, description=description))
        return self
    
    def add_table(self, data: list[dict], columns: list[str]) -> "RichResponse":
        """Add structured table."""
        self.parts.append(Table.from_data(data, columns))
        return self
    
    def add_code_block(self, code: str, language: str = "python") -> "RichResponse":
        """Add code block."""
        self.parts.append(Text(f"```{language}\n{code}\n```"))
        return self

# Example: Audit tool returns rich response
@mcp.tool()
async def audit_package(package_path: str) -> RichResponse:
    """Audit a package with rich visualization."""
    
    response = RichResponse(f"Auditing {package_path}...")
    
    # Run audit
    findings = await run_audit_agent(package_path)
    
    # Add findings table
    response.add_table(
        data=[
            {
                "file": f["file"],
                "issue": f["issue"],
                "severity": f["severity"],
                "line": f["line"],
            }
            for f in findings
        ],
        columns=["file", "issue", "severity", "line"],
    )
    
    # Add summary text
    severity_counts = {}
    for f in findings:
        severity_counts[f["severity"]] = severity_counts.get(f["severity"], 0) + 1
    
    summary = "\n".join(
        f"- {severity}: {count} issues"
        for severity, count in severity_counts.items()
    )
    response.add_text(f"\nSummary:\n{summary}")
    
    # Add diagram of issue distribution
    diagram_url = await generate_pie_chart(severity_counts)
    response.add_image(
        url=diagram_url,
        description="Issue distribution by severity",
    )
    
    return response
```

### 3. Progress Reporting for Long Operations

```python
# src/mem_graph/tools/agents/progress.py

from fastmcp.server.context import Context

async def long_running_tool(ctx: Context, package_path: str) -> RichResponse:
    """
    Tool that reports progress during long operations.
    
    Client sees real-time progress updates.
    """
    
    files = await enumerate_files(package_path)
    total = len(files)
    
    response = RichResponse(f"Processing {total} files...\n")
    
    for i, file_path in enumerate(files):
        # Process file
        result = await process_file(file_path)
        
        # Report progress
        progress_pct = ((i + 1) / total) * 100
        await ctx.report_progress(
            progress=progress_pct / 100,
            message=f"Processing {file_path} ({i + 1}/{total})",
        )
        
        # Add to response
        response.add_text(f"✓ {file_path}: {result}\n")
    
    response.add_text(f"\nCompleted {total} files")
    
    return response
```

### 4. Diagram Rendering

Create nice diagrams for complex results:

```python
# src/mem_graph/services/diagrams.py

import json
from typing import Any

async def generate_architecture_diagram(
    project_id: str,
    components: list[str],
) -> str:
    """
    Generate SVG architecture diagram.
    
    Returns data URI for embedding in response.
    """
    
    # Build Mermaid diagram
    mermaid = "graph LR\n"
    for i, component in enumerate(components):
        mermaid += f"  {component}[{i}]\n"
    
    # Convert to SVG (use mermaid-cli or kroki)
    svg = await convert_mermaid_to_svg(mermaid)
    
    # Return as data URI
    return f"data:image/svg+xml;base64,{base64.b64encode(svg).decode()}"

async def generate_pie_chart(
    data: dict[str, int],
    title: str = "",
) -> str:
    """Generate pie chart as SVG data URI."""
    
    # Build Chart.js-style spec
    chart_spec = {
        "type": "pie",
        "data": {
            "labels": list(data.keys()),
            "datasets": [{
                "data": list(data.values()),
                "backgroundColor": ["#FF6384", "#36A2EB", "#FFCE56"],
            }],
        },
        "options": {"title": {"text": title}},
    }
    
    # Render via quickchart.io or local service
    svg = await render_chart(chart_spec)
    return f"data:image/svg+xml;base64,{base64.b64encode(svg).decode()}"
```

### 5. Icon Assignment in Tools

Update all tools to have icons:

```python
# src/mem_graph/server.py

from .resources.icons import IconRegistry, TOOL_ICONS

# Assign icons to tools during server setup
@mcp.tool(
    icon=TOOL_ICONS.get("memory_store"),
    description="Store a new fact in persistent memory",
)
async def memory_store(content: str, tags: list[str] | None = None) -> dict:
    """..."""
    pass

@mcp.tool(
    icon=TOOL_ICONS.get("memory_recall"),
    description="Recall related facts from memory",
)
async def memory_recall(query: str, limit: int = 5) -> dict:
    """..."""
    pass

@mcp.tool(
    icon=TOOL_ICONS.get("audit_package"),
    description="Audit a package for code smells",
)
async def audit_package(package_path: str) -> RichResponse:
    """..."""
    pass
```

### 6. Server Metadata with Icon

```python
# src/mem_graph/server.py

mcp = FastMCP(
    name="mem-graph",
    description="Memory-augmented code analysis and refactoring",
    icon=SERVER_ICON,
    version="0.2.0",
)
```

---

## Benefits

1. **Visual Hierarchy:** Icons group related tools
2. **Information Clarity:** Tables/diagrams communicate complex data
3. **User Engagement:** Rich content feels interactive
4. **Professional feel:** Polished UX builds trust

---

## Icon Categories

| Category | Icon | Tools |
|----------|------|-------|
| Memory | 🧠 | memory_store, memory_recall, memory_manage |
| Audit | 🔍 | audit_package, triage_violations |
| Fix | 🔧 | execute_fix, orchestrate_codebase |
| Work | ✅ | task_update, decision_record |
| Filesystem | 📄 | file_read, file_write, file_delete |
| Graph | 🕸️ | (dashboard, patterns, etc.) |

---

## Implementation Checklist

- [ ] Create `IconRegistry` enum with all icons
- [ ] Create `RichResponse` class for multi-part responses
- [ ] Add Icon objects for each tool
- [ ] Update all tools to return `RichResponse` where appropriate
- [ ] Implement progress reporting for long ops
- [ ] Create diagram generators (mermaid, charts)
- [ ] Assign icons to server + tools
- [ ] Test rich content in MCP inspector
- [ ] Test progress reporting with long operation

---

## Success Criteria

1. All tools have icons displayed in client
2. Complex responses render as tables/diagrams
3. Long operations show progress updates
4. No regression in tool functionality
5. MCP clients display rich content correctly

---

## Dependencies

- FastMCP with Icon support
- `mermaid-cli` or `kroki` for diagram rendering
- Chart rendering library (quickchart.io API or local)

---

## Notes

- Icons use emoji for simplicity (no custom image assets needed)
- Rich content is optional—tools can still return plain text
- Progress reporting is cumulative (each update replaces previous)
- All images are embedded as data URIs (no external URLs)
