/**
 * X-Copilot Desktop App — Preload Script
 *
 * Exposes safe IPC APIs to the renderer process.
 * Uses contextBridge for security (nodeIntegration: false).
 */

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('xcopilot', {
  // Server status
  serverStatus: () => ipcRenderer.invoke('server:status'),
  serverStart: () => ipcRenderer.invoke('server:start'),
  serverStop: () => ipcRenderer.invoke('server:stop'),

  // App info
  version: () => ipcRenderer.invoke('app:version'),

  // Dialogs
  openFile: (options) => ipcRenderer.invoke('dialog:open', options),
  saveFile: (options) => ipcRenderer.invoke('dialog:save', options),

  // Server events
  onServerStatus: (callback) => {
    ipcRenderer.on('server-status', (event, data) => callback(data));
  },

  // Chat API
  chat: (messages, model = 'gpt-4o-mini') =>
    ipcRenderer.invoke('api:chat', { messages, model }),

  chatStream: (messages, model = 'gpt-4o-mini') => {
    return new Promise((resolve, reject) => {
      const chunks = [];
      ipcRenderer.invoke('api:chat-stream', { messages, model }).then((stream) => {
        stream.on('data', (chunk) => {
          chunks.push(chunk);
          if (typeof chunk === 'string') {
            try {
              const parsed = JSON.parse(chunk);
              if (parsed.choices?.[0]?.delta?.content) {
                const cb = window._streamCallback;
                if (cb) cb(parsed.choices[0].delta.content);
              }
            } catch {
              // Non-JSON chunk, ignore
            }
          }
        });
        stream.on('end', () => resolve(chunks.join('')));
        stream.on('error', reject);
      }).catch(reject);
    });
  },

  // Delegation API
  delegate: (goal, options = {}) =>
    ipcRenderer.invoke('api:delegate', { goal, ...options }),

  delegateBatch: (goals, options = {}) =>
    ipcRenderer.invoke('api:delegate-batch', { goals, ...options }),

  // Tasks API
  listTasks: () => ipcRenderer.invoke('api:tasks'),
  taskStatus: (taskId) => ipcRenderer.invoke('api:task-status', taskId),
  cancelTask: (taskId) => ipcRenderer.invoke('api:task-cancel', taskId),

  // Memory API
  memory: (type = 'all', search = '') =>
    ipcRenderer.invoke('api:memory', { type, search }),

  // Settings API
  getSettings: () => ipcRenderer.invoke('api:settings'),
  updateSettings: (settings) => ipcRenderer.invoke('api:settings-update', settings),

  // Cron API
  listCronJobs: () => ipcRenderer.invoke('api:cron'),
  createCronJob: (job) => ipcRenderer.invoke('api:cron-create', job),
  cancelCronJob: (jobId) => ipcRenderer.invoke('api:cron-cancel', jobId),
});