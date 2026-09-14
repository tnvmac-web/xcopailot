# X-Copilot

Self-growing AI agent for Windows — standalone desktop app with web dashboard.

## Architecture

```
xcopilot/
├── src/xcopilot/          # Main CLI package
│   ├── cli/               # Click CLI commands
│   ├── core/              # Core engine (delegation, conversation loop)
│   ├── tools/             # Tool registry + 5 built-in tools
│   ├── memory/            # 5-layer memory engine
│   ├── permission/        # 5-tier permission pipeline
│   ├── config.py          # Profile-aware YAML+env config
│   ├── state/             # SQLite+FTS5 session persistence
│   ├── plugins/           # Plugin system
│   ├── cron/              # JSON-backed job scheduler
│   └── gateway/           # Multi-platform gateway runner
├── server/                # FastAPI server (port 8001)
│   ├── main.py            # Server entry point
│   ├── auth.py            # Shared auth module
│   └── web_routers.py     # 7 API routers
├── desktop/               # Electron desktop app
│   ├── main.js            # Main process (server lifecycle + window)
│   ├── preload.js         # IPC bridge
│   ├── renderer/          # Chat UI
│   └── package.json       # Electron + electron-builder
├── webapp/                # Web dashboard SPA
│   ├── index.html
│   ├── css/styles.css
│   └── js/                # API client + app logic
├── tests/                 # 31 tests
└── pyproject.toml         # Project config
```

## Quick Start

```bash
# Install
pip install -e ".[dev,cli]"

# CLI REPL
xcopilot start

# Start server (webapp + API)
xcopilot desktop start --server

# Desktop app (Electron)
xcopilot desktop start

# Web dashboard
xcopilot webapp
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `xcopilot start` | CLI REPL |
| `xcopilot delegate run "task"` | Delegate a task |
| `xcopilot delegate batch "task1" "task2"` | Batch delegation |
| `xcopilot delegate list` | List tasks |
| `xcopilot delegate status <id>` | Task status |
| `xcopilot delegate cancel <id>` | Cancel task |
| `xcopilot delegate summary` | Task summary |
| `xcopilot desktop start` | Launch Electron app |
| `xcopilot desktop status` | Check server + app status |
| `xcopilot webapp` | Start web dashboard |
| `xcopilot config get/set` | Configuration |
| `xcopilot doctor` | Diagnose installation |

## API Endpoints

All endpoints on `http://127.0.0.1:8001/api/`:

- `GET /health` — Health check
- `GET /api/status` — Server status
- `POST /api/chat` — Chat message
- `POST /api/chat/stream` — Streaming chat
- `GET /api/sessions` — List sessions
- `POST /api/sessions` — Create session
- `GET /api/sessions/{id}` — Get session
- `GET /api/sessions/{id}/messages` — Session messages
- `GET /api/settings` — Get settings
- `PUT /api/settings` — Update settings
- `GET /api/cron/` — List cron jobs
- `POST /api/cron/` — Create cron job
- `GET /api/gateway/status` — Gateway status
- `GET /api/delegation/tasks` — List delegation tasks
- `POST /api/delegation/delegate` — Delegate task
- `GET /api/tools/` — List tools

## Web Dashboard

http://127.0.0.1:8001/

Features:
- Chat view with streaming responses
- Session sidebar with click-to-load
- Delegation tasks panel
- Settings panel (model, permission mode, provider)
- Terminal view (shell commands)
- Memory viewer (session/episodic/semantic/procedural stats)
- Real-time server status indicator
- Responsive design (desktop + mobile)

## Desktop App

Electron 33+ app with:
- Server lifecycle management (auto-start on launch)
- System tray icon (double-click to restore)
- Session sidebar with click-to-load
- Chat with streaming response display
- Delegation task panel
- Settings modal (model, permission mode, provider)
- NSIS Windows installer

Build:
```bash
cd desktop
npm install
npm run build
# Output: desktop/dist/X-Copilot Setup 0.1.1.exe
```

## Delegation

Task delegation system with 5-tier permission pipeline:
- **leaf** + STANDARD → auto-approved
- **orchestrator** + STANDARD → ask user
- **PLAN** mode → denied
- **BYPASS** mode → auto-approved
- **DONT_ASK** → auto-approved (non-destructive only)
- **AUTO_ASK** → always ask

## Memory Engine

5-layer memory:
1. **Session** — current conversation context
2. **Episodic** — past events and observations
3. **Semantic** — knowledge graph
4. **Procedural** — learned skills and patterns
5. **Project** — project-specific context

## Configuration

Profile-aware YAML + environment variables:
```bash
xcopilot config set model gpt-4o-mini
xcopilot config set permission_mode standard
xcopilot config set provider openai
```

## Testing

```bash
python -m pytest tests/ -v
```

31 tests: core (11), cli (6), server (6), tools (8)

## Version

0.1.1

## License

MIT