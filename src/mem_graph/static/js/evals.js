/**
 * evals.js - Evals page logic
 */
import { qs, fetchJson, text, escapeHtml, initProjectDropdown } from './common.js';

const state = {
  evals: [],
};

const elements = {};

function bindElements() {
  [
    'evals-status', 'evals-project-id', 'evals-refresh-button', 'evals-table',
    'evals-run-count', 'evals-run-list',
    'eval-total-runs', 'eval-pass-rate', 'eval-avg-duration',
    'eval-timeline-bars', 'eval-timeline-empty',
  ].forEach(id => {
    const key = id.replaceAll('-', ' ').replaceAll(/ ([a-z])/g, (_, letter) => letter.toUpperCase()).replaceAll(' ', '');
    elements[key] = qs(id);
  });
}

function renderEvalMetrics() {
  const total = state.evals.length;
  const passed = state.evals.filter(r => r.total_suites === r.passed_suites).length;
  const passRate = total > 0 ? Math.round((passed / total) * 100) : 0;
  const avgDuration = total > 0
    ? Math.round(state.evals.reduce((sum, r) => sum + (r.total_duration_ms || 0), 0) / total)
    : 0;

  if (elements.evalTotalRuns) elements.evalTotalRuns.textContent = String(total);
  if (elements.evalPassRate) elements.evalPassRate.textContent = total > 0 ? `${passRate}%` : '—';
  if (elements.evalAvgDuration) elements.evalAvgDuration.textContent = total > 0 ? `${avgDuration}ms` : '—';
}

function renderEvalTimeline() {
  if (!elements.evalTimelineBars || !elements.evalTimelineEmpty) return;
  if (!state.evals.length) {
    elements.evalTimelineBars.style.display = 'none';
    elements.evalTimelineEmpty.style.display = 'flex';
    return;
  }
  elements.evalTimelineEmpty.style.display = 'none';
  elements.evalTimelineBars.style.display = 'flex';
  const recent = state.evals.slice(-20);
  const maxDuration = Math.max(...recent.map(r => r.total_duration_ms || 1), 1);
  elements.evalTimelineBars.innerHTML = recent.map(run => {
    const pass = run.total_suites === run.passed_suites;
    const heightPct = Math.max(8, Math.round(((run.total_duration_ms || 0) / maxDuration) * 100));
    const color = pass ? '#00d4a8' : '#ff4d4d';
    const label = escapeHtml(text(run.started_at, 'unknown'));
    return `<div class="timeline-bar" title="${label}" style="height:${heightPct}%;background:${color};opacity:0.7;flex:1;min-width:6px;max-width:24px;border-radius:2px 2px 0 0;"></div>`;
  }).join('');
}

function renderSidebarList() {
  if (!elements.evalsRunList) return;
  if (!state.evals.length) {
    elements.evalsRunList.innerHTML = `
      <div class="eval-empty-state">
        <div class="eval-empty-icon">
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
            <rect x="4" y="5" width="12" height="2" rx="1" fill="#2d3d4d"/>
            <rect x="4" y="9" width="9" height="2" rx="1" fill="#2d3d4d"/>
            <rect x="4" y="13" width="5" height="2" rx="1" fill="#2d3d4d"/>
          </svg>
        </div>
        <p class="eval-empty-title">No eval runs yet</p>
        <p class="eval-empty-sub">Runs appear here after you execute an evaluation.</p>
      </div>`;
    return;
  }
  elements.evalsRunList.innerHTML = state.evals.map((run, i) => {
    const pass = run.total_suites === run.passed_suites;
    const statusClass = pass ? 'eval-run-pass' : 'eval-run-fail';
    const statusText = pass ? 'PASS' : 'FAIL';
    return `<div class="eval-run-item ${statusClass}" data-index="${i}">
      <span class="eval-run-status">${statusText}</span>
      <span class="eval-run-label">${escapeHtml(text(run.label || run.mode, 'run'))}</span>
      <span class="eval-run-time muted">${escapeHtml(text(run.started_at, ''))}</span>
    </div>`;
  }).join('');
  if (elements.evalsRunCount) elements.evalsRunCount.textContent = `${state.evals.length} run${state.evals.length !== 1 ? 's' : ''}`;
}

function renderEvals() {
  if (!state.evals.length) {
    if (elements.evalsTable) elements.evalsTable.innerHTML = '<p class="muted" style="padding: 16px; font-size: 12px;">No eval runs recorded.</p>';
    return;
  }
  const evalsHtml = state.evals.map((row) => {
    const statusText = row.total_suites === row.passed_suites ? 'PASS' : 'FAIL';
    const detailsText = escapeHtml(text(row.started_at, 'Details'));
    const summaryText = escapeHtml(text(row.summary));
    const detailsHtml = `<details><summary>${detailsText}</summary><pre class="schema-block" style="font-size:10px;">${summaryText}</pre></details>`;
    const statusCls = row.total_suites === row.passed_suites ? 'dot-done' : 'dot-fail';
    return `<tr>
      <td><span class="task-dot ${statusCls}" style="display:inline-block;margin-right:4px;"></span>${statusText}</td>
      <td>${escapeHtml(text(row.mode))}</td>
      <td>${escapeHtml(text(row.label))}</td>
      <td>${row.passed_suites}/${row.total_suites}</td>
      <td style="font-family:var(--font-mono);font-size:11px;">${Math.round(row.total_duration_ms || 0)}ms</td>
      <td>${escapeHtml(text(row.trigger))}</td>
      <td style="font-family:var(--font-mono);font-size:11px;">${escapeHtml(text(row.project_id))}</td>
      <td>${detailsHtml}</td>
    </tr>`;
  }).join('');
  if (elements.evalsTable) {
    elements.evalsTable.innerHTML = `<table><thead><tr><th>Status</th><th>Mode</th><th>Label</th><th>Suites</th><th>Duration</th><th>Trigger</th><th>Project</th><th>Summary</th></tr></thead><tbody>${evalsHtml}</tbody></table>`;
  }
}

async function loadEvals() {
  try {
    const params = new URLSearchParams({ limit: '20' });
    const projectId = elements.evalsProjectId?.value.trim();
    if (projectId) params.set('project_id', projectId);
    const payload = await fetchJson(`/dashboard/api/evals?${params.toString()}`);
    state.evals = payload.evals || [];
    if (elements.evalsStatus) elements.evalsStatus.textContent = `${state.evals.length} eval runs`;
    renderEvalMetrics();
    renderEvalTimeline();
    renderSidebarList();
    renderEvals();
  } catch (error) {
    if (elements.evalsStatus) elements.evalsStatus.textContent = error.message || 'Unable to load evals.';
  }
}

export async function initEvals() {
  bindElements();
  await initProjectDropdown('evals-project-id', () => loadEvals());

  elements.evalsRefreshButton?.addEventListener('click', loadEvals);

  await loadEvals();
}
