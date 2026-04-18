/**
 * dashboard.js - Overview page logic
 */
import { qs, fetchJson, renderStats, tableHtml, text, escapeHtml } from './common.js';

const elements = {};

function bindElements() {
  [
    'metric-health', 'metric-db', 'metric-nodes', 'metric-edges', 'metric-uptime',
    'task-status-list', 'violation-severity-list', 'recent-evals',
    'refresh-all-button', 'server-version', 'status-text',
    'graph-snapshot-label', 'agent-list-preview',
  ].forEach(id => {
    const key = id.replaceAll('-', ' ').replaceAll(/ ([a-z])/g, (_, letter) => letter.toUpperCase()).replaceAll(' ', '');
    elements[key] = qs(id);
  });
}

function renderRecentEvals(evals) {
  const rows = evals.slice(0, 5);
  if (!rows.length) {
    elements.recentEvals.innerHTML = '<p class="muted" style="padding: 12px 16px; font-size: 12px;">No eval runs recorded.</p>';
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

function renderAgentPreview(agents) {
  if (!elements.agentListPreview) return;
  if (!agents.length) {
    elements.agentListPreview.innerHTML = '<p class="muted" style="padding: 12px 16px; font-size: 12px;">No agent modules found.</p>';
    return;
  }
  const items = agents.slice(0, 6).map(agent => {
    const roles = (agent.agents || agent.roles || []).slice(0, 3).map(r => `<span class="tag">${escapeHtml(r)}</span>`).join('');
    return `<div class="agent-item"><span class="agent-name">${escapeHtml(agent.module)}</span><span class="agent-tags">${roles}</span></div>`;
  }).join('');
  elements.agentListPreview.innerHTML = items;
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

    if (elements.statusText) {
      elements.statusText.textContent = payload.status === 'ok' ? 'system healthy' : payload.status || 'unknown';
    }
    if (elements.graphSnapshotLabel) {
      elements.graphSnapshotLabel.textContent = `${telemetry.node_count || 0} nodes · ${telemetry.edge_count || 0} edges`;
    }

    renderStats(elements.taskStatusList, telemetry.task_status);
    renderStats(elements.violationSeverityList, telemetry.violation_severity);
  } catch (error) {
    elements.metricHealth.textContent = 'degraded';
    elements.metricDb.textContent = error.message || 'System unavailable';
    if (elements.statusText) elements.statusText.textContent = 'system degraded';
  }
}

async function loadRecentEvals() {
  try {
    const payload = await fetchJson('/dashboard/api/evals?limit=5');
    renderRecentEvals(payload.evals || []);
  } catch (error) {
    console.warn('[Dashboard] Failed to load recent evals:', error);
    elements.recentEvals.innerHTML = '<p class="muted" style="padding: 12px 16px; font-size: 12px;">Eval data unavailable.</p>';
  }
}

async function loadAgentPreview() {
  try {
    const payload = await fetchJson('/dashboard/api/agents');
    renderAgentPreview(payload.agents || []);
  } catch (error) {
    console.warn('[Dashboard] Failed to load agent preview:', error);
    if (elements.agentListPreview) {
      elements.agentListPreview.innerHTML = '<p class="muted" style="padding: 12px 16px; font-size: 12px;">Agent data unavailable.</p>';
    }
  }
}

export async function initDashboard() {
  bindElements();
  await Promise.all([loadSystem(), loadRecentEvals(), loadAgentPreview()]);

  elements.refreshAllButton.addEventListener('click', async () => {
    elements.refreshAllButton.disabled = true;
    await Promise.all([loadSystem(), loadRecentEvals(), loadAgentPreview()]);
    elements.refreshAllButton.disabled = false;
  });
}
