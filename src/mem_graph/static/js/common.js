/**
 * common.js - Shared utilities for Memory Atlas pages
 */

export const state = {
  styles: {},
};

export function qs(id) {
  return document.getElementById(id);
}

export function text(value, fallback = '') {
  if (value === null || value === undefined || value === '') {
    return fallback;
  }
  return String(value);
}

export async function fetchJson(url) {
  const response = await fetch(url);
  let payload = {};
  
  try {
    payload = await response.json().catch(() => ({}));
  } catch (e) {
    console.warn('[fetchJson] Could not parse response as JSON:', e);
  }
  
  if (!response.ok) {
    throw new Error(payload.error || payload.status || `Request failed with ${response.status}`);
  }
  return payload;
}

export function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem('memory-atlas-theme', theme);
  const toggle = qs('theme-toggle');
  if (toggle) {
    toggle.textContent = theme === 'dark' ? '☀' : '🌙';
  }
}

export function initTheme() {
  const stored = localStorage.getItem('memory-atlas-theme');
  const fallback = globalThis.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  applyTheme(stored || fallback);
  
  const toggle = qs('theme-toggle');
  if (toggle) {
    toggle.addEventListener('click', () => {
      applyTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark');
      // If there's a graph, we might want to refresh it, but that's page-specific
      if (globalThis.onThemeChange) globalThis.onThemeChange();
    });
  }
}

export function metaRow(label, value) {
  const row = document.createElement('div');
  const term = document.createElement('dt');
  const description = document.createElement('dd');
  term.textContent = label;
  description.textContent = text(value, 'None');
  row.append(term, description);
  return row;
}

export function escapeHtml(value) {
  return text(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

export async function initProjectDropdown(elementId, callback) {
  const element = qs(elementId);
  if (!element) return;

  try {
    const projects = await fetchJson('/dashboard/api/projects');
    element.innerHTML = projects.map(p =>
      `<option value="${p.id}">${p.name}</option>`
    ).join('');

    const params = new URLSearchParams(globalThis.location.search);
    const saved = params.get('project_id') || localStorage.getItem(`memgraph-project-${elementId}`);

    if (saved) {
      element.value = saved;
    }
  } catch (err) {
    console.warn('[Common] Failed to load projects:', err);
  }

  element.addEventListener('change', () => {
    localStorage.setItem(`memgraph-project-${elementId}`, element.value);
    const params = new URLSearchParams(globalThis.location.search);
    params.set('project_id', element.value);
    globalThis.location.search = params.toString();
    if (callback) callback(element.value);
  });
}

export async function loadStyles() {
  try {
    const payload = await fetchJson('/dashboard/api/styles');
    state.styles = payload.styles || {};
    return state.styles;
  } catch (err) {
    console.warn('[Common] Failed to load styles:', err);
    return {};
  }
}

export function styleFor(type) {
  return state.styles[type] || { color: '#116d72', size: 12 };
}

export function tableHtml(headers, rows) {
  const headerHtml = headers.map((header) => `<th>${escapeHtml(header)}</th>`).join('');
  const rowsHtml = rows.map((row) => {
    const cellsHtml = row.map((cell) => `<td>${escapeHtml(text(cell))}</td>`).join('');
    return `<tr>${cellsHtml}</tr>`;
  }).join('');
  return `<table><thead><tr>${headerHtml}</tr></thead><tbody>${rowsHtml}</tbody></table>`;
}

function dotClassForLabel(label) {
  const l = label.toLowerCase();
  if (/done|complet|pass/.test(l)) return 'dot-done';
  if (/fail|error|crit/.test(l)) return 'dot-fail';
  if (/run|activ|progress/.test(l)) return 'dot-run';
  if (/pend|wait|queue/.test(l)) return 'dot-pend';
  if (/warn/.test(l)) return 'dot-warn';
  return 'dot-default';
}

export function renderStats(container, stats) {
  container.innerHTML = '';
  const entries = Object.entries(stats || {});
  if (!entries.length) {
    container.innerHTML = '<p class="muted" style="padding: 12px 16px; font-size: 12px;">No records.</p>';
    return;
  }
  entries.forEach(([label, count]) => {
    const row = document.createElement('div');
    row.className = 'task-row';
    row.innerHTML = `<div class="task-label"><span class="task-dot ${dotClassForLabel(label)}"></span><span>${escapeHtml(label)}</span></div><strong>${escapeHtml(String(count))}</strong>`;
    container.append(row);
  });
}

export function bindNavigation() {
  // Current page highlighting
  const currentPath = globalThis.location.pathname;
  document.querySelectorAll('.nav-item').forEach(item => {
    const href = item.getAttribute('href');
    if (href === currentPath || (currentPath === '/' && href === '/dashboard')) {
      item.classList.add('is-active');
    }
  });
}

export async function initCommon() {
  initTheme();
  bindNavigation();
  await loadStyles();
}
