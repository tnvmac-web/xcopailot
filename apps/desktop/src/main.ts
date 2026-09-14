/**
 * X-Copilot Desktop App — Main Process
 *
 * Spawns headless X-Copilot server as backend.
 * Own composer/transcript — not embedding web dashboard.
 * Communicates via JSON-RPC.
 */

import { app, BrowserWindow, Tray, Menu, ipcMain } from "electron";
import { spawn } from "child_process";
import path from "path";
import fs from "fs";

let mainWindow: BrowserWindow | null = null;
let serverProcess: ReturnType<typeof spawn> | null = null;
let tray: Tray | null = null;

const SERVER_HOST = "127.0.0.1";
const SERVER_PORT = 8001;
const SERVER_URL = `http://${SERVER_HOST}:${SERVER_PORT}`;

function findPython(): string {
  const hermesVenv = path.join(
    process.env.LOCALAPPDATA || "",
    "hermes",
    "hermes-agent",
    "venv",
    "Scripts",
    "python.exe"
  );
  if (fs.existsSync(hermesVenv)) return hermesVenv;

  const projectPython = path.join(
    __dirname, "..", "..", "venv", "Scripts", "python.exe"
  );
  if (fs.existsSync(projectPython)) return projectPython;

  return "python";
}

function findServerScript(): string | null {
  const candidates = [
    path.join(__dirname, "..", "..", "server", "main.py"),
    path.join(app.getAppPath(), "..", "server", "main.py"),
  ];
  for (const p of candidates) {
    if (fs.existsSync(p)) return p;
  }
  return null;
}

function isServerRunning(): Promise<boolean> {
  return new Promise((resolve) => {
    const http = require("http");
    const req = http.get(`${SERVER_URL}/health`, (res: any) => {
      resolve(res.statusCode === 200);
    });
    req.on("error", () => resolve(false));
    req.setTimeout(2000, () => {
      req.destroy();
      resolve(false);
    });
  });
}

function startServer(): Promise<void> {
  return new Promise((resolve, reject) => {
    const serverScript = findServerScript();
    if (!serverScript) {
      reject(new Error("Server script not found"));
      return;
    }

    const pythonPath = findPython();
    const projectRoot = path.join(__dirname, "..", "..");

    serverProcess = spawn(pythonPath, [serverScript, "serve"], {
      cwd: projectRoot,
      detached: false,
      stdio: ["ignore", "pipe", "pipe"],
      env: {
        ...process.env,
        PYTHONPATH: [path.join(projectRoot, "src"), projectRoot].join(path.delimiter),
      },
    });

    serverProcess.stdout?.on("data", (data: Buffer) => {
      console.log(`[server] ${data}`);
    });

    serverProcess.stderr?.on("data", (data: Buffer) => {
      console.error(`[server-stderr] ${data}`);
    });

    serverProcess.on("error", (err: Error) => {
      console.error("[server] Failed:", err.message);
      reject(err);
    });

    // Wait for server to be ready
    let retries = 30;
    const check = () => {
      if (retries <= 0) {
        reject(new Error("Server failed to start in time"));
        return;
      }
      const http = require("http");
      const req = http.get(`${SERVER_URL}/health`, (res: any) => {
        if (res.statusCode === 200) {
          console.log("[server] Ready");
          resolve();
        } else {
          retries--;
          setTimeout(check, 1000);
        }
      });
      req.on("error", () => {
        retries--;
        setTimeout(check, 1000);
      });
      req.setTimeout(5000, () => {
        req.destroy();
        retries--;
        setTimeout(check, 1000);
      });
    };
    check();
  });
}

function stopServer(): Promise<void> {
  return new Promise((resolve) => {
    if (serverProcess) {
      serverProcess.kill("SIGTERM");
      serverProcess = null;
    }
    setTimeout(resolve, 1000);
  });
}

function createWindow(): void {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 800,
    minHeight: 600,
    title: "X-Copilot",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
    icon: path.join(__dirname, "assets", "icon.png"),
    show: false,
  });

  // Load renderer
  const devServer = process.env.XCOPILOT_DESKTOP_DEV_SERVER;
  if (devServer) {
    mainWindow.loadURL(devServer);
  } else {
    mainWindow.loadFile(path.join(__dirname, "renderer", "index.html"));
  }

  mainWindow.once("ready-to-show", () => {
    mainWindow?.show();
  });

  mainWindow.on("close", (event) => {
    if (!app.isQuitting) {
      event.preventDefault();
      mainWindow?.hide();
    }
  });
}

function createTray(): void {
  const iconPath = path.join(__dirname, "assets", "icon.png");
  const icon = fs.existsSync(iconPath) ? iconPath : undefined;
  tray = new Tray(icon);

  const contextMenu = Menu.buildFromTemplate([
    { label: "Show X-Copilot", click: () => mainWindow?.show() },
    { type: "separator" },
    {
      label: "Restart Server",
      click: async () => {
        await stopServer();
        try {
          await startServer();
          mainWindow?.webContents.send("server-status", { status: "restarted" });
        } catch (err: any) {
          mainWindow?.webContents.send("server-status", { status: "error", error: err.message });
        }
      },
    },
    { type: "separator" },
    { label: "Quit", click: () => quitApp() },
  ]);

  tray.setToolTip("X-Copilot");
  tray.setContextMenu(contextMenu);

  tray.on("double-click", () => {
    if (mainWindow) {
      mainWindow.isVisible() ? mainWindow.hide() : mainWindow.show();
    }
  });
}

async function quitApp() {
  app.isQuitting = true;
  await stopServer();
  app.quit();
}

// ── App lifecycle ──────────────────────────────────

app.whenReady().then(async () => {
  app.isQuitting = false;

  createTray();
  createWindow();

  // Start server in background
  try {
    await startServer();
    mainWindow?.webContents.send("server-status", { status: "started" });
  } catch (err: any) {
    console.error("[app] Server start failed:", err.message);
    mainWindow?.webContents.send("server-status", { status: "error", error: err.message });
  }

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("before-quit", async () => {
  app.isQuitting = true;
  await stopServer();
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    if (mainWindow) mainWindow.hide();
  }
});

app.on("will-quit", async () => {
  await stopServer();
});