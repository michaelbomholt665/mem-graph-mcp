# Mem-Graph Dashboard Repair & Stabilization Plan

## Overview
This document outlines the systematic repair and stabilization plan for the mem-graph dashboard, divided into three phases as specified.

## Phase 1: Backend Diagnostics & API Stabilization

### 1.1 Filesystem 500 Error Fix
**Current Issue**: The `/file-tree/api/tree` endpoint may return 500 errors due to improper handling of the `root_path` parameter.

**Location**: 
- Handler: `src/mem_graph/server.py` line 1214 (`_file_tree_data` function)
- Service: `src/mem_graph/tools/filesystem/tree.py` `get_file_tree` function
- Helper: `src/mem_graph/tools/filesystem/status.py` `resolve_root_path` and `_project_root` functions

**Required Changes**:
1. **Immediate Fix**: Ensure the `_file_tree_data` handler properly wraps all operations in try/except blocks and returns meaningful JSON error messages instead of 500 errors.

2. **Refactor `get_file_tree` call**: Modify the handler to automatically resolve repository root path from database when `project_id` is provided:
   ```python
   # Current behavior: requires user to provide root_path
   root_path=request.query_params.get("root_path")
   project_id=request.query_params.get("project_id")
   
   # Expected behavior: if project_id is provided, resolve root_path automatically
   if not root_path and project_id:
       root_path = _project_root(project_id)
   ```

3. **Error Handling**: Ensure all exceptions are caught and return proper JSON error responses with appropriate status codes (400 for bad requests, 500 for server errors).

### 1.2 Global Project List Endpoint
**Current Issue**: No endpoint exists to retrieve a list of projects for dropdown population.

**Required Changes**:
1. **Create new endpoint**: Add `GET /dashboard/api/projects` in `src/mem_graph/server.py`
2. **Query Project table**: Return list of projects with id and name fields
3. **Response format**: `[{id: str, name: str}]`
4. **Implementation location**: Add new route handler function (e.g., `_projects_list`)

**Example Implementation**:
```python
async def _projects_list(request: Request) -> JSONResponse:
    try:
        # Query Project table
        projects = await query_projects_from_db()
        return JSONResponse([{"id": p.id, "name": p.name} for p in projects])
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
```

### 1.3 Graph Data Validation
**Current Issue**: The `/dashboard/api/graph` endpoint may return data that doesn't conform to force-graph factory expectations.

**Required Changes**:
1. **Inspect raw JSON**: Verify the structure of nodes and edges returned by `/dashboard/api/graph`
2. **Ensure node format**: Each node must have `x` and `y` coordinates OR ensure `initializePositions` logic properly provides them
3. **Validation checks**:
   - Nodes array exists and contains objects
   - Each node has required fields (id, label, type, etc.)
   - Coordinates are properly initialized (either in node data or by layout algorithm)
4. **Fix initialization**: If `initializePositions` is used, verify it's being called correctly before graph rendering

## Phase 2: Frontend Engineering

### 2.1 Force Graph Rescue
**Current Issue**: Force Graph is failing to render properly.

**Files to inspect**:
- `src/mem_graph/static/dashboard.js`
- `src/mem_graph/static/force-graph.js`

**Required Changes**:
1. **Container verification**: Ensure ForceGraph factory receives the correct container element
   ```javascript
   // Check this in initializeGraph()
   elements.graphCanvas = qs('#graph-canvas');
   if (!elements.graphCanvas) {
     console.error("ForceGraph container #graph-canvas not found!");
     return;
   }
   ```

2. **Canvas sizing**: Verify canvas is properly sized before draw() is invoked
   - Check CSS dimensions
   - Ensure canvas has explicit width/height

3. **Debug logging**: Add console.log trace to draw() function to confirm it's being triggered
   ```javascript
   function draw() {
     console.log('draw() called - graph rendering');
     // existing draw logic
   }
   ```

4. **Draw invocation**: Ensure draw() is called after graph data is set and container is ready

### 2.2 Unified Dropdown Component
**Current Issue**: Dropdowns are not unified and don't fetch project data dynamically.

**Required Changes**:
1. **Fetch projects on load**: In `initialize()` function, add:
   ```javascript
   const stylesPayload = await fetchJson('/dashboard/api/styles');
   state.styles = stylesPayload.styles || {};
   
   // NEW: Fetch projects
   const projects = await fetchJson('/dashboard/api/projects');
   // Populate dropdowns with project data
   ```

2. **Refactor dropdowns**: Replace text inputs with `<select>` elements in:
   - `explorer-tab`
   - `files-tab`
   - Any other tabs that use project-specific inputs

3. **Populate projects**: Use the new `/dashboard/api/projects` endpoint to populate all dropdowns

4. **Event listeners**: Implement event listeners for dropdown changes:
   ```javascript
   elements.projectId.addEventListener('change', () => {
     refreshSnapshot();
     loadFileTree();
   });
   ```

5. **Update existing references**:
   - `elements.projectId` (for graph snapshots)
   - `elements.fileProjectId` (for file tree)
   - `elements.evalsProjectId` (for evaluations)

### 2.3 Event Handling
**Required Changes**:
1. **Dropdown change events**: Add event listeners to trigger refreshes:
   ```javascript
   elements.projectId.addEventListener('change', refreshSnapshot);
   elements.fileProjectId.addEventListener('change', loadFileTree);
   ```

2. **Ensure proper timing**: Make sure dropdowns are populated before any initial data fetch

## Phase 3: Verification Protocol

### 3.1 Logging Requirements
**All API handlers must be wrapped in try/except blocks**:
```python
try:
    # handler logic
    return JSONResponse(result)
except FileNotFoundError as e:
    return JSONResponse({"error": str(e)}, status_code=404)
except Exception as e:
    return JSONResponse({"error": str(e)}, status_code=500)
```

### 3.2 Console Debugging
**Add debug logs for every API call** in `dashboard.js`:
```javascript
async function fetchJson(url) {
  console.log('API Request:', url);
  const response = await fetch(url);
  console.log('API Response:', response.status, url);
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    console.error('API Error:', payload);
    throw new Error(payload.error || payload.status || `Request failed with ${response.status}`);
  }
  const data = await response.json();
  console.log('API Success:', url);
  return data;
}
```

### 3.3 Visual Check - Pass Conditions
All three conditions must be met:
1. ✅ **Graph renders without errors**: No JavaScript errors in console, force-graph displays nodes and edges
2. ✅ **File tree loads automatically**: When selecting a project from dropdown, file tree populates without manual refresh
3. ✅ **Explorer tab correctly filters**: Selected project filters the graph to show only related nodes

## Constraints

### Development Constraints
1. **No new features**: Do not add new features until all three phases are verified complete
2. **API logging**: All API calls must be logged to browser console during development
3. **Error handling**: All endpoints must return meaningful error messages, never raw 500 errors

### Testing Checklist
- [ ] Backend API endpoints return proper JSON responses
- [ ] `/file-tree/api/tree` handles project_id parameter correctly
- [ ] `/dashboard/api/projects` returns valid project list
- [ ] `/dashboard/api/graph` returns properly formatted data
- [ ] Force Graph renders without errors
- [ ] Dropdowns populate from API on page load
- [ ] Selecting project triggers file tree refresh
- [ ] Selecting project triggers graph refresh
- [ ] Explorer tab filters graph by selected project
- [ ] All API calls logged to console
- [ ] Error messages are user-friendly (not raw exceptions)

## Implementation Priority

### Critical (Must Fix First)
1. File 500 error in `/file-tree/api/tree`
2. Add `/dashboard/api/projects` endpoint
3. Force Graph rendering issue

### High Priority
4. Graph data validation and coordinate initialization
5. Unified dropdown component
6. Event listeners for dropdown changes

### Medium Priority
7. Enhanced error logging in API handlers
8. Console debug logging in frontend
9. Verification of all pass conditions

## Next Steps
1. Review and approve this plan
2. Begin with Phase 1, Critical items
3. Document any issues found during inspection
4. Implement fixes incrementally with testing
5. Verify each phase before proceeding to the next
6. Complete all verification checks before feature expansion