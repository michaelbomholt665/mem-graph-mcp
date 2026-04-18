(() => {
  const state = {
    graph: null,
    snapshot: null,
    styles: {},
    selectedNodeId: null,
    pendingNodeId: null,
    agents: [],
    workflows: [],
    tools: [],
    evals: [],
    tree: null,
    expanded: new Set(['.']),
    selectedFileNode: null,
  };

  const elements = {};
  const tabTitles = {
    overview: ['Overview', 'Server status, graph telemetry, and recent evaluation health.'],
    explorer: ['Explorer', 'Search and inspect the memory graph.'],
    agents: ['Agents', 'Checked-in agent modules and deterministic workflow diagrams.'],
    tools: ['Tools', 'MCP tool catalog grouped by namespace.'],
    evals: ['Evals', 'Recent local evaluation runs.'],
    files: ['Files', 'Repository tree and graph-backed file violations.'],
  };

  function qs(id) {
    return document.getElementById(id);
  }

  function text(value, fallback = '') {
    if (value === null || value === undefined || value === '') {
      return fallback;
    }
    return String(value);
  }

  async function fetchJson(url) {
    const response = await fetch(url);
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.error || payload.status || `Request failed with ${response.status}`);
    }
    return response.json();
  }

  function applyTheme(theme) {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem('memory-atlas-theme', theme);
    elements.themeToggle.textContent = theme === 'dark' ? 'Light Theme' : 'Dark Theme';
  }

  function initTheme() {
    const stored = localStorage.getItem('memory-atlas-theme');
    const fallback = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    applyTheme(stored || fallback);
  }

  function switchTab(tab) {
    document.querySelectorAll('[data-tab]').forEach((button) => {
      button.classList.toggle('is-active', button.dataset.tab === tab);
    });
    document.querySelectorAll('[data-panel]').forEach((panel) => {
      panel.classList.toggle('is-active', panel.dataset.panel === tab);
    });
    const [title, subtitle] = tabTitles[tab] || tabTitles.overview;
    elements.pageTitle.textContent = title;
    elements.pageSubtitle.textContent = subtitle;
    
    if (tab === 'explorer') {
      if (!state.graph) {
        initializeGraph();
      }
      if (state.graph) {
        setTimeout(() => state.graph.refresh(), 40);
      }
    }
    if (tab === 'files' && !state.tree) {
      loadFileTree();
    }
  }

  function activeTypes() {
    return Array.from(document.querySelectorAll('[data-type-filter]:checked')).map((input) => input.value);
  }

  function styleFor(type) {
    return state.styles[type] || { color: '#116d72', size: 12 };
  }

  function setStatus(element, message) {
    element.textContent = message;
  }

  function buildLegend(types) {
    elements.legend.innerHTML = '';
    types.forEach((type) => {
      const item = document.createElement('span');
      item.className = 'legend-item';
      const swatch = document.createElement('span');
      swatch.className = 'swatch';
      swatch.style.backgroundColor = styleFor(type).color;
      item.append(swatch, document.createTextNode(type));
      elements.legend.append(item);
    });
  }

  function buildTypeFilters(types) {
    const existing = activeTypes();
    const preserved = existing.length > 0 ? new Set(existing) : new Set(types);
    elements.typeFilters.innerHTML = '';
    types.forEach((type) => {
      const chip = document.createElement('div');
      chip.className = 'type-chip';
      const label = document.createElement('label');
      const checkbox = document.createElement('input');
      checkbox.type = 'checkbox';
      checkbox.checked = preserved.has(type);
      checkbox.value = type;
      checkbox.dataset.typeFilter = 'true';
      checkbox.addEventListener('change', () => refreshSnapshot());
      const swatch = document.createElement('span');
      swatch.className = 'swatch';
      swatch.style.backgroundColor = styleFor(type).color;
      label.append(checkbox, swatch, document.createTextNode(type));
      chip.append(label);
      elements.typeFilters.append(chip);
    });
  }

  function drawNode(node, ctx, globalScale) {
    const style = styleFor(node.type);
    const radius = style.size || 12;
    const selected = node.id === state.selectedNodeId;
    const label = node.label || node.id;
    const fontSize = Math.max(12 / globalScale, 5);
    const ink = getComputedStyle(document.documentElement).getPropertyValue('--ink').trim() || '#182026';

    ctx.save();
    ctx.beginPath();
    ctx.fillStyle = style.color;
    ctx.globalAlpha = selected ? 1 : 0.9;
    ctx.arc(node.x, node.y, radius, 0, 2 * Math.PI);
    ctx.fill();
    ctx.lineWidth = selected ? 4 / globalScale : 1.5 / globalScale;
    ctx.strokeStyle = selected ? '#d28a32' : 'rgba(255,255,255,0.9)';
    ctx.stroke();
    if (globalScale > 1.25 || selected) {
      ctx.font = `600 ${fontSize}px system-ui`;
      ctx.fillStyle = ink;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'top';
      ctx.fillText(label, node.x, node.y + radius + 4);
    }
    ctx.restore();
  }

  function initializeGraph() {
    if (!elements.graphCanvas) {
      console.error("ForceGraph container #graph-canvas not found!");
      return;
    }
    state.graph = ForceGraph()(elements.graphCanvas)
      .backgroundColor('transparent')
      .linkColor(() => getComputedStyle(document.documentElement).getPropertyValue('--line').trim() || '#d8e0e6')
      .linkDirectionalParticles(0)
      .nodeCanvasObject(drawNode)
      .nodePointerAreaPaint((node, color, ctx) => {
        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.arc(node.x, node.y, (styleFor(node.type).size || 12) + 8, 0, 2 * Math.PI);
        ctx.fill();
      })
      .onNodeClick((node) => selectNode(node.id, true));
  }

  function graphDataFromSnapshot(snapshot) {
    return {
      nodes: snapshot.nodes.map((node) => ({
        ...node,
        color: styleFor(node.type).color,
        val: styleFor(node.type).size || 12,
      })),
      links: snapshot.edges.map((edge) => ({ ...edge })),
    };
  }

  function renderSnapshot(snapshot) {
    state.snapshot = snapshot;
    elements.graphSummary.textContent = `${snapshot.nodes.length} nodes / ${snapshot.edges.length} edges`;
    buildLegend(snapshot.available_types || []);
    buildTypeFilters(snapshot.available_types || []);
    state.graph.graphData(graphDataFromSnapshot(snapshot));
  }

  function renderSearchResults(results) {
    elements.searchResults.innerHTML = '';
    if (!results.length) {
      elements.searchResults.innerHTML = '<li class="muted">No matching nodes found.</li>';
      return;
    }
    results.forEach((result) => {
      const item = document.createElement('li');
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'result-button';
      button.textContent = `${result.label} (${result.type})`;
      button.addEventListener('click', () => selectNode(result.id, true));
      item.append(button);
      elements.searchResults.append(item);
    });
  }

  function metaRow(label, value) {
    const row = document.createElement('div');
    const term = document.createElement('dt');
    const description = document.createElement('dd');
    term.textContent = label;
    description.textContent = text(value, 'None');
    row.append(term, description);
    return row;
  }

  function renderDetails(details) {
    if (details.error) {
      elements.detailsEmpty.textContent = details.error;
      elements.detailsEmpty.classList.remove('is-hidden');
      elements.detailsCard.classList.add('is-hidden');
      return;
    }
    const node = details.node;
    elements.detailsType.textContent = node.type;
    elements.detailsTitle.textContent = node.label;
    elements.detailsMetadata.innerHTML = '';
    Object.entries(node.metadata || {}).forEach(([key, value]) => {
      if (value !== null && value !== undefined && value !== '') {
        elements.detailsMetadata.append(metaRow(key.replaceAll('_', ' '), value));
      }
    });
    elements.detailsRelationships.innerHTML = '';
    const relationships = details.relationships || [];
    if (!relationships.length) {
      elements.detailsRelationships.innerHTML = '<li class="muted">No related nodes in the current snapshot.</li>';
    } else {
      relationships.forEach((relationship) => {
        const item = document.createElement('li');
        item.textContent = `${relationship.node.label} / ${relationship.direction} / ${relationship.relationship}`;
        elements.detailsRelationships.append(item);
      });
    }
    elements.detailsEmpty.classList.add('is-hidden');
    elements.detailsCard.classList.remove('is-hidden');
  }

  async function selectNode(nodeId, shouldFocus = false) {
    state.selectedNodeId = nodeId;
    state.graph.refresh();
    if (shouldFocus) {
      const liveNode = (state.graph.graphData().nodes || []).find((candidate) => candidate.id === nodeId);
      if (liveNode && typeof liveNode.x === 'number' && typeof liveNode.y === 'number') {
        state.graph.centerAt(liveNode.x, liveNode.y, 350);
        state.graph.zoom(3.5, 400);
      }
    }
    try {
      renderDetails(await fetchJson(`/dashboard/api/node/${encodeURIComponent(nodeId)}`));
    } catch (error) {
      renderDetails({ error: error.message || 'Failed to load node details.' });
    }
  }

  async function refreshSnapshot() {
    try {
      setStatus(elements.snapshotStatus, 'Refreshing graph snapshot');
      const params = new URLSearchParams();
      const projectId = elements.projectId.value.trim();
      if (projectId) params.set('project_id', projectId);
      params.set('depth', elements.depthSelect.value);
      params.set('max_nodes', elements.maxNodesSelect.value);
      const types = activeTypes();
      if (types.length) params.set('node_types', types.join(','));
      const snapshot = await fetchJson(`/dashboard/api/graph?${params.toString()}`);
      renderSnapshot(snapshot);
      elements.lastUpdated.textContent = `Updated ${new Date(snapshot.timestamp).toLocaleTimeString()}`;
      setStatus(elements.snapshotStatus, 'Graph snapshot ready');
      if (state.pendingNodeId && snapshot.nodes.some((node) => node.id === state.pendingNodeId)) {
        await selectNode(state.pendingNodeId, true);
        state.pendingNodeId = null;
      }
    } catch (error) {
      setStatus(elements.snapshotStatus, error.message || 'Failed to load graph snapshot.');
      elements.graphSummary.textContent = 'Snapshot unavailable';
    }
  }

  async function runSearch() {
    const query = elements.searchInput.value.trim();
    if (!query) {
      renderSearchResults([]);
      return;
    }
    try {
      const params = new URLSearchParams({ query, limit: '12' });
      const projectId = elements.projectId.value.trim();
      if (projectId) params.set('project_id', projectId);
      const types = activeTypes();
      if (types.length) params.set('node_types', types.join(','));
      const results = await fetchJson(`/dashboard/api/search?${params.toString()}`);
      renderSearchResults(results);
      if (results[0]) await selectNode(results[0].id, true);
    } catch (error) {
      renderSearchResults([]);
      setStatus(elements.snapshotStatus, error.message || 'Search failed.');
    }
  }

  function renderStats(container, stats) {
    container.innerHTML = '';
    const entries = Object.entries(stats || {});
    if (!entries.length) {
      container.innerHTML = '<p class="muted">No records.</p>';
      return;
    }
    entries.forEach(([label, count]) => {
      const row = document.createElement('div');
      row.className = 'stat-row';
      row.append(document.createTextNode(label), document.createTextNode(String(count)));
      container.append(row);
    });
  }

  async function loadSystem() {
    try {
      const payload = await fetchJson('/dashboard/api/system');
      const telemetry = payload.telemetry || {};
      elements.metricHealth.textContent = payload.status || 'unknown';
      elements.metricDb.textContent = payload.db?.status || 'unknown';
      elements.metricNodes.textContent = String(telemetry.node_count || 0);
      elements.metricEdges.textContent = String(telemetry.edge_count || 0);
      elements.metricUptime.textContent = `${Math.round(payload.uptime_seconds || 0)}s`;
      elements.serverVersion.textContent = `${payload.server.name} ${payload.server.version}`;
      renderStats(elements.taskStatusList, telemetry.task_status);
      renderStats(elements.violationSeverityList, telemetry.violation_severity);
    } catch (error) {
      elements.metricHealth.textContent = 'degraded';
      elements.metricDb.textContent = error.message || 'System unavailable';
    }
  }

  function renderRecentEvals() {
    const rows = state.evals.slice(0, 5);
    if (!rows.length) {
      elements.recentEvals.innerHTML = '<p class="muted">No eval runs recorded.</p>';
      return;
    }
    elements.recentEvals.innerHTML = tableHtml(
      ['Mode', 'Status', 'Suites', 'Started'],
      rows.map((row) => [
        text(row.mode),
        row.total_suites === row.passed_suites ? 'PASS' : 'FAIL',
        `${row.passed_suites}/${row.total_suites}`,
        text(row.started_at, 'Unknown'),
      ]),
    );
  }

  function renderAgents() {
    elements.agentsList.innerHTML = '';
    if (!state.agents.length) {
      elements.agentsList.innerHTML = '<p class="muted">No agent modules found.</p>';
      return;
    }
    state.agents.forEach((agent) => {
      const card = document.createElement('article');
      card.className = 'agent-card';
      const title = document.createElement('h4');
      title.textContent = agent.module;
      const desc = document.createElement('p');
      desc.className = 'muted';
      desc.textContent = agent.description;
      const tags = document.createElement('div');
      tags.className = 'tag-row';
      [...(agent.agents || []), ...(agent.roles || [])].forEach((tag) => {
        const chip = document.createElement('span');
        chip.className = 'tag';
        chip.textContent = tag;
        tags.append(chip);
      });
      card.append(title, desc, tags);
      elements.agentsList.append(card);
    });
  }

  function renderWorkflowSvg(workflow) {
    const width = 760;
    const rowHeight = 72;
    const height = Math.max(220, workflow.nodes.length * rowHeight + 30);
    const positions = new Map();
    workflow.nodes.forEach((node, index) => {
      positions.set(node, { x: 230 + (index % 2) * 250, y: 35 + index * rowHeight });
    });
    const edgeLines = (workflow.edges || []).map((edge) => {
      const source = positions.get(edge.source);
      const target = positions.get(edge.target);
      if (!source || !target) return '';
      return `<path d="M ${source.x + 90} ${source.y + 16} L ${target.x} ${target.y + 16}" stroke="var(--line)" fill="none" marker-end="url(#arrow)" /><text x="${(source.x + target.x) / 2 + 30}" y="${(source.y + target.y) / 2 + 10}" fill="var(--muted)" font-size="11">${escapeHtml(edge.label || '')}</text>`;
    }).join('');
    const nodeBoxes = workflow.nodes.map((node) => {
      const position = positions.get(node);
      return `<g><rect x="${position.x}" y="${position.y}" width="180" height="34" rx="7" fill="var(--surface-2)" stroke="var(--line)" /><text x="${position.x + 90}" y="${position.y + 22}" text-anchor="middle" fill="var(--ink)" font-size="12">${escapeHtml(node)}</text></g>`;
    }).join('');
    return `<svg class="workflow-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(workflow.display_name)}"><defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="7" refY="3" orient="auto"><path d="M0,0 L0,6 L8,3 z" fill="var(--line)" /></marker></defs>${edgeLines}${nodeBoxes}</svg>`;
  }

  function renderWorkflows() {
    elements.workflowList.innerHTML = '';
    state.workflows.forEach((workflow) => {
      const card = document.createElement('article');
      card.className = 'workflow-card';
      card.innerHTML = `<h4>${escapeHtml(workflow.display_name)}</h4><p class="muted">${escapeHtml(workflow.description)}</p><p class="muted">${escapeHtml(workflow.source_file)}</p>${renderWorkflowSvg(workflow)}<details><summary>Mermaid</summary><pre class="schema-block">${escapeHtml(workflow.mermaid)}</pre></details>`;
      elements.workflowList.append(card);
    });
  }

  async function loadAgentsAndWorkflows() {
    try {
      const [agentsPayload, workflowPayload] = await Promise.all([
        fetchJson('/dashboard/api/agents'),
        fetchJson('/dashboard/api/workflows'),
      ]);
      state.agents = agentsPayload.agents || [];
      state.workflows = workflowPayload.workflows || [];
      elements.agentsStatus.textContent = `${state.agents.length} modules`;
      elements.workflowsStatus.textContent = `${state.workflows.length} workflows`;
      renderAgents();
      renderWorkflows();
    } catch (error) {
      elements.agentsStatus.textContent = error.message || 'Unable to load agents.';
      elements.workflowsStatus.textContent = 'Unavailable';
    }
  }

  function tableHtml(headers, rows) {
    return `<table><thead><tr>${headers.map((header) => `<th>${escapeHtml(header)}</th>`).join('')}</tr></thead><tbody>${rows.map((row) => `<tr>${row.map((cell) => `<td>${escapeHtml(text(cell))}</td>`).join('')}</tr>`).join('')}</tbody></table>`;
  }

  function renderTools() {
    const query = elements.toolsFilter.value.trim().toLowerCase();
    const rows = [];
    state.tools.forEach((group) => {
      (group.tools || []).forEach((tool) => {
        const haystack = `${tool.name} ${tool.description} ${group.namespace}`.toLowerCase();
        if (!query || haystack.includes(query)) {
          rows.push([
            group.namespace,
            tool.name,
            tool.description || '',
            JSON.stringify(tool.input_schema || {}, null, 2),
          ]);
        }
      });
    });
    if (!rows.length) {
      elements.toolsTable.innerHTML = '<p class="muted">No matching tools.</p>';
      return;
    }
    elements.toolsTable.innerHTML = `<table><thead><tr><th>Namespace</th><th>Name</th><th>Description</th><th>Schema</th></tr></thead><tbody>${rows.map((row) => `<tr><td>${escapeHtml(row[0])}</td><td>${escapeHtml(row[1])}</td><td>${escapeHtml(row[2])}</td><td><details><summary>Input</summary><pre class="schema-block">${escapeHtml(row[3])}</pre></details></td></tr>`).join('')}</tbody></table>`;
  }

  async function loadTools() {
    try {
      const payload = await fetchJson('/dashboard/api/tools');
      state.tools = payload.namespaces || [];
      elements.toolsStatus.textContent = `${payload.count || 0} tools`;
      renderTools();
    } catch (error) {
      elements.toolsStatus.textContent = error.message || 'Unable to load tools.';
    }
  }

  function renderEvals() {
    if (!state.evals.length) {
      elements.evalsTable.innerHTML = '<p class="muted">No eval runs recorded.</p>';
      return;
    }
    elements.evalsTable.innerHTML = `<table><thead><tr><th>Status</th><th>Mode</th><th>Label</th><th>Suites</th><th>Duration</th><th>Trigger</th><th>Project</th><th>Summary</th></tr></thead><tbody>${state.evals.map((row) => `<tr><td>${row.total_suites === row.passed_suites ? 'PASS' : 'FAIL'}</td><td>${escapeHtml(text(row.mode))}</td><td>${escapeHtml(text(row.label))}</td><td>${row.passed_suites}/${row.total_suites}</td><td>${Math.round(row.total_duration_ms || 0)}ms</td><td>${escapeHtml(text(row.trigger))}</td><td>${escapeHtml(text(row.project_id))}</td><td><details><summary>${escapeHtml(text(row.started_at, 'Details'))}</summary><pre class="schema-block">${escapeHtml(text(row.summary))}</pre></details></td></tr>`).join('')}</tbody></table>`;
  }

  async function loadEvals() {
    try {
      const params = new URLSearchParams({ limit: '20' });
      const projectId = elements.evalsProjectId.value.trim();
      if (projectId) params.set('project_id', projectId);
      const payload = await fetchJson(`/dashboard/api/evals?${params.toString()}`);
      state.evals = payload.evals || [];
      elements.evalsStatus.textContent = `${state.evals.length} eval runs`;
      renderEvals();
      renderRecentEvals();
    } catch (error) {
      elements.evalsStatus.textContent = error.message || 'Unable to load evals.';
      elements.recentEvals.innerHTML = '<p class="muted">Eval data unavailable.</p>';
    }
  }

  function fileTreeParams() {
    const params = new URLSearchParams();
    const rootPath = elements.fileRootPath.value.trim();
    const projectId = elements.fileProjectId.value.trim();
    if (rootPath) params.set('root_path', rootPath);
    if (projectId) params.set('project_id', projectId);
    if (elements.fileIncludeHidden.checked) params.set('include_hidden', 'true');
    return params;
  }

  function summarizeTree(node) {
    let files = 0;
    let directories = 0;
    const stack = [node];
    while (stack.length) {
      const current = stack.pop();
      if (current.is_dir) {
        directories += 1;
        (current.children || []).forEach((child) => stack.push(child));
      } else {
        files += 1;
      }
    }
    return `${directories} directories / ${files} files`;
  }

  function fileNodeMatches(node, query, problemsOnly) {
    const matchesSelf = (!problemsOnly || node.violation_count > 0)
      && (!query || node.relative_path.toLowerCase().includes(query) || node.name.toLowerCase().includes(query));
    return matchesSelf || (node.children || []).some((child) => fileNodeMatches(child, query, problemsOnly));
  }

  function ensureExpanded(path) {
    const segments = path.split('/');
    let current = '';
    segments.forEach((segment) => {
      current = current ? `${current}/${segment}` : segment;
      state.expanded.add(current);
    });
    state.expanded.add('.');
  }

  function renderTreeNode(node, depth = 0) {
    const query = elements.fileFilterInput.value.trim().toLowerCase();
    const problemsOnly = elements.fileProblemsOnly.checked;
    if (!fileNodeMatches(node, query, problemsOnly)) return null;
    const wrapper = document.createElement('div');
    const row = document.createElement('button');
    row.type = 'button';
    row.className = 'tree-row';
    row.style.paddingLeft = `${8 + depth * 16}px`;
    if (state.selectedFileNode?.path === node.path) row.classList.add('is-selected');
    const expanded = state.expanded.has(node.relative_path);
    row.innerHTML = `<span>${node.is_dir ? (expanded ? 'v' : '>') : ''}</span><span class="tree-icon">${node.is_dir ? 'DIR' : 'FILE'}</span><span class="tree-label">${escapeHtml(node.name)}</span><span class="muted">${node.last_audited ? new Date(node.last_audited).toLocaleDateString() : ''}</span>${node.violation_count ? `<span class="tree-badge">${node.violation_count}</span>` : '<span></span>'}`;
    row.addEventListener('click', async () => {
      state.selectedFileNode = node;
      if (node.is_dir) {
        if (expanded) state.expanded.delete(node.relative_path);
        else state.expanded.add(node.relative_path);
      }
      ensureExpanded(node.relative_path);
      renderFileTree();
      await renderFileDetails(node);
    });
    wrapper.append(row);
    if (node.is_dir && expanded) {
      (node.children || []).forEach((child) => {
        const childNode = renderTreeNode(child, depth + 1);
        if (childNode) wrapper.append(childNode);
      });
    }
    return wrapper;
  }

  function renderFileTree() {
    elements.fileTreeRoot.innerHTML = '';
    if (!state.tree) return;
    const tree = renderTreeNode(state.tree, 0);
    if (tree) elements.fileTreeRoot.append(tree);
  }

  function renderDirectoryDetails(node) {
    elements.fileDetailsKind.textContent = 'Directory';
    elements.fileDetailsTitle.textContent = node.relative_path === '.' ? node.path : node.relative_path;
    elements.fileDetailsMeta.innerHTML = '';
    elements.fileDetailsMeta.append(
      metaRow('Absolute Path', node.path),
      metaRow('Open Violations', node.violation_count || 0),
      metaRow('Last Audited', node.last_audited ? new Date(node.last_audited).toLocaleString() : 'Unknown'),
      metaRow('Violation Types', (node.violation_types || []).join(', ') || 'None'),
    );
    elements.fileDetailsCount.textContent = `${node.violation_count || 0} open issues in this branch`;
    elements.fileViolationList.innerHTML = '<li class="muted">Directory summaries aggregate child file data.</li>';
    elements.fileDashboardLink.classList.add('is-hidden');
  }

  async function renderFileDetails(node) {
    elements.fileDetailsEmpty.classList.add('is-hidden');
    elements.fileDetailsCard.classList.remove('is-hidden');
    elements.fileDetailsSubhead.textContent = node.relative_path === '.' ? node.path : node.relative_path;
    if (node.is_dir) {
      renderDirectoryDetails(node);
      return;
    }
    try {
      const params = fileTreeParams();
      params.set('file_path', node.relative_path);
      const details = await fetchJson(`/file-tree/api/violations?${params.toString()}`);
      elements.fileDetailsKind.textContent = 'File';
      elements.fileDetailsTitle.textContent = details.relative_path;
      elements.fileDetailsMeta.innerHTML = '';
      elements.fileDetailsMeta.append(
        metaRow('Absolute Path', details.absolute_path),
        metaRow('Open Violations', details.violation_count || 0),
        metaRow('Last Audited', details.last_audited ? new Date(details.last_audited).toLocaleString() : 'Unknown'),
        metaRow('Violation Types', (details.violation_types || []).join(', ') || 'None'),
      );
      elements.fileDetailsCount.textContent = `${details.total} total findings`;
      elements.fileViolationList.innerHTML = '';
      if (!details.violations?.length) {
        elements.fileViolationList.innerHTML = '<li class="muted">No graph-backed violations recorded for this file.</li>';
      } else {
        details.violations.forEach((violation) => {
          const item = document.createElement('li');
          item.textContent = `${violation.severity} / ${violation.rule} / ${violation.description}`;
          elements.fileViolationList.append(item);
        });
      }
      if (details.graph_node_id) {
        elements.fileDashboardLink.href = `/dashboard?node=${encodeURIComponent(details.graph_node_id)}`;
        elements.fileDashboardLink.classList.remove('is-hidden');
      } else {
        elements.fileDashboardLink.classList.add('is-hidden');
      }
    } catch (error) {
      elements.fileViolationList.innerHTML = `<li class="muted">${escapeHtml(error.message || 'Failed to load file details.')}</li>`;
    }
  }

  async function loadFileTree() {
    try {
      elements.fileTreeStatus.textContent = 'Refreshing file tree';
      const tree = await fetchJson(`/file-tree/api/tree?${fileTreeParams().toString()}`);
      state.tree = tree;
      state.expanded = new Set(['.']);
      ensureExpanded(tree.relative_path);
      elements.fileTreeSummary.textContent = summarizeTree(tree);
      elements.fileTreeStatus.textContent = 'File tree ready';
      renderFileTree();
    } catch (error) {
      state.tree = null;
      elements.fileTreeRoot.innerHTML = `<p class="muted">${escapeHtml(error.message || 'Failed to load file tree.')}</p>`;
      elements.fileTreeSummary.textContent = 'Tree unavailable';
      elements.fileTreeStatus.textContent = error.message || 'Failed to load file tree.';
    }
  }

  function escapeHtml(value) {
    return text(value)
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#039;');
  }

  function bindElements() {
    [
      'theme-toggle', 'server-version', 'page-title', 'page-subtitle', 'refresh-all-button',
      'metric-health', 'metric-db', 'metric-nodes', 'metric-edges', 'metric-uptime',
      'task-status-list', 'violation-severity-list', 'recent-evals',
      'project-id', 'search-input', 'search-button', 'refresh-button', 'reset-filters-button',
      'depth-select', 'max-nodes-select', 'snapshot-status', 'last-updated', 'graph-summary',
      'graph-canvas', 'type-filters', 'search-results', 'details-empty', 'details-card',
      'details-type', 'details-title', 'details-metadata', 'details-relationships', 'legend',
      'agents-status', 'agents-list', 'workflows-status', 'workflow-list',
      'tools-status', 'tools-filter', 'tools-table',
      'evals-status', 'evals-project-id', 'evals-refresh-button', 'evals-table',
      'file-root-path', 'file-project-id', 'file-problems-only', 'file-include-hidden',
      'file-filter-input', 'file-refresh-button', 'file-tree-status', 'file-tree-summary',
      'file-tree-root', 'file-details-empty', 'file-details-card', 'file-details-kind',
      'file-details-title', 'file-details-subhead', 'file-details-meta', 'file-details-count',
      'file-violation-list', 'file-dashboard-link',
    ].forEach((id) => {
      const key = id.replaceAll('-', ' ').replace(/ ([a-z])/g, (_, letter) => letter.toUpperCase()).replace(' ', '');
      elements[key] = qs(id);
    });
  }

  async function initialize() {
    bindElements();
    initTheme();
    const params = new URLSearchParams(globalThis.location.search);
    state.pendingNodeId = params.get('node');
    if (params.get('project_id')) {
      elements.projectId.value = params.get('project_id');
      elements.fileProjectId.value = params.get('project_id');
      elements.evalsProjectId.value = params.get('project_id');
    }

    const stylesPayload = await fetchJson('/dashboard/api/styles');
    state.styles = stylesPayload.styles || {};

    document.querySelectorAll('[data-tab]').forEach((button) => {
      button.addEventListener('click', () => switchTab(button.dataset.tab));
    });
    document.querySelectorAll('[data-tab-link]').forEach((button) => {
      button.addEventListener('click', () => switchTab(button.dataset.tabLink));
    });
    elements.themeToggle.addEventListener('click', () => {
      applyTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark');
      if (state.graph) state.graph.refresh();
    });
    elements.refreshAllButton.addEventListener('click', () => {
      loadSystem();
      refreshSnapshot();
      loadAgentsAndWorkflows();
      loadTools();
      loadEvals();
      if (document.querySelector('[data-panel="files"]').classList.contains('is-active')) loadFileTree();
    });
    elements.searchButton.addEventListener('click', runSearch);
    elements.refreshButton.addEventListener('click', refreshSnapshot);
    elements.depthSelect.addEventListener('change', refreshSnapshot);
    elements.maxNodesSelect.addEventListener('change', refreshSnapshot);
    elements.projectId.addEventListener('keydown', (event) => { if (event.key === 'Enter') refreshSnapshot(); });
    elements.searchInput.addEventListener('keydown', (event) => { if (event.key === 'Enter') runSearch(); });
    elements.resetFiltersButton.addEventListener('click', () => {
      document.querySelectorAll('[data-type-filter]').forEach((input) => { input.checked = true; });
      refreshSnapshot();
    });
    elements.toolsFilter.addEventListener('input', renderTools);
    elements.evalsRefreshButton.addEventListener('click', loadEvals);
    elements.fileRefreshButton.addEventListener('click', loadFileTree);
    elements.fileFilterInput.addEventListener('input', renderFileTree);
    elements.fileProblemsOnly.addEventListener('change', renderFileTree);
    elements.fileIncludeHidden.addEventListener('change', loadFileTree);

    await Promise.allSettled([
      loadSystem(),
      refreshSnapshot(),
      loadAgentsAndWorkflows(),
      loadTools(),
      loadEvals(),
    ]);
    setInterval(() => {
      loadSystem();
      refreshSnapshot();
      loadEvals();
    }, 30000);
  }

  document.addEventListener('DOMContentLoaded', () => {
    initialize().catch((error) => {
      console.error(error);
    });
  });
})();
