/**
 * file-tree.js - Files page logic
 */
import { qs, fetchJson, escapeHtml, initProjectDropdown, metaRow } from './common.js';

const state = {
  tree: null,
  expanded: new Set(['.']),
  selectedFileNode: null,
};

const elements = {};

function bindElements() {
  [
    'file-root-path', 'file-project-id', 'file-problems-only', 'file-include-hidden',
    'file-filter-input', 'file-refresh-button', 'file-tree-status', 'file-tree-summary',
    'file-tree-root', 'file-details-empty', 'file-details-card', 'file-details-kind',
    'file-details-title', 'file-details-subhead', 'file-details-meta', 'file-details-count',
    'file-violation-list', 'file-dashboard-link',
  ].forEach(id => {
    const key = id.replaceAll('-', ' ').replaceAll(/ ([a-z])/g, (_, letter) => letter.toUpperCase()).replaceAll(' ', '');
    elements[key] = qs(id);
  });
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
  let expandIcon = '';
  if (node.is_dir) {
    expandIcon = expanded ? 'v' : '>';
  }
  const nameText = escapeHtml(node.name);
  const auditDate = node.last_audited ? new Date(node.last_audited).toLocaleDateString() : '';
  const badgeHtml = node.violation_count ? `<span class="tree-badge">${node.violation_count}</span>` : '<span></span>';
  row.innerHTML = `<span>${expandIcon}</span><span class="tree-icon">${node.is_dir ? 'DIR' : 'FILE'}</span><span class="tree-label">${nameText}</span><span class="muted">${auditDate}</span>${badgeHtml}`;
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
    if (!details.violations || details.violations.length === 0) {
      elements.fileViolationList.innerHTML = '<li class="muted">No graph-backed violations recorded for this file.</li>';
    } else {
      details.violations.forEach((violation) => {
        const item = document.createElement('li');
        item.textContent = `${violation.severity} / ${violation.rule} / ${violation.description}`;
        elements.fileViolationList.append(item);
      });
    }
    if (details.graph_node_id) {
      elements.fileDashboardLink.href = `/explore?node=${encodeURIComponent(details.graph_node_id)}`;
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

export async function initFileTree() {
  bindElements();
  await initProjectDropdown('file-project-id', () => loadFileTree());
  
  elements.fileRefreshButton.addEventListener('click', loadFileTree);
  elements.fileFilterInput.addEventListener('input', renderFileTree);
  elements.fileProblemsOnly.addEventListener('change', renderFileTree);
  elements.fileIncludeHidden.addEventListener('change', loadFileTree);

  await loadFileTree();
}