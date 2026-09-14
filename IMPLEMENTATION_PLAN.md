# X-Copilot — Full Architecture Implementation Plan

## Phase 1: Directory Reorganization
Reorganize src/xcopilot/ to match X-Copilot facade+siblings pattern:
- Move CLI subcommands to xcopilot/cli/commands/ (one file per command)
- Split tools/ into registry-based auto-discovery
- Create xcopilot/plugins/ for plugin system
- Create xcopilot/cron/ for scheduled jobs
- Create xcopilot/state/ for session persistence

## Phase 2: Core Infrastructure
- Tool registry with auto-discovery (tools/registry.py)
- Toolsets grouping (28 toolsets like X-Copilot)
- Config system (config.yaml, profile-aware paths)
- State layer (SQLite + FTS5 session storage)

## Phase 3: Agent Loop Refactor
- Proper turn loop phases: input → prompt builder → provider → tool dispatch → response
- Prompt builder with system prompt tiers (stable → context → volatile)
- Provider resolution (OpenAI, Anthropic, Ollama, LM Studio, OpenRouter, NVIDIA)
- Compression & context management

## Phase 4: Gateway & Surfaces
- Gateway facade (gateway/run.py pattern)
- TUI gateway (JSON-RPC backend)
- Desktop app backend (Tauri + Rust)
- Web dashboard (FastAPI routers)
- ACP adapter (IDE integration)

## Phase 5: Plugins & Extension Points
- Plugin system (memory, context_engine, model_provider, kanban, image_gen)
- Skills marketplace integration
- MCP server support
- Cron jobs system
- Desktop plugins
- TUI widgets

## Phase 6: Testing Infrastructure
- Test placement mirroring source tree
- Proper test fixtures
- Integration tests

## Phase 7: Dependency & Config
- Dependency pinning
- uv.lock
- Config & state management