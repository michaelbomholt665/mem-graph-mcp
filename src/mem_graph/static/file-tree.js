(() => {
  const state = {
    tree: null,
    selectedPath: null,
    expanded: new Set(),
    selectedNode: null,
  };

  const elements = {};

  function qs(id) {
    return document.getElementById(id);
  }

  async function fetchJson(url) {
    const response = await fetch(url);
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.error || `Request failed with ${response.status}`);
    }
    return response.json();
  }

  function treeParams() {
    const params = new URLSearchParams();
    const rootPath = elements.rootPath.value.trim();
    const projectId = elements.projectId.value.trim();
    if (rootPath) {
      params.set('root_path', rootPath);
    }
    if (projectId) {
      params.set('project_id', projectId);
    }
    if (elements.includeHidden.checked) {
      params.set('include_hidden', 'true');
    }
    return params;
  }

  function formatTimestamp(value) {
    if (!value) {
      return 'Unknown';
    }
    return new Date(value).toLocaleString();
  }

  function setStatus(text) {
    elements.treeStatus.textContent = text;
  }

  function summarizeTree(node) {
    let files = 0;
    let directories = 0;
    const stack = [node];
    while (stack.length > 0) {
      const current = stack.pop();
      if (current.is_dir) {
        directories += 1;
        (current.children || []).forEach((child) => stack.push(child));
      } else {
        files += 1;
      }
    }
    return `${directories} directories · ${files} files`;
  }

  function nodeMatchesFilter(node, query, problemsOnly) {
    const selfMatches = (!problemsOnly || node.violation_count > 0)
      && (!query || node.relative_path.toLowerCase().includes(query) || node.name.toLowerCase().includes(query));
    if (selfMatches) {
      return true;
    }
    return (node.children || []).some((child) => nodeMatchesFilter(child, query, problemsOnly));
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

  function renderBadge(count) {
    if (!count) {
      return null;
    }
    const badge = document.createElement('span');
    badge.className = 'tree-badge';
    badge.textContent = String(count);
    return badge;
  }

  function renderTreeNode(node, depth = 0) {
    const query = elements.filterInput.value.trim().toLowerCase();
    const problemsOnly = elements.problemsOnly.checked;
    if (!nodeMatchesFilter(node, query, problemsOnly)) {
      return null;
    }

    const wrapper = document.createElement('div');
    wrapper.className = 'tree-node';

    const row = document.createElement('button');
    row.type = 'button';
    row.className = 'tree-row';
    row.style.paddingLeft = `${12 + depth * 18}px`;
    if (state.selectedPath === node.path) {
      row.classList.add('is-selected');
    }

    const toggle = document.createElement('span');
    toggle.className = 'tree-toggle';
    if (node.is_dir) {
      const expanded = state.expanded.has(node.relative_path);
      toggle.textContent = expanded ? '▾' : '▸';
      toggle.addEventListener('click', (event) => {
        event.stopPropagation();
        if (expanded) {
          state.expanded.delete(node.relative_path);
        } else {
          state.expanded.add(node.relative_path);
        }
        renderTree();
      });
    }

    const icon = document.createElement('span');
    icon.className = 'tree-icon';
    icon.textContent = node.is_dir ? 'DIR' : 'FILE';

    const label = document.createElement('span');
    label.className = 'tree-label';
    label.textContent = node.name;

    const meta = document.createElement('span');
    meta.className = 'tree-meta';
    meta.textContent = node.last_audited ? `Audited ${new Date(node.last_audited).toLocaleDateString()}` : '';

    const badge = renderBadge(node.violation_count);

    row.append(toggle, icon, label, meta);
    if (badge) {
      row.append(badge);
    }
    row.addEventListener('click', async () => {
      state.selectedPath = node.path;
      state.selectedNode = node;
      ensureExpanded(node.relative_path);
      renderTree();
      await renderDetails(node);
    });

    wrapper.append(row);

    if (node.is_dir && state.expanded.has(node.relative_path)) {
      (node.children || []).forEach((child) => {
        const childNode = renderTreeNode(child, depth + 1);
        if (childNode) {
          wrapper.append(childNode);
        }
      });
    }

    return wrapper;
  }

  function renderTree() {
    elements.treeRoot.innerHTML = '';
    if (!state.tree) {
      return;
    }
    const tree = renderTreeNode(state.tree, 0);
    if (tree) {
      elements.treeRoot.append(tree);
    }
  }

  function metaRow(label, value) {
    const row = document.createElement('div');
    const term = document.createElement('dt');
    const description = document.createElement('dd');
    term.textContent = label;
    description.textContent = value;
    row.append(term, description);
    return row;
  }

  function renderDirectoryDetails(node) {
    elements.detailsKind.textContent = 'Directory';
    elements.detailsTitle.textContent = node.relative_path === '.' ? node.path : node.relative_path;
    elements.detailsMeta.innerHTML = '';
    elements.detailsMeta.append(
      metaRow('Absolute Path', node.path),
      metaRow('Open Violations', String(node.violation_count || 0)),
      metaRow('Last Audited', formatTimestamp(node.last_audited)),
      metaRow('Violation Types', node.violation_types?.join(', ') || 'None'),
    );
    elements.detailsCount.textContent = `${node.violation_count || 0} open issues in this branch`;
    elements.violationList.innerHTML = '<li class="muted">Directory summaries aggregate child file data. Select a file for detailed findings.</li>';
    elements.dashboardLink.classList.add('is-hidden');
  }

  async function renderFileDetails(node) {
    const params = treeParams();
    params.set('file_path', node.relative_path);
    const details = await fetchJson(`/file-tree/api/violations?${params.toString()}`);

    elements.detailsKind.textContent = 'File';
    elements.detailsTitle.textContent = details.relative_path;
    elements.detailsMeta.innerHTML = '';
    elements.detailsMeta.append(
      metaRow('Absolute Path', details.absolute_path),
      metaRow('Open Violations', String(details.violation_count || 0)),
      metaRow('Last Audited', formatTimestamp(details.last_audited)),
      metaRow('Violation Types', details.violation_types?.join(', ') || 'None'),
    );
    elements.detailsCount.textContent = `${details.total} total findings recorded`;

    elements.violationList.innerHTML = '';
    if (!details.violations || details.violations.length === 0) {
      elements.violationList.innerHTML = '<li class="muted">No graph-backed violations recorded for this file.</li>';
    } else {
      details.violations.forEach((violation) => {
        const item = document.createElement('li');
        item.className = `violation-item severity-${violation.severity.toLowerCase()}`;
        item.innerHTML = `
          <div class="violation-topline">
            <strong>${violation.rule}</strong>
            <span class="severity-pill">${violation.severity}</span>
          </div>
          <p>${violation.description}</p>
          <p class="muted">${violation.status} · line ${violation.line_start || 'n/a'} · detected ${formatTimestamp(violation.detected_at)}</p>
        `;
        elements.violationList.append(item);
      });
    }

    if (details.graph_node_id) {
      elements.dashboardLink.href = `/dashboard?node=${encodeURIComponent(details.graph_node_id)}`;
      elements.dashboardLink.classList.remove('is-hidden');
    } else {
      elements.dashboardLink.classList.add('is-hidden');
    }
  }

  async function renderDetails(node) {
    elements.detailsEmpty.classList.add('is-hidden');
    elements.detailsCard.classList.remove('is-hidden');
    elements.detailsSubhead.textContent = node.relative_path === '.' ? node.path : node.relative_path;

    if (node.is_dir) {
      renderDirectoryDetails(node);
      return;
    }

    try {
      await renderFileDetails(node);
    } catch (error) {
      elements.detailsMeta.innerHTML = '';
      elements.detailsCount.textContent = 'Unable to load file detail';
      elements.violationList.innerHTML = `<li class="muted">${error.message || 'Failed to load file details.'}</li>`;
    }
  }

  async function loadTree() {
    try {
      setStatus('Refreshing file tree…');
      const tree = await fetchJson(`/file-tree/api/tree?${treeParams().toString()}`);
      state.tree = tree;
      state.expanded = new Set(['.']);
      ensureExpanded(tree.relative_path);
      elements.treeSummary.textContent = summarizeTree(tree);
      setStatus('File tree ready.');
      renderTree();
      if (state.selectedNode) {
        await renderDetails(state.selectedNode);
      }
    } catch (error) {
      state.tree = null;
      elements.treeRoot.innerHTML = `<p class="muted">${error.message || 'Failed to load the file tree.'}</p>`;
      elements.treeSummary.textContent = 'Tree unavailable';
      setStatus(error.message || 'Failed to load the file tree.');
    }
  }

  function initializeFromLocation() {
    const params = new URLSearchParams(globalThis.location.search);
    elements.rootPath.value = params.get('root_path') || '';
    elements.projectId.value = params.get('project_id') || '';
  }

  async function initialize() {
    elements.rootPath = qs('root-path');
    elements.projectId = qs('project-id');
    elements.problemsOnly = qs('problems-only');
    elements.includeHidden = qs('include-hidden');
    elements.filterInput = qs('filter-input');
    elements.refreshButton = qs('refresh-button');
    elements.treeStatus = qs('tree-status');
    elements.treeSummary = qs('tree-summary');
    elements.treeRoot = qs('tree-root');
    elements.detailsEmpty = qs('details-empty');
    elements.detailsCard = qs('details-card');
    elements.detailsKind = qs('details-kind');
    elements.detailsTitle = qs('details-title');
    elements.detailsSubhead = qs('details-subhead');
    elements.detailsMeta = qs('details-meta');
    elements.detailsCount = qs('details-count');
    elements.violationList = qs('violation-list');
    elements.dashboardLink = qs('dashboard-link');

    initializeFromLocation();

    elements.refreshButton.addEventListener('click', loadTree);
    elements.filterInput.addEventListener('input', renderTree);
    elements.problemsOnly.addEventListener('change', renderTree);
    elements.includeHidden.addEventListener('change', loadTree);
    elements.rootPath.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') {
        loadTree();
      }
    });
    elements.projectId.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') {
        loadTree();
      }
    });

    await loadTree();
  }

  initialize().catch((error) => {
    const root = qs('tree-root');
    if (root) {
      root.innerHTML = `<p class="muted">${error.message || 'Failed to initialize the explorer.'}</p>`;
    }
  });
})();