/**
 * X-Copilot Web Dashboard — API Client
 * Mirrors X-Copilot web API client pattern.
 * Communicates with the X-Copilot FastAPI server.
 */

const API_BASE = '';  // Relative — served by same FastAPI server

const headers = {
  'Content-Type': 'application/json',
  'Authorization': 'Bearer admin',
};

export const api = {
  // ── Health ──────────────────────────────────
  health: () => fetch(`${API_BASE}/health`).then(r => r.json()),

  // ── Chat ────────────────────────────────────
  chat: (messages, model = 'gpt-4o-mini', sessionId = null) =>
    fetch(`${API_BASE}/api/chat`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ messages, model, session_id: sessionId }),
    }).then(r => r.json()),

  // ── Sessions ────────────────────────────────
  listSessions: (profile = 'default') =>
    fetch(`${API_BASE}/api/sessions?profile=${profile}`, { headers }).then(r => r.json()),

  getSession: (sessionId) =>
    fetch(`${API_BASE}/api/sessions/${sessionId}`, { headers }).then(r => r.json()),

  createSession: (title = 'New Session') =>
    fetch(`${API_BASE}/api/sessions`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ title }),
    }).then(r => r.json()),

  deleteSession: (sessionId) =>
    fetch(`${API_BASE}/api/sessions/${sessionId}`, { method: 'DELETE', headers }),

  // ── Settings ────────────────────────────────
  getSettings: () =>
    fetch(`${API_BASE}/api/settings`, { headers }).then(r => r.json()),

  updateSettings: (settings) =>
    fetch(`${API_BASE}/api/settings`, {
      method: 'PUT',
      headers,
      body: JSON.stringify(settings),
    }).then(r => r.json()),

  // ── Delegation ──────────────────────────────
  delegate: (goal, options = {}) =>
    fetch(`${API_BASE}/api/delegation/delegate`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ goal, ...options }),
    }).then(r => r.json()),

  delegateBatch: (goals, options = {}) =>
    fetch(`${API_BASE}/api/delegation/delegate/batch`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ goals, ...options }),
    }).then(r => r.json()),

  listTasks: (status = null) => {
    const url = status ? `${API_BASE}/api/delegation/tasks?status=${status}` : `${API_BASE}/api/delegation/tasks`;
    return fetch(url, { headers }).then(r => r.json());
  },

  getTask: (taskId) =>
    fetch(`${API_BASE}/api/delegation/status/${taskId}`, { headers }).then(r => r.json()),

  cancelTask: (taskId) =>
    fetch(`${API_BASE}/api/delegation/tasks/${taskId}`, { method: 'DELETE', headers }).then(r => r.json()),

  delegationSummary: () =>
    fetch(`${API_BASE}/api/delegation/summary`, { headers }).then(r => r.json()),

  delegationHistory: (limit = 50) =>
    fetch(`${API_BASE}/api/delegation/history?limit=${limit}`, { headers }).then(r => r.json()),

  // ── Tools ───────────────────────────────────
  listTools: (toolset = null) => {
    const url = toolset ? `${API_BASE}/api/tools?toolset=${toolset}` : `${API_BASE}/api/tools`;
    return fetch(url, { headers }).then(r => r.json());
  },

  getToolSchemas: () =>
    fetch(`${API_BASE}/api/tools/schemas`, { headers }).then(r => r.json()),

  // ── Memory ──────────────────────────────────
  getMemory: (type = 'all', search = '') =>
    fetch(`${API_BASE}/api/memory?type=${type}&search=${search}`, { headers }).then(r => r.json()),

  clearMemory: () =>
    fetch(`${API_BASE}/api/memory`, { method: 'DELETE', headers }),

  // ── Cron ────────────────────────────────────
  listCronJobs: (profile = 'default') =>
    fetch(`${API_BASE}/api/cron?profile=${profile}`, { headers }).then(r => r.json()),

  createCronJob: (job) =>
    fetch(`${API_BASE}/api/cron`, {
      method: 'POST',
      headers,
      body: JSON.stringify(job),
    }).then(r => r.json()),

  cancelCronJob: (jobId) =>
    fetch(`${API_BASE}/api/cron/${jobId}/cancel`, { method: 'POST', headers }).then(r => r.json()),

  getCronJob: (jobId) =>
    fetch(`${API_BASE}/api/cron/${jobId}`, { headers }).then(r => r.json()),

  // ── Gateway ─────────────────────────────────
  gatewayStatus: () =>
    fetch(`${API_BASE}/api/gateway/status`, { headers }).then(r => r.json()),

  gatewaySessions: (platform = null) => {
    const url = platform ? `${API_BASE}/api/gateway/sessions?platform=${platform}` : `${API_BASE}/api/gateway/sessions`;
    return fetch(url, { headers }).then(r => r.json());
  },

  // ── Chat Stream ─────────────────────────────
  chatStream: async function* (messages, model = 'gpt-4o-mini', sessionId = null) {
    const resp = await fetch(`${API_BASE}/api/chat/stream`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ messages, model, session_id: sessionId }),
    });
    if (!resp.ok) throw new Error(`Stream error: ${resp.status}`);
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let idx;
      while ((idx = buffer.indexOf('\n')) !== -1) {
        const line = buffer.slice(0, idx).trim();
        buffer = buffer.slice(idx + 1);
        if (line) {
          try {
            yield JSON.parse(line);
          } catch {
            // Non-JSON line, skip
          }
        }
      }
    }
  },
};