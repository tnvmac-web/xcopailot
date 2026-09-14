/**
 * X-Copilot Electron Desktop App — Main Process
 *
 * Manages the X-Copilot FastAPI server lifecycle and the BrowserWindow.
 * In dev mode: auto-starts the server from the project root.
 * In installed mode: connects to an already-running server.
 */

const { app, BrowserWindow, Tray, Menu, ipcMain, dialog } = require('electron');
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

let mainWindow = null;
let serverProcess = null;
let tray = null;

const SERVER_HOST = '127.0.0.1';
const SERVER_PORT = 8001;
const SERVER_URL = `http://${SERVER_HOST}:${SERVER_PORT}`;

// ── Server lifecycle ────────────────────────────────────

function findServerScript() {
  const appPath = app.getAppPath();
  const isDev = process.argv.includes('--dev') || !app.isPackaged;

  if (isDev) {
    // Dev mode: server is in the project root
    const candidates = [
      path.join(appPath, '..', 'server', 'main.py'),
      path.join(appPath, '..', '..', 'server', 'main.py'),
      path.join(appPath, 'server', 'main.py'),
    ];
    for (const p of candidates) {
      if (fs.existsSync(p)) return p;
    }
  } else {
    // Installed mode: server is NOT bundled — user must start it separately
    return null;
  }
  return null;
}

function findPython() {
  const isDev = process.argv.includes('--dev') || !app.isPackaged;

  if (isDev) {
    // Dev mode: try X-Copilot venv, then system Python, then PATH
    const appPath = app.getAppPath();
    const projectPython = path.join(appPath, '..', 'venv', 'Scripts', 'python.exe');
    if (fs.existsSync(projectPython)) return projectPython;

  }

  return process.platform === 'win32' ? 'python' : 'python3';
}

function isServerRunning() {
  return new Promise((resolve) => {
    const http = require('http');
    const req = http.get(`${SERVER_URL}/health`, (res) => {
      resolve(res.statusCode === 200);
    });
    req.on('error', () => resolve(false));
    req.setTimeout(2000, () => {
      req.destroy();
      resolve(false);
    });
  });
}

function startServer() {
  return new Promise((resolve, reject) => {
    const serverScript = findServerScript();
    if (!serverScript) {
      reject(new Error('Server script not found. Start the server first: xcopilot desktop start --server'));
      return;
    }

    const pythonPath = findPython();
    const appPath = app.getAppPath();
    const projectRoot = path.join(appPath, '..');

    serverProcess = spawn(pythonPath, [serverScript, 'serve'], {
      cwd: projectRoot,
      detached: false,
      stdio: ['ignore', 'pipe', 'pipe'],
      env: {
        ...process.env,
        PYTHONPATH: [
          path.join(projectRoot, 'src'),
          projectRoot,
        ].join(path.delimiter),
      },
    });

    serverProcess.stdout.on('data', (data) => {
      console.log(`[server] ${data}`);
    });

    serverProcess.stderr.on('data', (data) => {
      console.error(`[server-stderr] ${data}`);
    });

    serverProcess.on('error', (err) => {
      console.error('[server] Failed to start:', err.message);
      reject(err);
    });

    serverProcess.on('close', (code) => {
      console.log(`[server] Process exited with code ${code}`);
    });

    waitForServer(resolve, reject);
  });
}

function waitForServer(resolve, reject, retries = 30) {
  if (retries <= 0) {
    reject(new Error('Server failed to start in time'));
    return;
  }

  const http = require('http');
  const req = http.get(`${SERVER_URL}/health`, (res) => {
    if (res.statusCode === 200) {
      console.log('[server] Ready');
      resolve();
    } else {
      setTimeout(() => waitForServer(resolve, reject, retries - 1), 1000);
    }
  });

  req.on('error', () => {
    setTimeout(() => waitForServer(resolve, reject, retries - 1), 1000);
  });

  req.setTimeout(5000, () => {
    req.destroy();
    setTimeout(() => waitForServer(resolve, reject, retries - 1), 1000);
  });
}

function stopServer() {
  return new Promise((resolve) => {
    if (serverProcess) {
      serverProcess.kill('SIGTERM');
      serverProcess = null;
    }
    setTimeout(resolve, 1000);
  });
}

// ── Window management ───────────────────────────────────

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 800,
    minHeight: 600,
    title: 'X-Copilot',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
    icon: path.join(__dirname, 'assets', 'icon.png'),
    show: false,
  });

  mainWindow.loadFile(path.join(__dirname, 'renderer', 'index.html'));

  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
    if (process.argv.includes('--dev')) {
      mainWindow.webContents.openDevTools();
    }
  });

  mainWindow.on('close', (event) => {
    if (!app.isQuitting) {
      event.preventDefault();
      mainWindow.hide();
    }
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

// ── Tray ────────────────────────────────────────────────

function createTray() {
  const iconPath = path.join(__dirname, 'assets', 'icon.png');
  tray = new Tray(fs.existsSync(iconPath) ? iconPath : undefined);

  const contextMenu = Menu.buildFromTemplate([
    { label: 'Show X-Copilot', click: () => mainWindow?.show() },
    { type: 'separator' },
    {
      label: 'Restart Server',
      click: async () => {
        await stopServer();
        try {
          await startServer();
          mainWindow?.webContents.send('server-status', { status: 'restarted' });
        } catch (err) {
          mainWindow?.webContents.send('server-status', { status: 'error', error: err.message });
        }
      },
    },
    { type: 'separator' },
    { label: 'Quit', click: () => quitApp() },
  ]);

  tray.setToolTip('X-Copilot');
  tray.setContextMenu(contextMenu);

  tray.on('double-click', () => {
    if (mainWindow) {
      mainWindow.isVisible() ? mainWindow.hide() : mainWindow.show();
    }
  });
}

// ── IPC handlers ────────────────────────────────────────

async function setupIpc() {
  ipcMain.handle('server:status', async () => {
    const running = await isServerRunning();
    return { status: running ? 'running' : 'stopped' };
  });

  ipcMain.handle('server:start', async () => {
    try {
      await startServer();
      return { status: 'started' };
    } catch (err) {
      return { status: 'error', error: err.message };
    }
  });

  ipcMain.handle('server:stop', async () => {
    await stopServer();
    return { status: 'stopped' };
  });

  ipcMain.handle('app:version', () => ({
    version: app.getVersion(),
    platform: process.platform,
    arch: process.arch,
  }));

  ipcMain.handle('dialog:open', async (event, options) => {
    const result = await dialog.showOpenDialog(mainWindow || BrowserWindow.getFocusedWindow(), options);
    return result;
  });

  ipcMain.handle('dialog:save', async (event, options) => {
    const result = await dialog.showSaveDialog(mainWindow || BrowserWindow.getFocusedWindow(), options);
    return result;
  });
}

// ── App lifecycle ───────────────────────────────────────

async function quitApp() {
  app.isQuitting = true;
  await stopServer();
  app.quit();
}

async function init() {
  app.isQuitting = false;

  await setupIpc();
  createTray();
  createWindow();

  // Try to start server only in dev mode
  const isDev = process.argv.includes('--dev') || !app.isPackaged;
  if (isDev) {
    try {
      await startServer();
      mainWindow?.webContents.send('server-status', { status: 'started' });
    } catch (err) {
      console.error('[app] Server start failed:', err.message);
      mainWindow?.webContents.send('server-status', { status: 'error', error: err.message });
    }
  } else {
    // Installed mode: just check if server is running
    const running = await isServerRunning();
    mainWindow?.webContents.send('server-status', { status: running ? 'started' : 'stopped' });
  }

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
}

app.whenReady().then(init);

app.on('before-quit', async () => {
  app.isQuitting = true;
  await stopServer();
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    if (mainWindow) mainWindow.hide();
  }
});

app.on('will-quit', async () => {
  await stopServer();
});