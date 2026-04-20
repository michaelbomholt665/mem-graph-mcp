# Design: Phase 5c - File Explorer Tab

**Status:** Design Phase  
**Priority:** Low (Nice-to-have)  
**Date:** 2026-04-13

---

## Overview

Phase 5c adds a file tree view to the dashboard that shows:

1. **Project Structure:** Hierarchical view of all files
2. **Violation Markers:** Red badges show violations per file
3. **Last Audited:** Timestamp when each file was last analyzed
4. **Quick Jump:** Click file to jump to it in the graph dashboard

This complements the graph by providing traditional folder navigation for users comfortable with file trees.

---

## Goals

1. **Familiar Navigation:** File tree is how users think about code
2. **Problem Highlighting:** Violations are visible at a glance
3. **Integration:** File tree connects to graph dashboard
4. **Filtering:** Users can filter by violation type or status

---

## Scope

### In Scope
- Build file tree navigation (hierarchy)
- Show violation badges per file
- Add last-audited timestamp
- Implement click-to-jump to graph
- Add filtering (by violation, by status)

### Out of Scope
- File editing in this UI (use agent tools instead)
- Custom file icons per type (use simple text)
- Collapsing/expanding performance optimization (assume reasonable tree size)

---

## Architecture

### 1. File API for Tree

```python
# src/mem_graph/tools/filesystem/tree.py

from pydantic import BaseModel, Field

class FileNode(BaseModel):
    """Node in file tree."""
    path: str
    name: str
    is_dir: bool
    children: list["FileNode"] = Field(default_factory=list)
    violation_count: int = 0
    last_audited: str | None = None
    violations: list[str] = Field(default_factory=list)  # violation types

@mcp.tool()
async def get_file_tree(
    root_path: str,
    include_violations: bool = True,
) -> FileNode:
    """
    Get file tree for a directory.
    
    Includes violation counts and last audit timestamps.
    """
    
    async def build_tree(path: str) -> FileNode:
        """Recursively build tree."""
        
        is_dir = os.path.isdir(path)
        name = os.path.basename(path) or path
        
        node = FileNode(
            path=path,
            name=name,
            is_dir=is_dir,
        )
        
        if is_dir:
            # Add children
            for item in os.listdir(path):
                if item.startswith('.'):
                    continue  # Skip hidden
                
                child_path = os.path.join(path, item)
                child = await build_tree(child_path)
                node.children.append(child)
        
        # Query violations for this file
        if include_violations:
            violations = await graph.query("""
                MATCH (v:Violation {file: $path})
                RETURN v.type as type, COUNT(*) as count
            """, path=path)
            
            node.violation_count = sum(v['count'] for v in violations)
            node.violations = [v['type'] for v in violations]
            
            # Get last audit timestamp
            audit = await graph.query("""
                MATCH (f:File {path: $path})-[:AUDITED_AT]-(audit:Audit)
                RETURN audit.timestamp as timestamp
                ORDER BY audit.timestamp DESC
                LIMIT 1
            """, path=path)
            
            if audit:
                node.last_audited = audit[0]['timestamp']
        
        return node
    
    root = await build_tree(root_path)
    
    # Sort children (dirs first, then by name)
    def sort_tree(node: FileNode):
        node.children.sort(key=lambda n: (not n.is_dir, n.name.lower()))
        for child in node.children:
            sort_tree(child)
    
    sort_tree(root)
    
    return root

@mcp.tool()
async def get_file_violations(file_path: str) -> dict:
    """Get all violations for a specific file."""
    
    violations = await graph.query("""
        MATCH (v:Violation {file: $path})
        RETURN {
            type: v.type,
            severity: v.severity,
            line: v.line,
            description: v.description,
            fix: v.suggested_fix,
        } as violations
        ORDER BY v.severity DESC, v.line ASC
    """, path=file_path)
    
    return {
        "file": file_path,
        "total": len(violations),
        "violations": violations,
    }
```

### 2. Frontend File Tree

```html
<!-- src/mem_graph/static/file-tree.html -->

<!DOCTYPE html>
<html>
<head>
    <title>File Explorer</title>
    <style>
        body {
            font-family: system-ui;
            margin: 0;
            display: flex;
            height: 100vh;
        }
        
        #tree-container {
            width: 300px;
            border-right: 1px solid #ddd;
            overflow-y: auto;
            background: #f9f9f9;
        }
        
        #details-container {
            flex: 1;
            overflow-y: auto;
            padding: 20px;
        }
        
        .tree-item {
            padding: 8px 12px;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 0.9em;
        }
        
        .tree-item:hover {
            background: #e8e8e8;
        }
        
        .tree-item.selected {
            background: #2196F3;
            color: white;
        }
        
        .tree-toggle {
            width: 20px;
            text-align: center;
            cursor: pointer;
        }
        
        .tree-toggle.expanded::before {
            content: "▼";
        }
        
        .tree-toggle.collapsed::before {
            content: "▶";
        }
        
        .tree-icon {
            width: 16px;
        }
        
        .tree-name {
            flex: 1;
        }
        
        .tree-badge {
            background: #F44336;
            color: white;
            border-radius: 12px;
            padding: 2px 8px;
            font-size: 0.75em;
            font-weight: bold;
        }
        
        .tree-children {
            padding-left: 24px;
        }
        
        .tree-children.hidden {
            display: none;
        }
        
        .violation {
            padding: 12px;
            margin-bottom: 12px;
            border-left: 4px;
            background: #f5f5f5;
        }
        
        .violation.critical {
            border-left-color: #D32F2F;
        }
        
        .violation.high {
            border-left-color: #F57C00;
        }
        
        .violation.medium {
            border-left-color: #FBC02D;
        }
        
        .violation-title {
            font-weight: bold;
            margin-bottom: 5px;
        }
        
        .violation-line {
            font-size: 0.85em;
            color: #666;
        }
        
        h2 { margin-top: 0; }
    </style>
</head>
<body>
    <div id="tree-container">
        <h3>Files</h3>
        <div id="tree"></div>
    </div>
    
    <div id="details-container">
        <h2 id="file-name"></h2>
        <div id="violations"></div>
    </div>

    <script>
        let treeData = null;
        
        // Load file tree
        async function loadTree() {
            const response = await fetch('/get_file_tree?root_path=/project');
            treeData = await response.json();
            renderTree(treeData);
        }
        
        function renderTree(node, parentEl = null, depth = 0) {
            if (!parentEl) {
                parentEl = document.getElementById('tree');
                parentEl.innerHTML = '';
            }
            
            const itemEl = document.createElement('div');
            itemEl.className = 'tree-item';
            itemEl.style.paddingLeft = `${12 + depth * 24}px`;
            
            // Toggle for directories
            if (node.is_dir && node.children.length > 0) {
                const toggle = document.createElement('span');
                toggle.className = 'tree-toggle collapsed';
                toggle.onclick = (e) => {
                    e.stopPropagation();
                    toggle.classList.toggle('expanded');
                    toggle.classList.toggle('collapsed');
                    childrenEl.classList.toggle('hidden');
                };
                itemEl.appendChild(toggle);
            } else {
                const spacer = document.createElement('span');
                spacer.className = 'tree-toggle';
                itemEl.appendChild(spacer);
            }
            
            // Icon
            const icon = document.createElement('span');
            icon.className = 'tree-icon';
            icon.textContent = node.is_dir ? '📁' : '📄';
            itemEl.appendChild(icon);
            
            // Name
            const nameEl = document.createElement('span');
            nameEl.className = 'tree-name';
            nameEl.textContent = node.name;
            itemEl.appendChild(nameEl);
            
            // Violation badge
            if (node.violation_count > 0) {
                const badge = document.createElement('span');
                badge.className = 'tree-badge';
                badge.textContent = node.violation_count;
                itemEl.appendChild(badge);
            }
            
            // Click to show details
            itemEl.onclick = async () => {
                document.querySelectorAll('.tree-item.selected').forEach(e => {
                    e.classList.remove('selected');
                });
                itemEl.classList.add('selected');
                
                await showFileDetails(node.path);
            };
            
            parentEl.appendChild(itemEl);
            
            // Children
            if (node.children.length > 0) {
                const childrenEl = document.createElement('div');
                childrenEl.className = 'tree-children hidden';
                parentEl.appendChild(childrenEl);
                
                for (const child of node.children) {
                    renderTree(child, childrenEl, depth + 1);
                }
            }
        }
        
        async function showFileDetails(filePath) {
            const response = await fetch(`/get_file_violations?file_path=${encodeURIComponent(filePath)}`);
            const data = await response.json();
            
            document.getElementById('file-name').textContent = filePath;
            
            const violationsEl = document.getElementById('violations');
            violationsEl.innerHTML = '';
            
            if (data.violations.length === 0) {
                violationsEl.innerHTML = '<p style="color: #4CAF50;">✓ No violations</p>';
                return;
            }
            
            for (const v of data.violations) {
                const el = document.createElement('div');
                el.className = `violation ${v.severity.toLowerCase()}`;
                el.innerHTML = `
                    <div class="violation-title">${v.type}</div>
                    <div class="violation-line">Line ${v.line}: ${v.severity}</div>
                    <p>${v.description}</p>
                    ${v.fix ? `<p><strong>Fix:</strong> ${v.fix}</p>` : ''}
                `;
                violationsEl.appendChild(el);
            }
        }
        
        // Load on startup
        loadTree();
    </script>
</body>
</html>
```

### 3. Server Routes

```python
# src/mem_graph/server.py

async def file_tree_html(request):
    """Serve file tree explorer."""
    return FileResponse('src/mem_graph/static/file-tree.html')

async def get_file_tree_api(request):
    """API: Get file tree."""
    root = request.query_params.get('root_path', '/project')
    tree = await get_file_tree(root)
    return JSONResponse(tree.model_dump())

async def get_file_violations_api(request):
    """API: Get violations for file."""
    file_path = request.query_params.get('file_path')
    violations = await get_file_violations(file_path)
    return JSONResponse(violations)

# Add routes
app.routes.extend([
    Route('/file-explorer', file_tree_html),
    Route('/get_file_tree', get_file_tree_api),
    Route('/get_file_violations', get_file_violations_api),
])
```

---

## Benefits

1. **Familiar Navigation:** Traditional file tree is recognizable
2. **Problem Visibility:** Violations show up as badges
3. **Context:** Timestamp tells when each file was last analyzed
4. **Integration:** Click to jump to file in graph dashboard

---

## Implementation Checklist

- [ ] Create `get_file_tree` tool
- [ ] Create `get_file_violations` tool
- [ ] Build file-tree.html with tree navigation
- [ ] Add CSS styling for tree
- [ ] Add click handlers and file details panel
- [ ] Add violation badges to tree nodes
- [ ] Add routes to server
- [ ] Test tree rendering with large codebases
- [ ] Performance test (should handle 1000+ files)

---

## Success Criteria

1. File tree displays all files in hierarchy
2. Violation counts show as badges
3. Clicking file shows its violations
4. Tree is navigable and responsive
5. No performance issues with 1000+ files

---

## Dependencies

- No external libraries (vanilla JS)
- Graph client for violation queries

---

## Notes

- File tree is read-only (editing happens via agent tools)
- Updates happen via periodic refresh (auto-refresh every 60s?)
- Badge count is total violations, not categorized per file
- Hidden files (`.`) are excluded
