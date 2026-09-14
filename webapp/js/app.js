/**
 * X-Copilot Web Dashboard — Main App
 * Mirrors X-Copilot web dashboard SPA pattern.
 */

import { api } from './api.js';

// ── State ────────────────────────────────────────
const state = {
  currentView: 'chat',    // chat | tasks | settings | terminal | memory
  sessionId: null,
  messages: [],
  serverRunning: false,
  tasks: [],
  settings: null,
  streaming: false,
};

// ── DOM refs ─────────────────────────────────────
const app = document.getElementById('app');
const chatMessages = document.getElementById('chat-messages');
const chatInput = document.getElementById('chat-input');
const btnSend = document.getElementById('btn-send');
const btnNewChat = document.getElementById('btn-new-chat');
const btnTasks = document.getElementById('btn-tasks');
const btnSettings = document.getElementById('btn-settings');
const btnTerminal = document.getElementById('btn-terminal');
const btnMemory = document.getElementById('btn-memory');
const sidebarSessions = document.getElementById('sidebar-sessions');
const tasksList = document.getElementById('tasks-list');
const serverDot = document.getElementById('server-dot');
const serverStatusText = document.getElementById('server-status-text');
const appVersion = document.getElementById('app-version');

// ── Views ────────────────────────────────────────
function showView(view) {
  state.currentView = view;
  document.querySelectorAll('.view').forEach(el => el.style.display = 'none');
  const viewEl = document.getElementById(`view-${view}`);
  if (viewEl) viewEl.style.display = 'flex';

  // Update sidebar active
  document.querySelectorAll('.sidebar-item').forEach(el => el.classList.remove('active'));
  const activeItem = document.querySelector(`.sidebar-item[data-view="${view}"]`);
  if (activeItem) activeItem.classList.add('active');
}

// ── Server status ─────────────────────────────────
async function checkServerStatus() {
  try {
    const status = await api.health();
    updateServerStatus('running');
    state.serverRunning = true;
    btnSend.disabled = false;
  } catch {
    updateServerStatus('stopped');
    state.serverRunning = false;
    btnSend.disabled = true;
  }
}

function updateServerStatus(status) {
  serverDot.className = 'status-dot';
  if (status === 'running') {
    serverDot.classList.add('running');
    serverStatusText.textContent = 'Server Running';
  } else {
    serverDot.classList.add('stopped');
    serverStatusText.textContent = 'Server Stopped';
  }
}

// ── Chat ──────────────────────────────────────────
function addMessage(role, content) {
  const div = document.createElement('div');
  div.className = `message ${role}`;
  div.textContent = content;
  chatMessages.appendChild(div);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  return div;
}

function addStreamingMessage() {
  const div = document.createElement('div');
  div.className = 'message assistant';
  div.innerHTML = '<span class="cursor"></span>';
  chatMessages.appendChild(div);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  return div;
}

function updateStreamingMessage(div, text) {
  div.innerHTML = text + '<span class="cursor"></span>';
}

async function sendMessage() {
  const text = chatInput.value.trim();
  if (!text || !state.serverRunning || state.streaming) return;

  chatInput.value = '';
  btnSend.disabled = true;
  state.streaming = true;

  addMessage('user', text);
  state.messages.push({ role: 'user', content: text });

  const assistantDiv = addStreamingMessage();

  try {
    const model = state.settings?.model || 'gpt-4o-mini';
    const stream = api.chatStream(state.messages, model, state.sessionId);
    let fullText = '';
    for await (const chunk of stream) {
      const content = chunk.choices?.[0]?.delta?.content || '';
      if (content) {
        fullText += content;
        updateStreamingMessage(assistantDiv, fullText);
      }
    }
    assistantDiv.innerHTML = fullText || 'No response';
    state.messages.push({ role: 'assistant', content: fullText });
  } catch (err) {
    assistantDiv.className = 'message error';
    assistantDiv.innerHTML = `Error: ${err.message}. Is the server running?`;
  }

  state.streaming = false;
  btnSend.disabled = false;
  chatInput.focus();
}

async function newChat() {
  state.sessionId = null;
  state.messages = [];
  chatMessages.innerHTML = '';
  addMessage('system', 'New conversation started');
  chatInput.focus();
  await loadSessions();
}

// ── Sessions sidebar ─────────────────────────────
async function loadSessions() {
  try {
    const data = await api.listSessions();
    sidebarSessions.innerHTML = data.sessions.map(s => `
      <div class="sidebar-item" data-id="${s.id}">
        <span class="session-title">${s.title}</span>
        <span class="session-time">${new Date(s.updated_at).toLocaleDateString()}</span>
      </div>
    `).join('');

    sidebarSessions.querySelectorAll('.sidebar-item').forEach(el => {
      el.addEventListener('click', () => loadSession(el.dataset.id));
    });
  } catch {
    sidebarSessions.innerHTML = '<div style="padding:8px;color:var(--text-muted);font-size:12px;">No sessions</div>';
  }
}

async function loadSession(sessionId) {
  try {
    const session = await api.getSession(sessionId);
    state.sessionId = session.id;
    const messagesResp = await fetch(`http://127.0.0.1:8001/api/sessions/${sessionId}/messages`, {
      headers: { 'Authorization': `Bearer ${AUTH_TOKEN}` },
    });
    const data = await messagesResp.json();
    state.messages = data.messages || [];
    chatMessages.innerHTML = '';
    state.messages.forEach(m => addMessage(m.role, m.content));

    // Update sidebar active
    sidebarSessions.querySelectorAll('.sidebar-item').forEach(el => {
      el.classList.toggle('active', el.dataset.id === sessionId);
    });
  } catch (err) {
    console.error('Failed to load session:', err);
  }
}

// ── Tasks ─────────────────────────────────────────
async function loadTasks() {
  try {
    const data = await api.listTasks();
    state.tasks = data.tasks || [];
    tasksList.innerHTML = state.tasks.map(t => `
      <div class="task-item">
        <div class="goal">${(t.goal || '').substring(0, 50)}</div>
        <div class="meta">${t.task_id} · ${new Date(t.created_at).toLocaleString()}</div>
        <span class="status status-${t.status}">${t.status}</span>
      </div>
    `).join('');
  } catch {
    tasksList.innerHTML = '<div style="padding:8px;color:var(--text-muted);font-size:12px;">No tasks</div>';
  }
}

// ── Settings ──────────────────────────────────────
async function loadSettings() {
  try {
    state.settings = await api.getSettings();
    document.getElementById('setting-model').value = state.settings.model || 'gpt-4o-mini';
    document.getElementById('setting-permission').value = state.settings.permission_mode || 'standard';
    document.getElementById('setting-provider').value = state.settings.provider || 'openai';
  } catch {
    // Use defaults
  }
}

async function saveSettings() {
  const settings = {
    model: document.getElementById('setting-model').value,
    permission_mode: document.getElementById('setting-permission').value,
    provider: document.getElementById('setting-provider').value,
  };
  try {
    await api.updateSettings(settings);
    state.settings = settings;
  } catch (err) {
    console.error('Failed to save settings:', err);
  }
}

// ── Terminal ──────────────────────────────────────
async function loadTerminal() {
  const terminalView = document.getElementById('view-terminal');
  if (!terminalView.querySelector('.terminal-output')) {
    const output = document.createElement('div');
    output.className = 'terminal-output';
    output.id = 'terminal-output';
    output.textContent = 'X-Copilot Terminal\nType commands below...\n\n';
    const input = document.createElement('div');
    input.className = 'terminal-input';
    input.innerHTML = '<input type="text" id="terminal-cmd" placeholder="Enter command..." autocomplete="off">';
    terminalView.appendChild(output);
    terminalView.appendChild(input);

    document.getElementById('terminal-cmd').addEventListener('keydown', async (e) => {
      if (e.key !== 'Enter') return;
      const cmd = e.target.value.trim();
      if (!cmd) return;
      e.target.value = '';
      output.textContent += `$ ${cmd}\n`;
      try {
        const result = await api.runShell(cmd);
        output.textContent += result.output || result.error || 'OK\n';
      } catch (err) {
        output.textContent += `Error: ${err.message}\n`;
      }
      output.textContent += '\n';
      output.scrollTop = output.scrollHeight;
    });
  }
}

// ── Memory ────────────────────────────────────────
async function loadMemory() {
  try {
    const data = await api.getMemory();
    const memoryView = document.getElementById('view-memory');
    memoryView.innerHTML = `
      <div class="memory-stats">
        <div class="memory-stat"><div class="value">${data.session_count || 0}</div><div class="label">Sessions</div></div>
        <div class="memory-stat"><div class="value">${data.episodic_count || 0}</div><div class="label">Episodic</div></div>
        <div class="memory-stat"><div class="value">${data.semantic_count || 0}</div><div class="label">Semantic</div></div>
        <div class="memory-stat"><div class="value">${data.procedural_count || 0}</div><div class="label">Skills</div></div>
      </div>
      <h3 style="margin-bottom:8px;">Recent Events</h3>
      <div class="memory-events">
        ${(data.events || []).map(e => `
          <div class="memory-event">
            <div>${e.type}: ${JSON.stringify(e.payload).substring(0, 80)}</div>
            <div class="timestamp">${new Date(e.timestamp).toLocaleString()}</div>
          </div>
        `).join('')}
      </div>
    `;
  } catch (err) {
    console.error('Failed to load memory:', err);
  }
}

// ── Event listeners ──────────────────────────────
btnSend.addEventListener('click', sendMessage);
chatInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

btnNewChat.addEventListener('click', newChat);

btnTasks.addEventListener('click', () => {
  showView('tasks');
  loadTasks();
});

btnSettings.addEventListener('click', () => {
  showView('settings');
  loadSettings();
});

btnTerminal.addEventListener('click', () => {
  showView('terminal');
  loadTerminal();
});

btnMemory.addEventListener('click', () => {
  showView('memory');
  loadMemory();
});

// Settings save
document.getElementById('btn-settings-save')?.addEventListener('click', saveSettings);
document.getElementById('btn-settings-cancel')?.addEventListener('click', () => showView('chat'));

// ── Init ──────────────────────────────────────────
async function init() {
  try {
    const version = await api.health();
    appVersion.textContent = 'v0.1.1';
  } catch {
    appVersion.textContent = 'v0.1.1';
  }

  await checkServerStatus();
  await loadSessions();
  chatInput.focus();

  // Periodic server status check
  setInterval(checkServerStatus, 10000);
}

init();