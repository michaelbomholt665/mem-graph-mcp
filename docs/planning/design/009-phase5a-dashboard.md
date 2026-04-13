# Design: Phase 5a - Knowledge Graph Dashboard (ForceGraph Visualization)

**Status:** Design Phase  
**Priority:** Low-Medium (Advanced UI)  
**Date:** 2026-04-13

---

## Overview

Phase 5a builds an interactive web-based dashboard that visualizes the knowledge graph in real-time. Users can:

1. **Explore Nodes:** Click to zoom into memory facts, code modules, violations
2. **Trace Relationships:** See how violations relate to decisions to code patches
3. **Monitor Activity:** Watch as agents update the graph during runs
4. **Search and Filter:** Find specific patterns or violations

This requires a lightweight web frontend (vanilla JS or Vue) that queries the FastMCP server for graph data.

---

## Goals

1. **Visual Knowledge Representation:** See the graph, not just query results
2. **Interactive Exploration:** Drill down into nodes and connections
3. **Real-Time Updates:** Dashboard updates as agents work
4. **Integration with CLI:** Launch from `fastmcp dev apps`

---

## Scope

### In Scope
- Design ForceGraph visualization (3D force-directed layout)
- Create node types: Memory, Codebase, Violations, Decisions
- Implement relationship edges with labels
- Build lightweight web frontend (no heavy frameworks)
- Add graph query API to FastMCP server
- Implement real-time updates (polling or WebSocket)
- Add search and filter UI

### Out of Scope
- Complex animation (keep it simple for performance)
- Custom node designs (use consistent circle + icon pattern)
- Persistent graph state (stateless refresh is acceptable)
- Multi-user collaboration (single-user for now)

---

## Architecture

### 1. Graph Query API

Add tools to FastMCP server for querying graph structure:

```python
# src/mem_graph/tools/graph/graph_queries.py

from pydantic import BaseModel, Field

class NodeData(BaseModel):
    """Node in visualization."""
    id: str
    label: str
    type: str  # "fact", "violation", "decision", "file", "agent"
    metadata: dict

class EdgeData(BaseModel):
    """Relationship in visualization."""
    source: str  # from_node_id
    target: str  # to_node_id
    label: str
    type: str  # "AFFECTS", "IMPLEMENTS", "MENTIONS", etc.

class GraphSnapshot(BaseModel):
    """Complete graph snapshot for visualization."""
    nodes: list[NodeData]
    edges: list[EdgeData]
    timestamp: str

@mcp.tool()
async def get_graph_snapshot(
    project_id: str | None = None,
    node_types: list[str] | None = None,
    depth: int = 2,
) -> GraphSnapshot:
    """
    Get graph snapshot for visualization.
    
    Args:
        project_id: Filter to specific project (None = all)
        node_types: Filter to specific types (None = all)
        depth: How many hops to include (1-3)
    
    Returns:
        GraphSnapshot with all nodes and edges visible to dashboard
    """
    
    query = """
    MATCH (n:Fact|Violation|Decision|File|Agent)
    WHERE $project_id IS NULL OR n.project_id = $project_id
    AND ($types IS NULL OR TYPE(n) IN $types)
    WITH n
    MATCH (n)-[r]-(m)
    WHERE LENGTH(shortestPath((n)-[*]->(m))) <= $depth
    RETURN
        COLLECT(DISTINCT {
            id: n.node_id,
            label: COALESCE(n.name, n.title, n.id),
            type: LABELS(n)[0],
            metadata: properties(n),
        }) as nodes,
        COLLECT(DISTINCT {
            source: n.node_id,
            target: m.node_id,
            label: TYPE(r),
            type: TYPE(r),
        }) as edges
    """
    
    result = await graph.query(
        query,
        project_id=project_id,
        types=node_types,
        depth=depth,
    )
    
    nodes = result.get("nodes", [])
    edges = result.get("edges", [])
    
    # Deduplicate
    node_ids = {n["id"] for n in nodes}
    edges = [e for e in edges if e["source"] in node_ids and e["target"] in node_ids]
    
    return GraphSnapshot(
        nodes=[NodeData(**n) for n in nodes],
        edges=[EdgeData(**e) for e in edges],
        timestamp=datetime.now().isoformat(),
    )

@mcp.tool()
async def get_node_details(node_id: str) -> dict:
    """Get full details for a specific node."""
    
    query = """
    MATCH (n) WHERE n.node_id = $node_id
    OPTIONAL MATCH (n)-[r]-(related)
    RETURN
        properties(n) as node,
        COLLECT({
            type: TYPE(r),
            target: related.node_id,
            target_label: COALESCE(related.name, related.title, related.id),
        }) as relationships
    """
    
    result = await graph.query(query, node_id=node_id)
    return result

@mcp.tool()
async def search_graph(
    query: str,
    limit: int = 20,
) -> list[NodeData]:
    """Full-text search over graph nodes."""
    
    cypher = """
    MATCH (n)
    WHERE n.content CONTAINS $query OR n.name CONTAINS $query
    RETURN
        n.node_id as id,
        COALESCE(n.name, n.title, n.id) as label,
        LABELS(n)[0] as type,
        properties(n) as metadata
    LIMIT $limit
    """
    
    results = await graph.query(cypher, query=query, limit=limit)
    return [NodeData(**r) for r in results]
```

### 2. Frontend (HTML + Vanilla JS)

```html
<!-- src/mem_graph/static/dashboard.html -->

<!DOCTYPE html>
<html>
<head>
    <title>Memory Graph Dashboard</title>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <script src="https://d3js.org/d3.v7.min.js"></script>
    <script src="https://threejs.org/build/three.min.js"></script>
    <script src="https://threejs.org/examples/js/controls/TrackballControls.js"></script>
    <!-- ForceGraph 3D -->
    <script src="https://cdn.jsdelivr.net/npm/3d-force-graph@1/dist/3d-force-graph.min.js"></script>
    
    <style>
        body { margin: 0; font-family: system-ui; }
        #canvas { display: block; width: 100%; height: 100vh; }
        #sidebar {
            position: absolute;
            top: 0;
            right: 0;
            width: 300px;
            max-height: 100%;
            background: rgba(255, 255, 255, 0.95);
            border-left: 1px solid #ddd;
            padding: 20px;
            overflow-y: auto;
            box-shadow: -2px 0 10px rgba(0, 0, 0, 0.1);
        }
        #search { width: 100%; padding: 8px; margin-bottom: 15px; }
        .filter-group { margin-bottom: 15px; }
        .filter-group label { display: block; margin-bottom: 5px; }
        .filter-group input { margin-right: 5px; }
        .node-info { margin-top: 20px; padding: 15px; background: #f5f5f5; border-radius: 4px; }
        .node-info h3 { margin-top: 0; }
        .node-info p { margin: 5px 0; font-size: 0.9em; }
        .loading { text-align: center; color: #999; }
    </style>
</head>
<body>
    <!-- 3D Graph Canvas -->
    <div id="canvas"></div>
    
    <!-- Sidebar with search and filters -->
    <div id="sidebar">
        <h2>Knowledge Graph</h2>
        <input id="search" type="text" placeholder="Search nodes..." />
        
        <div class="filter-group">
            <label>Node Types:</label>
            <div>
                <input type="checkbox" id="filter-fact" value="Fact" checked /> Fact
                <input type="checkbox" id="filter-violation" value="Violation" checked /> Violation
                <input type="checkbox" id="filter-decision" value="Decision" checked /> Decision
                <input type="checkbox" id="filter-file" value="File" checked /> File
            </div>
        </div>
        
        <div class="node-info" id="node-info" style="display: none;">
            <h3 id="node-title"></h3>
            <div id="node-details"></div>
        </div>
    </div>

    <script>
        const Graph = ForceGraph3D();
        
        let graphData = { nodes: [], links: [] };
        let selectedNode = null;
        
        // Initialize canvas
        const canvas = document.getElementById('canvas');
        Graph(canvas)
            .bgColor('#f5f5f5')
            .nodeAutoColorBy('type')
            .nodeLabel(node => `${node.label}\n(${node.type})`)
            .onNodeClick(node => selectNode(node));
        
        // Load graph data
        async function loadGraph() {
            const response = await fetch('/get_graph_snapshot?project_id=null');
            const data = await response.json();
            
            graphData = {
                nodes: data.nodes,
                links: data.edges.map(e => ({
                    source: e.source,
                    target: e.target,
                    label: e.label,
                })),
            };
            
            Graph
                .graphData(graphData)
                .nodeVal(node => {
                    // Node size by type
                    const sizes = { Fact: 10, Violation: 15, Decision: 12, File: 8 };
                    return sizes[node.type] || 8;
                });
        }
        
        // Select node and show details
        async function selectNode(node) {
            selectedNode = node;
            
            const response = await fetch(`/get_node_details?node_id=${node.id}`);
            const details = await response.json();
            
            const infoEl = document.getElementById('node-info');
            document.getElementById('node-title').textContent = node.label;
            document.getElementById('node-details').innerHTML = `
                <p><strong>Type:</strong> ${node.type}</p>
                <p><strong>ID:</strong> <code>${node.id}</code></p>
                ${Object.entries(details.metadata || {})
                    .slice(0, 5)  // Show first 5 fields
                    .map(([k, v]) => `<p><strong>${k}:</strong> ${String(v).substring(0, 50)}</p>`)
                    .join('')}
            `;
            infoEl.style.display = 'block';
            
            // Highlight connected nodes
            Graph.highlightedLink(); // Clear previous
            Graph.highlightedNode(node);
        }
        
        // Search
        document.getElementById('search').addEventListener('input', async (e) => {
            if (!e.target.value) return;
            
            const response = await fetch(`/search_graph?query=${encodeURIComponent(e.target.value)}`);
            const results = await response.json();
            
            if (results.length > 0) {
                selectNode(results[0]);
                // Pan to node
                Graph.centerAt(results[0], 300);
                Graph.zoom(2, 300);
            }
        });
        
        // Filter
        ['fact', 'violation', 'decision', 'file'].forEach(type => {
            document.getElementById(`filter-${type}`).addEventListener('change', (e) => {
                const activeTypes = Array.from(document.querySelectorAll('input[type="checkbox"]:checked'))
                    .map(el => el.value);
                
                const filtered = {
                    nodes: graphData.nodes.filter(n => activeTypes.includes(n.type)),
                    links: graphData.links.filter(l => {
                        const source = graphData.nodes.find(n => n.id === l.source);
                        const target = graphData.nodes.find(n => n.id === l.target);
                        return source && target && 
                               activeTypes.includes(source.type) && 
                               activeTypes.includes(target.type);
                    }),
                };
                
                Graph.graphData(filtered);
            });
        });
        
        // Load on startup
        loadGraph();
        
        // Auto-refresh every 30 seconds
        setInterval(loadGraph, 30000);
    </script>
</body>
</html>
```

### 3. Server Routes

```python
# src/mem_graph/server.py

from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Route

async def dashboard(request):
    """Serve dashboard HTML."""
    return FileResponse('src/mem_graph/static/dashboard.html')

async def graph_snapshot(request):
    """API: Get graph snapshot."""
    project_id = request.query_params.get('project_id')
    snapshot = await get_graph_snapshot(project_id)
    return JSONResponse(snapshot.model_dump())

async def node_details(request):
    """API: Get node details."""
    node_id = request.query_params.get('node_id')
    details = await get_node_details(node_id)
    return JSONResponse(details)

async def search(request):
    """API: Search graph."""
    query = request.query_params.get('query', '')
    limit = int(request.query_params.get('limit', 20))
    results = await search_graph(query, limit)
    return JSONResponse([r.model_dump() for r in results])

# Add routes to app
app.routes.extend([
    Route('/dashboard', dashboard),
    Route('/get_graph_snapshot', graph_snapshot),
    Route('/get_node_details', node_details),
    Route('/search_graph', search),
])
```

### 4. Node Type Styling

```python
# src/mem_graph/static/node_styles.json

{
  "Fact": {
    "color": "#4CAF50",
    "icon": "💾",
    "size": 10
  },
  "Violation": {
    "color": "#F44336",
    "icon": "⚠️",
    "size": 15
  },
  "Decision": {
    "color": "#2196F3",
    "icon": "🎯",
    "size": 12
  },
  "File": {
    "color": "#FF9800",
    "icon": "📄",
    "size": 8
  },
  "Agent": {
    "color": "#9C27B0",
    "icon": "🤖",
    "size": 12
  },
  "Pattern": {
    "color": "#00BCD4",
    "icon": "🔄",
    "size": 10
  }
}
```

---

## Benefits

1. **Visual Understanding:** See data relationships at a glance
2. **Exploration:** Drill down into complex graphs
3. **Real-Time Feedback:** Watch agents update graph during runs
4. **Search Efficiency:** Find patterns quickly
5. **Engagement:** Interactive dashboard feels more sophisticated

---

## Implementation Order

1. Create graph query API tools
2. Build frontend HTML + JS
3. Add routes to server
4. Test in browser
5. Add real-time updates (polling)
6. Add WebSocket for live updates (future)

---

## Implementation Checklist

- [ ] Create `get_graph_snapshot` tool
- [ ] Create `get_node_details` tool
- [ ] Create `search_graph` tool
- [ ] Build dashboard.html with ForceGraph
- [ ] Add CSS styling
- [ ] Add search and filter UI
- [ ] Add node selection and details panel
- [ ] Add routes to server
- [ ] Test graph visualization
- [ ] Test search and filter

---

## Success Criteria

1. Dashboard displays graph with 3D visualization
2. Nodes are colored by type
3. Edges show relationships
4. Search finds and highlights nodes
5. Filters hide/show node types
6. Clicking nodes shows details
7. No performance degradation with 1000+ nodes
8. Auto-refreshes to show fresh data

---

## Dependencies

- `3d-force-graph` JavaScript library (CDN)
- `three.js` for 3D rendering
- `d3.js` for data manipulation
- No backend dependencies (uses existing tools)

---

## Future Enhancements

1. **Live Updates:** WebSocket for real-time graph changes
2. **Timeline:** Replay graph evolution over time
3. **Metrics:** Show confidence scores, decay rates
4. **Clustering:** Auto-group similar nodes
5. **Export:** Download graph as JSON/SVG
