/**
 * tools.js - Tools page logic
 */
import { qs, fetchJson, escapeHtml } from './common.js';

const state = {
  tools: [],
  currentNs: 'all',
};

const elements = {};

const NS_PILL_MAP = {
  audit: 'ns-audit',
  background: 'ns-bg',
  bg: 'ns-bg',
  core: 'ns-core',
  filesystem: 'ns-fs',
  fs: 'ns-fs',
  graph: 'ns-graph',
  memory: 'ns-memory',
};

function nsPillClass(namespace) {
  const key = namespace.toLowerCase().trim();
  for (const [fragment, cls] of Object.entries(NS_PILL_MAP)) {
    if (key === fragment || key.includes(fragment)) return cls;
  }
  return 'ns-default';
}

function renderNsChips() {
  if (!elements.toolsNsBar) return;
  const namespaces = state.tools.map(g => g.namespace).filter(Boolean);
  const chips = ['all', ...namespaces].map(ns => {
    const active = state.currentNs === ns ? ' is-active' : '';
    return `<button class="ns-chip${active}" data-ns="${escapeHtml(ns)}" type="button">${escapeHtml(ns)}</button>`;
  });
  elements.toolsNsBar.innerHTML = chips.join('');
  elements.toolsNsBar.querySelectorAll('.ns-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      state.currentNs = chip.dataset.ns;
      renderNsChips();
      renderTools();
    });
  });
}

function renderTools() {
  const query = elements.toolsFilter?.value.trim().toLowerCase() ?? '';
  let totalCount = 0;
  const rows = [];

  state.tools.forEach((group) => {
    if (state.currentNs !== 'all' && group.namespace !== state.currentNs) return;
    (group.tools || []).forEach((tool) => {
      const haystack = `${tool.name} ${tool.description} ${group.namespace}`.toLowerCase();
      if (!query || haystack.includes(query)) {
        totalCount += 1;
        const pillClass = nsPillClass(group.namespace);
        const schemaJson = escapeHtml(JSON.stringify(tool.input_schema || {}, null, 2));
        const rowId = `schema-${escapeHtml(group.namespace)}-${escapeHtml(tool.name)}`.replaceAll(/[^a-zA-Z0-9-]/g, '-');
        rows.push(`
          <tr>
            <td><span class="ns-pill ${pillClass}">${escapeHtml(group.namespace)}</span></td>
            <td class="tool-name-cell">${escapeHtml(tool.name)}</td>
            <td class="tool-desc-cell">${escapeHtml(tool.description || '')}</td>
            <td>
              <button class="secondary-button" type="button" aria-expanded="false" aria-controls="${rowId}"
                style="padding: 2px 8px; font-size: 10px;"
                onclick="const r=document.getElementById('${rowId}');const show=r.style.display==='none'||!r.style.display;r.style.display=show?'table-row':'none';this.textContent=show?'hide':'show';this.setAttribute('aria-expanded',show);">
                show
              </button>
            </td>
          </tr>
          <tr id="${rowId}" class="expanded-schema-row" style="display:none;">
            <td colspan="4"><pre class="schema-block">${schemaJson}</pre></td>
          </tr>`);
      }
    });
  });

  if (elements.toolsCount) elements.toolsCount.textContent = `${totalCount} tool${totalCount !== 1 ? 's' : ''}`;

  const tbody = elements.toolsTbody;
  if (!tbody) return;
  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="4" style="text-align:center; padding: 24px; color: var(--muted); font-size: 12px;">No matching tools.</td></tr>`;
    return;
  }
  tbody.innerHTML = rows.join('');
}

async function loadTools() {
  try {
    const payload = await fetchJson('/dashboard/api/tools');
    state.tools = payload.namespaces || [];
    renderNsChips();
    renderTools();
  } catch (error) {
    const tbody = elements.toolsTbody;
    if (tbody) tbody.innerHTML = `<tr><td colspan="4" style="padding: 24px; color: var(--muted);">${escapeHtml(error.message || 'Unable to load tools.')}</td></tr>`;
  }
}

export async function initTools() {
  [
    'tools-count', 'tools-filter', 'tools-ns-bar', 'tools-tbody',
  ].forEach(id => {
    const key = id.replaceAll('-', ' ').replaceAll(/ ([a-z])/g, (_, letter) => letter.toUpperCase()).replaceAll(' ', '');
    elements[key] = qs(id);
  });

  await loadTools();

  elements.toolsFilter?.addEventListener('input', renderTools);
}
