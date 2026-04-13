(() => {
  const state = {
    graph: null,
    snapshot: null,
    styles: {},
    selectedNodeId: null,
    refreshHandle: null,
    pendingNodeId: null,
  };

  const elements = {};

  function qs(id) {
    return document.getElementById(id);
  }

  async function fetchJson(url) {
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`Request failed with ${response.status}`);
    }
    return response.json();
  }

  function activeTypes() {
    return Array.from(document.querySelectorAll('[data-type-filter]:checked')).map(
      (input) => input.value,
    );
  }

  function styleFor(type) {
    return state.styles[type] || { color: '#1f2a30', size: 12 };
  }

  function setStatus(text) {
    elements.snapshotStatus.textContent = text;
  }

  function setLastUpdated(timestamp) {
    if (!timestamp) {
      elements.lastUpdated.textContent = 'Waiting for first snapshot';
      return;
    }
    const date = new Date(timestamp);
    elements.lastUpdated.textContent = `Updated ${date.toLocaleTimeString()}`;
  }

  function buildLegend(availableTypes) {
    elements.legend.innerHTML = '';
    availableTypes.forEach((type) => {
      const item = document.createElement('span');
      item.className = 'legend-item';
      const swatch = document.createElement('span');
      swatch.className = 'swatch';
      swatch.style.backgroundColor = styleFor(type).color;
      item.append(swatch, document.createTextNode(type));
      elements.legend.append(item);
    });
  }

  function buildTypeFilters(availableTypes) {
    const existing = activeTypes();
    const preserved = existing.length > 0 ? new Set(existing) : new Set(availableTypes);
    elements.typeFilters.innerHTML = '';

    availableTypes.forEach((type) => {
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

      const count = document.createElement('span');
      count.className = 'result-meta';
      count.textContent = type;

      label.append(checkbox, swatch, document.createTextNode(type));
      chip.append(label, count);
      elements.typeFilters.append(chip);
    });
  }

  function drawNode(node, ctx, globalScale) {
    const style = styleFor(node.type);
    const radius = style.size || 12;
    const selected = node.id === state.selectedNodeId;
    const label = node.label || node.id;
    const fontSize = Math.max(12 / globalScale, 4);

    ctx.save();
    ctx.beginPath();
    ctx.fillStyle = style.color;
    ctx.globalAlpha = selected ? 1 : 0.92;
    ctx.arc(node.x, node.y, radius, 0, 2 * Math.PI, false);
    ctx.fill();

    ctx.lineWidth = selected ? 4 / globalScale : 1.5 / globalScale;
    ctx.strokeStyle = selected ? '#b84a3d' : 'rgba(255,255,255,0.9)';
    ctx.stroke();

    if (globalScale > 1.3 || selected) {
      ctx.font = `600 ${fontSize}px Space Grotesk`;
      ctx.fillStyle = '#1f2a30';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'top';
      ctx.fillText(label, node.x, node.y + radius + 3);
    }
    ctx.restore();
  }

  function initializeGraph() {
    state.graph = ForceGraph()(elements.graphCanvas)
      .backgroundColor('rgba(0,0,0,0)')
      .linkColor(() => 'rgba(31,42,48,0.18)')
      .linkDirectionalParticles(0)
      .nodeCanvasObject(drawNode)
      .nodePointerAreaPaint((node, color, ctx) => {
        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.arc(node.x, node.y, (styleFor(node.type).size || 12) + 8, 0, 2 * Math.PI, false);
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
    elements.graphSummary.textContent = `${snapshot.nodes.length} nodes · ${snapshot.edges.length} edges`;
    buildLegend(snapshot.available_types);
    buildTypeFilters(snapshot.available_types);
    state.graph.graphData(graphDataFromSnapshot(snapshot));
    if (state.selectedNodeId) {
      state.graph.refresh();
    }
  }

  function renderSearchResults(results) {
    elements.searchResults.innerHTML = '';

    if (results.length === 0) {
      const item = document.createElement('li');
      item.className = 'muted';
      item.textContent = 'No matching nodes found.';
      elements.searchResults.append(item);
      return;
    }

    results.forEach((result) => {
      const item = document.createElement('li');
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'result-button';
      button.innerHTML = `
        <strong>${result.label}</strong><br />
        <span class="result-meta">${result.type}</span>
      `;
      button.addEventListener('click', () => selectNode(result.id, true));
      item.append(button);
      elements.searchResults.append(item);
    });
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
      if (value === null || value === undefined || value === '') {
        return;
      }
      const row = document.createElement('div');
      const term = document.createElement('dt');
      const description = document.createElement('dd');
      term.textContent = key.replaceAll('_', ' ');
      description.textContent = String(value);
      row.append(term, description);
      elements.detailsMetadata.append(row);
    });

    elements.detailsRelationships.innerHTML = '';
    if ((details.relationships || []).length === 0) {
      const item = document.createElement('li');
      item.className = 'muted';
      item.textContent = 'No related nodes in the current snapshot.';
      elements.detailsRelationships.append(item);
    } else {
      details.relationships.forEach((relationship) => {
        const item = document.createElement('li');
        item.innerHTML = `
          <strong>${relationship.node.label}</strong><br />
          <span class="result-meta">${relationship.direction} · ${relationship.relationship}</span>
        `;
        elements.detailsRelationships.append(item);
      });
    }

    elements.detailsEmpty.classList.add('is-hidden');
    elements.detailsCard.classList.remove('is-hidden');
  }

  async function selectNode(nodeId, shouldFocus = false) {
    state.selectedNodeId = nodeId;
    state.graph.refresh();

    if (shouldFocus && state.snapshot) {
      const liveNode = (state.graph.graphData().nodes || []).find((candidate) => candidate.id === nodeId);
      if (liveNode && typeof liveNode.x === 'number' && typeof liveNode.y === 'number') {
        state.graph.centerAt(liveNode.x, liveNode.y, 400);
        state.graph.zoom(4, 500);
      }
    }

    try {
      const details = await fetchJson(`/dashboard/api/node/${encodeURIComponent(nodeId)}`);
      renderDetails(details);
    } catch (error) {
      renderDetails({ error: error.message || 'Failed to load node details.' });
    }
  }

  async function refreshSnapshot() {
    try {
      setStatus('Refreshing graph snapshot…');
      const params = new URLSearchParams();
      const projectId = elements.projectId.value.trim();
      if (projectId) {
        params.set('project_id', projectId);
      }
      params.set('depth', elements.depthSelect.value);
      params.set('max_nodes', elements.maxNodesSelect.value);

      const types = activeTypes();
      if (types.length > 0) {
        params.set('node_types', types.join(','));
      }

      const snapshot = await fetchJson(`/dashboard/api/graph?${params.toString()}`);
      renderSnapshot(snapshot);
      setLastUpdated(snapshot.timestamp);
      setStatus('Graph snapshot ready.');

      if (state.selectedNodeId) {
        const exists = snapshot.nodes.some((node) => node.id === state.selectedNodeId);
        if (exists) {
          await selectNode(state.selectedNodeId, false);
        } else {
          state.selectedNodeId = null;
          elements.detailsCard.classList.add('is-hidden');
          elements.detailsEmpty.classList.remove('is-hidden');
          elements.detailsEmpty.textContent = 'Select a node from the graph or search results to inspect it.';
        }
      } else if (state.pendingNodeId) {
        const exists = snapshot.nodes.some((node) => node.id === state.pendingNodeId);
        if (exists) {
          await selectNode(state.pendingNodeId, true);
        }
        state.pendingNodeId = null;
      }
    } catch (error) {
      setStatus(error.message || 'Failed to load the graph snapshot.');
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
      if (projectId) {
        params.set('project_id', projectId);
      }
      const types = activeTypes();
      if (types.length > 0) {
        params.set('node_types', types.join(','));
      }
      const results = await fetchJson(`/dashboard/api/search?${params.toString()}`);
      renderSearchResults(results);
      if (results[0]) {
        await selectNode(results[0].id, true);
      }
    } catch (error) {
      renderSearchResults([]);
      setStatus(error.message || 'Search failed.');
    }
  }

  async function initialize() {
    const params = new URLSearchParams(globalThis.location.search);
    state.pendingNodeId = params.get('node');

    elements.projectId = qs('project-id');
    elements.searchInput = qs('search-input');
    elements.searchButton = qs('search-button');
    elements.refreshButton = qs('refresh-button');
    elements.resetFiltersButton = qs('reset-filters-button');
    elements.depthSelect = qs('depth-select');
    elements.maxNodesSelect = qs('max-nodes-select');
    elements.snapshotStatus = qs('snapshot-status');
    elements.lastUpdated = qs('last-updated');
    elements.graphSummary = qs('graph-summary');
    elements.graphCanvas = qs('graph-canvas');
    elements.typeFilters = qs('type-filters');
    elements.searchResults = qs('search-results');
    elements.detailsEmpty = qs('details-empty');
    elements.detailsCard = qs('details-card');
    elements.detailsType = qs('details-type');
    elements.detailsTitle = qs('details-title');
    elements.detailsMetadata = qs('details-metadata');
    elements.detailsRelationships = qs('details-relationships');
    elements.legend = qs('legend');

    initializeGraph();
    const stylesPayload = await fetchJson('/dashboard/api/styles');
    state.styles = stylesPayload.styles || {};

    elements.searchButton.addEventListener('click', runSearch);
    elements.refreshButton.addEventListener('click', refreshSnapshot);
    elements.depthSelect.addEventListener('change', refreshSnapshot);
    elements.maxNodesSelect.addEventListener('change', refreshSnapshot);
    elements.projectId.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') {
        refreshSnapshot();
      }
    });
    elements.searchInput.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') {
        runSearch();
      }
    });
    elements.resetFiltersButton.addEventListener('click', () => {
      Array.from(document.querySelectorAll('[data-type-filter]')).forEach((input) => {
        input.checked = true;
      });
      refreshSnapshot();
    });

    await refreshSnapshot();
    state.refreshHandle = globalThis.setInterval(refreshSnapshot, 30000);
  }

  document.addEventListener('DOMContentLoaded', () => {
    initialize().catch((error) => {
      setStatus(error.message || 'Dashboard initialization failed.');
    });
  });
})();