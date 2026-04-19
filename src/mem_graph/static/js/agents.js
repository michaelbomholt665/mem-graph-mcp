/**
 * agents.js - Agents page logic
 */
import { qs, fetchJson, escapeHtml } from './common.js';

const state = {
  agents: [],
  workflows: [],
  selectedIndex: -1,
};

const elements = {};

function bindElements() {
  [
    'agents-count', 'agents-list', 'agent-detail-panel',
    'workflow-graph-panel', 'workflow-select',
  ].forEach(id => {
    const key = id.replaceAll('-', ' ').replaceAll(/ ([a-z])/g, (_, letter) => letter.toUpperCase()).replaceAll(' ', '');
    elements[key] = qs(id);
  });
}

function renderAgentDetail(agent) {
  if (!agent) {
    elements.agentDetailPanel.innerHTML = '<div class="empty-state">Select an agent to view details.</div>';
    return;
  }
  const roles = (agent.agents || agent.roles || []).map(r => `<span class="tag">${escapeHtml(r)}</span>`).join('');
  const toolsList = (agent.tools || []).map(t => `<li class="muted" style="font-size: 12px; font-family: var(--font-mono);">${escapeHtml(t)}</li>`).join('');
  const promptsHtml = agent.system_prompt
    ? `<pre class="schema-block" style="margin: 0 0 12px; font-size: 11px; white-space: pre-wrap;">${escapeHtml(agent.system_prompt)}</pre>`
    : '<p class="muted" style="font-size: 12px; padding: 8px 0;">No system prompt defined.</p>';
  elements.agentDetailPanel.innerHTML = `
    <div style="padding: 16px; display: flex; flex-direction: column; gap: 16px; height: 100%; overflow-y: auto; box-sizing: border-box;">
      <div>
        <p class="eyebrow" style="margin-bottom: 4px; font-size: 10px; color: var(--muted);">MODULE</p>
        <p style="font-size: 14px; font-weight: 600; color: var(--ink); font-family: var(--font-mono);">${escapeHtml(agent.module)}</p>
        ${agent.description ? `<p class="muted" style="font-size: 12px; margin-top: 4px;">${escapeHtml(agent.description)}</p>` : ''}
        <div class="tag-row" style="margin-top: 8px;">${roles}</div>
      </div>
      ${agent.model ? `<div><p class="eyebrow" style="font-size: 10px; color: var(--muted); margin-bottom: 4px;">MODEL</p><p style="font-family: var(--font-mono); font-size: 12px; color: var(--ink);">${escapeHtml(agent.model)}</p></div>` : ''}
      ${toolsList ? `<div><p class="eyebrow" style="font-size: 10px; color: var(--muted); margin-bottom: 4px;">TOOLS (${(agent.tools || []).length})</p><ul style="padding-left: 14px; margin: 0; display: flex; flex-direction: column; gap: 3px;">${toolsList}</ul></div>` : ''}
      <div>
        <p class="eyebrow" style="font-size: 10px; color: var(--muted); margin-bottom: 6px;">SYSTEM PROMPT</p>
        ${promptsHtml}
      </div>
    </div>`;
}

function renderWorkflowSvg(workflow) {
  const width = 480;
  const rowHeight = 72;
  const height = Math.max(220, workflow.nodes.length * rowHeight + 30);
  const positions = new Map();
  workflow.nodes.forEach((node, index) => {
    positions.set(node, { x: 140 + (index % 2) * 180, y: 35 + index * rowHeight });
  });
  const edgeLines = (workflow.edges || []).map((edge) => {
    const source = positions.get(edge.source);
    const target = positions.get(edge.target);
    if (!source || !target) return '';
    const mx = (source.x + target.x) / 2 + 90;
    const my = (source.y + target.y) / 2 + 16;
    return `<path d="M ${source.x + 90} ${source.y + 16} L ${target.x} ${target.y + 16}" stroke="#1e3040" fill="none" marker-end="url(#arrow)" /><text x="${mx}" y="${my}" fill="#2d3d4d" font-size="10" text-anchor="middle">${escapeHtml(edge.label || '')}</text>`;
  }).join('');
  const nodeBoxes = workflow.nodes.map((node) => {
    const position = positions.get(node);
    return `<g><rect x="${position.x}" y="${position.y}" width="180" height="34" rx="6" fill="#141820" stroke="#1e2a38" /><text x="${position.x + 90}" y="${position.y + 22}" text-anchor="middle" fill="#8ba4b4" font-size="11" font-family="'DM Mono',monospace">${escapeHtml(node)}</text></g>`;
  }).join('');
  return `<svg class="workflow-svg" viewBox="0 0 ${width} ${height}" style="width:100%;height:auto;" role="img" aria-label="${escapeHtml(workflow.display_name)}"><defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0,0 L0,6 L8,3 z" fill="#1e3040" /></marker></defs>${edgeLines}${nodeBoxes}</svg>`;
}

function renderWorkflowGraph(workflow) {
  if (!workflow) {
    elements.workflowGraphPanel.innerHTML = '<div class="empty-state">No workflow selected.</div>';
    return;
  }
  const mermaidBlock = workflow.mermaid
    ? `<details style="padding: 12px 16px 0;"><summary style="font-size: 11px; color: var(--muted); cursor: pointer;">Mermaid source</summary><pre class="schema-block" style="margin-top: 8px; font-size: 10px;">${escapeHtml(workflow.mermaid)}</pre></details>`
    : '';
  elements.workflowGraphPanel.innerHTML = `
    <div style="padding: 16px; overflow-y: auto; height: 100%; box-sizing: border-box;">
      <p style="font-size: 13px; font-weight: 600; color: var(--ink); font-family: var(--font-mono); margin-bottom: 4px;">${escapeHtml(workflow.display_name)}</p>
      ${workflow.description ? `<p class="muted" style="font-size: 12px; margin-bottom: 12px;">${escapeHtml(workflow.description)}</p>` : ''}
      ${renderWorkflowSvg(workflow)}
      ${mermaidBlock}
    </div>`;
}

function populateWorkflowSelect() {
  if (!elements.workflowSelect) return;
  if (!state.workflows.length) {
    elements.workflowSelect.innerHTML = '<option value="">No workflows</option>';
    return;
  }
  elements.workflowSelect.innerHTML = state.workflows
    .map((w, i) => `<option value="${i}">${escapeHtml(w.display_name)}</option>`)
    .join('');
  renderWorkflowGraph(state.workflows[0]);
}

function selectAgent(index) {
  state.selectedIndex = index;
  document.querySelectorAll('#agents-list .agent-item').forEach((el, i) => {
    el.classList.toggle('is-selected', i === index);
  });
  renderAgentDetail(state.agents[index] ?? null);
}

function renderAgents() {
  elements.agentsList.innerHTML = '';
  if (!state.agents.length) {
    elements.agentsList.innerHTML = '<div class="empty-state">No agent modules found.</div>';
    return;
  }
  elements.agentsCount.textContent = String(state.agents.length);
  state.agents.forEach((agent, index) => {
    const item = document.createElement('div');
    item.className = 'agent-item';
    const tags = (agent.agents || agent.roles || []).slice(0, 2).map(r => `<span class="tag">${escapeHtml(r)}</span>`).join('');
    item.innerHTML = `<span class="agent-name">${escapeHtml(agent.module)}</span><span class="agent-tags">${tags}</span>`;
    item.addEventListener('click', () => selectAgent(index));
    elements.agentsList.append(item);
  });
  if (state.agents.length > 0) selectAgent(0);
}

async function loadAgentsAndWorkflows() {
  try {
    const [agentsPayload, workflowPayload] = await Promise.all([
      fetchJson('/dashboard/api/agents'),
      fetchJson('/dashboard/api/workflows'),
    ]);
    state.agents = agentsPayload.agents || [];
    state.workflows = workflowPayload.workflows || [];
    renderAgents();
    populateWorkflowSelect();
  } catch (error) {
    elements.agentsCount.textContent = '0';
    elements.agentDetailPanel.innerHTML = `<div class="empty-state">${escapeHtml(error.message || 'Unable to load agents.')}</div>`;
    elements.workflowGraphPanel.innerHTML = '<div class="empty-state">Unavailable</div>';
  }
}

export async function initAgents() {
  bindElements();
  await loadAgentsAndWorkflows();

  elements.workflowSelect?.addEventListener('change', () => {
    const index = Number.parseInt(elements.workflowSelect.value, 10);
    if (!Number.isNaN(index)) renderWorkflowGraph(state.workflows[index] ?? null);
  });
}
