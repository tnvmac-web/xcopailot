# X-Copilot Architecture — Project File

## What is X-Copilot

Self-growing AI agent for Windows. Uses Hermes Agent as the backend subagent
orchestration engine. X-Copilot adds a 5-layer memory system, permission pipeline,
skills marketplace, and task delegation on top of Hermes.

## Hermes Backend (the engine)

Hermes provides the core agent loop, tool system, memory, and delegation primitives.
X-Copilot wraps Hermes via `hermes_tools` Python module (auto-imported by Hermes).

### Hermes Entry Points
- CLI: `hermes_cli/main.py` — interactive REPL with slash commands
- Gateway: `gateway/run.py` — messaging platforms (Telegram, Discord, Slack, etc.)
- ACP: `acp_adapter/` — IDE integration (VS Code, Zed, JetBrains)
- Batch Runner: `batch_runner.py` — trajectory generation
- API Server: fastapi-based server

### Hermes Agent Loop
User input → HermesCLI.process_input() → AIAgent.run_conversation()
→ prompt_builder.build_system_prompt() → runtime_provider.resolve_runtime_provider()
→ API call (chat_completions / codex_responses / anthropic_messages)
→ tool_calls? → model_tools.handle_function_call() → loop
→ final response → display → save to SessionDB

### Hermes Major Subsystems
| Subsystem | Path | Role |
|-----------|------|------|
| Agent Loop | `run_agent.py` + `agent/conversation_loop.py` | Orchestration engine |
| Prompt System | `agent/prompt_builder.py` + `system_prompt.py` | System prompt assembly |
| Provider Resolution | `hermes_cli/runtime_provider.py` | Provider → api_mode + credentials |
| Tool System | `tools/registry.py` | 70+ tools, 28 toolsets |
| Session Storage | `hermes_state.py` | SQLite + FTS5 |
| Gateway | `gateway/run.py` | 25+ platform adapters |
| Plugin System | `plugins/` | Memory providers, context engines |
| Cron | `cron/` | Agent tasks (not shell tasks) |
| Delegation | `tools/delegate_tool.py` + `tools/async_delegation.py` | Subagent delegation |

### Hermes Design Principles
- Prompt stability: system prompt doesn't change mid-conversation
- Observable execution: every tool call visible via callbacks
- Interruptible: API calls and tool execution cancellable mid-flight
- Platform-agnostic core: one AIAgent class serves all entry points
- Loose coupling: optional subsystems use registry patterns
- Profile isolation: each profile gets own HERMES_HOME, config, memory, sessions

## X-Copilot Architecture

### Components
```
┌─────────────────────────────────────────────────────────┐
│                    X-Copilot CLI                          │
│  (Click CLI + Rich console + prompt_toolkit REPL)        │
│  Commands: start, delegate, memory, skills, model, ...   │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│                 Core Engine                              │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────┐ │
│  │ Conversation │ │ Permission   │ │ TaskDelegator    │ │
│  │ Loop         │ │ Pipeline     │ │ (Hermes wrapper) │ │
│  │              │ │ 5-tier:      │ │                  │ │
│  │ model→tools  │ │ BYPASS/PLAN/ │ │ delegate_task    │ │
│  │ →response    │ │ STANDARD/    │ │ → Hermes subagent│ │
│  │              │ │ DONT_ASK/    │ │ async + batch    │ │
│  │              │ │ AUTO_ASK     │ │ durable ledger   │ │
│  └──────────────┘ └──────────────┘ └──────────────────┘ │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│                   Memory (5 layers)                       │
│  Session → Episodic → Semantic → Procedural → Project   │
│  (SQLite + JSONL + Chroma + AGENTS.md + agentmemory)     │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│                  Tool System                             │
│  ShellTool + FileTool + SearchTool + WebTool             │
│  + DelegationTool (permission-aware)                     │
│  + MCP tools (dynamic discovery)                         │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│              Model Providers                             │
│  OpenAI / Anthropic / Ollama / LM Studio /              │
│  OpenRouter / NVIDIA / Google AI                         │
└─────────────────────────────────────────────────────────┘
```

### Memory Layers
1. **Session** — in-memory conversation history (dict)
2. **Episodic** — SQLite + JSONL event store with FTS5 search
3. **Semantic** — Chroma vector DB for similarity search
4. **Procedural** — YAML-based skill definitions
5. **Project** — AGENTS.md + project-specific context

### Permission Pipeline (5 tiers)
| Mode | Reads | Writes | Shell | Delegation |
|------|-------|--------|-------|------------|
| BYPASS | Allow | Allow | Allow | Allow |
| PLAN | Allow | Deny | Deny | Deny |
| STANDARD | Allow | Ask | Ask | Leaf=allow, Orchestrator=ask |
| DONT_ASK | Allow | Allow | Allow | Allow non-destructive |
| AUTO_ASK | Allow | Ask | Ask | Always ask |

### Delegation Architecture
X-Copilot delegates tasks to Hermes subagents using Hermes'
`delegate_task` tool. The `TaskDelegator` class wraps this with:

- **Immutable tasks** — DelegationTask is frozen (dataclass(frozen=True))
- **Durable ledger** — SQLite-backed task persistence
- **Episodic recording** — Every delegation event stored in MemoryEngine
- **Permission-aware** — DelegationTool checks PermissionPipeline before dispatch
- **Batch execution** — `delegate batch` runs multiple goals in parallel
- **Background mode** — `-b` flag for async non-blocking delegation

### CLI Commands
```
xcopilot start              — REPL with agent loop
xcopilot delegate run       — Delegate single task
xcopilot delegate batch     — Delegate multiple tasks in parallel
xcopilot delegate status    — Check task status
xcopilot delegate list      — List all tasks
xcopilot delegate cancel    — Cancel a task
xcopilot delegate summary   — Aggregated stats
xcopilot memory             — Memory management
xcopilot skills             — Skills marketplace
xcopilot model              — Model provider management
xcopilot serve              — Start API server
```

### Server API
FastAPI server on port 8000 with WebSocket support:
- REST: `/api/delegation/*` (delegate, batch, status, tasks, summary, history)
- WebSocket: `/api/delegation/events` (real-time status updates)
- Auth: Bearer token via `/api/auth/login`

### File Dependency Chain
```
tools/registry.py  (no deps — imported by all tool files)
       ↑
tools/*.py  (each calls registry.register() at import time)
       ↑
model_tools.py  (imports tools/registry + triggers tool discovery)
       ↑
run_agent.py, cli.py, batch_runner.py, environments/
```

Tool registration happens at import time — any `tools/*.py` with a
top-level `registry.register()` call is auto-discovered.

## Key Files

| File | Role |
|------|------|
| `src/xcopilot/cli/main.py` | CLI entry point — Click groups, REPL |
| `src/xcopilot/core/conversation_loop.py` | Agent loop — model → tools → response |
| `src/xcopilot/core/delegation.py` | TaskDelegator — Hermes delegation wrapper |
| `src/xcopilot/core/models.py` | ChatMessage, ChatResponse, ModelProvider, registry |
| `src/xcopilot/permission/pipeline.py` | 5-tier permission engine |
| `src/xcopilot/memory/__init__.py` | MemoryEngine — 5-layer memory orchestration |
| `src/xcopilot/memory/episodic.py` | EpisodicMemory — SQLite + JSONL |
| `src/xcopilot/memory/semantic.py` | SemanticMemory — Chroma vector DB |
| `src/xcopilot/memory/procedural.py` | ProceduralMemory — skill definitions |
| `src/xcopilot/memory/project.py` | ProjectMemory — AGENTS.md |
| `src/xcopilot/tools/delegation.py` | DelegationTool — permission-aware tool |
| `src/xcopilot/tools/shell.py` | ShellTool — terminal execution |
| `src/xcopilot/tools/file.py` | FileTool — read/write/patch/search |
| `src/xcopilot/tools/search.py` | SearchTool — grep + web search |
| `src/xcopilot/tools/web.py` | WebTool — web extraction |
| `src/xcopilot/skills/marketplace.py` | Skills marketplace |
| `src/xcopilot/core/graph.py` | KnowledgeGraph — dependency graph |
| `src/xcopilot/core/checkpoint.py` | CheckpointManager — rollback points |
| `src/xcopilot/core/learner.py` | LearnerEngine — self-improvement |
| `src/xcopilot/core/planner.py` | PlannerEngine — task planning |
| `src/xcopilot/core/evaluator.py` | Evaluator — quality assessment |
| `server/main.py` | FastAPI server — REST + WebSocket API |
| `pyproject.toml` | Project config — deps, scripts, build |

## Integration Points

### X-Copilot → Hermes
- `hermes_tools.delegate_task()` — spawn Hermes subagent
- `hermes_tools.memory_recall()` — recall past observations
- `hermes_tools.memory_save()` — save insights to memory
- `hermes_tools.web_search()` — web search via Hermes
- `hermes_tools.terminal()` — shell execution via Hermes

### X-Copilot → Memory
- MemoryEngine records delegation results as EpisodicEvents
- Delegation history queryable via `memory.query_delegation_history()`
- Session memory auto-saved at conversation end

### X-Copilot → Permission Pipeline
- Every tool call checked against PermissionMode
- DelegationTool pre-checks: leaf→allow, orchestrator→ask, PLAN→deny
- ConversationLoop checks DELEGATE action before tool dispatch

## Build & Run

```bash
# Install
pip install -e ".[dev,cli]"

# CLI REPL
xcopilot start

# Desktop app
xcopilot desktop start

# Server only
xcopilot desktop start --server

# Development mode (with DevTools)
xcopilot desktop start --dev

# Check status
xcopilot desktop status

# Delegate a task
xcopilot delegate run "analyze this codebase"

# Start server
xcopilot serve

# Run tests
python -m pytest tests/ -v
```

## Webapp (Dashboard SPA)

```
webapp/
├── index.html           — Main dashboard HTML
├── css/
│   └── styles.css       — Dark theme, responsive styles
└── js/
    ├── app.js           — Main app logic (views, routing)
    └── api.js           — API client (chat, sessions, tasks, settings, cron)
```

### Webapp Features
- Chat view with streaming responses
- Session sidebar with click-to-load
- Delegation tasks panel
- Settings panel (model, permission mode, provider)
- Terminal view (shell commands)
- Memory viewer (session/episodic/semantic/procedural stats)
- Real-time server status indicator
- Responsive design (desktop + mobile)

```
desktop/
├── main.js              — Electron main process (server lifecycle + window)
├── preload.js           — Safe IPC bridge (contextBridge)
├── package.json         — Electron + electron-builder config
├── generate_icons.py    — Icon generator (SVG/PNG/ICO)
├── assets/
│   ├── icon.svg         — Vector icon
│   ├── icon.png         — PNG icon (256x256)
│   └── icon.ico         — Windows ICO icon
└── renderer/
    └── index.html       — Chat UI (sidebar + messages + input + delegation panel)
```

### Desktop Features
- **Server lifecycle** — starts/stops X-Copilot FastAPI server automatically
- **System tray** — minimize to tray, double-click to restore
- **Chat UI** — sidebar with sessions, message bubbles, streaming cursor
- **Delegation panel** — view/manage delegated tasks from desktop
- **Settings modal** — model, permission mode, provider config
- **Server status** — real-time dot indicator (green=running, red=stopped, yellow=error)
- **DevTools** — `--dev` flag for debugging
- **NSIS installer** — `npm run build` creates Windows installer

## Testing

31 tests across 4 suites:
- `tests/core/test_delegation.py` — 11 tests (TaskDelegator lifecycle)
- `tests/cli/test_delegate_command.py` — 6 tests (CLI commands)
- `tests/server/test_delegation_api.py` — 6 tests (REST API endpoints)
- `tests/tools/test_delegation_tool.py` — 8 tests (permission checks)