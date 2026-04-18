/**
 * explore.js - Graph Explorer page logic
 */
import { qs, fetchJson, styleFor, metaRow, initProjectDropdown } from './common.js';

const state = {
  graph: null,
  snapshot: null,
  selectedNodeId: null,
  pendingNodeId: null,
};

const elements = {};

function bindElements() {
  [
    'project-id', 'search-input', 'search-button', 'refresh-button', 'reset-filters-button',
    'depth-select', 'max-nodes-select', 'snapshot-status', 'last-updated', 'graph-summary',
    'graph-canvas', 'type-filters', 'search-results', 'details-empty', 'details-card',
    'details-type', 'details-title', 'details-metadata', 'details-relationships', 'legend',
    'server-version'
  ].forEach(id => {
    const key = id.replaceAll('-', ' ').replaceAll(/ ([a-z])/g, (_, letter) => letter.toUpperCase()).replaceAll(' ', '');
    elements[key] = qs(id);
  });
}

function activeTypes() {
  return Array.from(document.querySelectorAll('[data-type-filter]:checked')).map((input) => input.value);
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
  state.graph = ForceGraph(elements.graphCanvas)
    .setBackgroundColor('transparent')
    .setLinkColor(() => getComputedStyle(document.documentElement).getPropertyValue('--line').trim() || '#d8e0e6')
    .linkDirectionalParticles(0)
    .setNodeCanvasObject(drawNode)
    .setNodePointerAreaPaint((node, color, ctx) => {
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.arc(node.x, node.y, (styleFor(node.type).size || 12) + 8, 0, 2 * Math.PI);
      ctx.fill();
    })
    .setOnNodeClick((node) => selectNode(node.id, true));

  globalThis.onThemeChange = () => {
    if (state.graph) state.graph.refresh();
  };
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
  if (state.graph) {
    state.graph.setGraphData(graphDataFromSnapshot(snapshot));
  }
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
  if (relationships.length === 0) {
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
  if (state.graph) {
    state.graph.refresh();
  }
  if (shouldFocus) {
    const liveNode = (state.graph.getGraphData().nodes || []).find((candidate) => candidate.id === nodeId);
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

export async function initExplore() {
  bindElements();
  initializeGraph();
  
  const params = new URLSearchParams(globalThis.location.search);
  state.pendingNodeId = params.get('node');
  
  await initProjectDropdown('project-id', () => refreshSnapshot());
  
  elements.searchButton.addEventListener('click', runSearch);
  elements.searchInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') runSearch();
  });
  elements.refreshButton.addEventListener('click', refreshSnapshot);
  elements.resetFiltersButton.addEventListener('click', () => {
    document.querySelectorAll('[data-type-filter]').forEach(i => i.checked = true);
    refreshSnapshot();
  });
  elements.depthSelect.addEventListener('change', refreshSnapshot);
  elements.maxNodesSelect.addEventListener('change', refreshSnapshot);

  await refreshSnapshot();
}
