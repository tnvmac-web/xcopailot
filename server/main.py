from __future__ import annotations

import hashlib
import json
import os
import secrets
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from re import fullmatch
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect, status as http_status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from xcopilot.core.conversation_loop import ConversationLoop
from xcopilot.core.delegation import TaskDelegator, TaskStatus
from xcopilot.core.model_providers import register_all_providers
from xcopilot.core.models import ChatMessage, ModelCapability, ModelProvider, registry
from xcopilot.memory import MemoryEngine
from xcopilot.permission.pipeline import PermissionMode
from xcopilot.skills import marketplace
from xcopilot.core.graph import KnowledgeGraph
from server.web_routers import (
    chat_router,
    sessions_router,
    settings_router,
    cron_router,
    gateway_router,
    delegation_router,
    tools_router,
)
from server.auth import require_auth, _issue_token, ACTIVE_TOKENS

AUTH_SECRET = os.environ.get("XCOPILOT_AUTH_SECRET", "xcopilot-local-dev-secret")
DEFAULT_USERNAME = os.environ.get("XCOPILOT_ADMIN_USERNAME", "admin")
DEFAULT_PASSWORD = os.environ.get("XCOPILOT_ADMIN_PASSWORD", "admin")
DEFAULT_MODEL = os.environ.get("XCOPILOT_DEFAULT_MODEL", "gpt-4o-mini")


def _read_project_model_config() -> dict[str, dict[str, str]]:
    """Read provider configuration from the project file with env interpolation."""
    config_path = Path(__file__).resolve().parents[1] / ".xcopilot" / "config.json"
    try:
        raw_config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    model_config = raw_config.get("models", {})
    resolved: dict[str, dict[str, str]] = {}
    for provider, values in model_config.items():
        if not isinstance(values, dict):
            continue
        resolved[provider] = {}
        for key, value in values.items():
            if not isinstance(value, str):
                continue
            match = fullmatch(r"\$\{([A-Z0-9_]+)\}", value)
            resolved[provider][key] = os.environ.get(match.group(1), "") if match else value
    return resolved


def _provider_config() -> dict[str, dict[str, str]]:
    """Build provider configuration from project settings and environment overrides."""
    project_config = _read_project_model_config()

    def value(provider: str, key: str, env_name: str, default: str = "") -> str:
        return os.environ.get(env_name) or project_config.get(provider, {}).get(key, default)

    config: dict[str, dict[str, str]] = {}
    if value("openai", "api_key", "OPENAI_API_KEY"):
        config["openai"] = {
            "api_key": value("openai", "api_key", "OPENAI_API_KEY"),
            "base_url": value("openai", "base_url", "OPENAI_BASE_URL", "https://api.openai.com/v1"),
        }
    if value("anthropic", "api_key", "ANTHROPIC_API_KEY"):
        config["anthropic"] = {
            "api_key": value("anthropic", "api_key", "ANTHROPIC_API_KEY"),
            "base_url": value("anthropic", "base_url", "ANTHROPIC_BASE_URL", "https://api.anthropic.com"),
        }
    if value("ollama", "base_url", "OLLAMA_BASE_URL"):
        config["ollama"] = {"base_url": value("ollama", "base_url", "OLLAMA_BASE_URL")}
    if value("lmstudio", "base_url", "LMSTUDIO_BASE_URL"):
        config["lmstudio"] = {"base_url": value("lmstudio", "base_url", "LMSTUDIO_BASE_URL")}
    if value("openrouter", "api_key", "OPENROUTER_API_KEY"):
        config["openrouter"] = {"api_key": value("openrouter", "api_key", "OPENROUTER_API_KEY")}
    if value("nvidia", "api_key", "NVIDIA_API_KEY"):
        config["nvidia"] = {
            "api_key": value("nvidia", "api_key", "NVIDIA_API_KEY"),
            "base_url": value("nvidia", "base_url", "NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"),
        }
    return config


@dataclass
class SessionRecord:
    """Persistent in-memory session state for authenticated clients."""

    id: str
    user_id: str
    title: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    messages: list[dict[str, Any]] = field(default_factory=list)


ACTIVE_TOKENS = {}  # imported from server.auth
SESSIONS: dict[str, SessionRecord] = {}
USER_SETTINGS: dict[str, dict[str, Any]] = {}
conversation_loop = ConversationLoop()
register_all_providers(_provider_config())
if registry.get(ModelProvider.OPENAI):
    registry.set_default(ModelProvider.OPENAI)
elif registry.get(ModelProvider.ANTHROPIC):
    registry.set_default(ModelProvider.ANTHROPIC)


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield


app = FastAPI(title="X-Copilot API", version="0.1.1", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register web routers
app.include_router(chat_router)
app.include_router(sessions_router)
app.include_router(settings_router)
app.include_router(cron_router)
app.include_router(gateway_router)
app.include_router(delegation_router)
app.include_router(tools_router)

# ── Webapp static files ───────────────────────────
webapp_dir = Path(__file__).resolve().parent.parent / "webapp"
if webapp_dir.exists():
    app.mount("/css", StaticFiles(directory=str(webapp_dir / "css")), name="webapp-css")
    app.mount("/js", StaticFiles(directory=str(webapp_dir / "js")), name="webapp-js")

    @app.get("/", response_class=HTMLResponse)
    async def webapp_root():
        index_file = webapp_dir / "index.html"
        if index_file.exists():
            return HTMLResponse(content=index_file.read_text(encoding="utf-8"))
        return HTMLResponse(content="<h1>X-Copilot Web Dashboard</h1><p>Webapp not found.</p>")


def _get_or_create_session(session_id: str | None, user_id: str, title: str | None = None) -> SessionRecord:
    if session_id and session_id in SESSIONS:
        return SESSIONS[session_id]
    session_key = session_id or secrets.token_urlsafe(12)
    session = SessionRecord(
        id=session_key,
        user_id=user_id,
        title=title or f"Session {len(SESSIONS) + 1}",
    )
    SESSIONS[session_key] = session
    return session


def _settings_for(user_id: str) -> dict[str, Any]:
    return USER_SETTINGS.setdefault(
        user_id,
        {
            "default_model": DEFAULT_MODEL,
            "temperature": 0.7,
            "max_tokens": 4096,
            "context_mode": "auto",
            "theme": "system",
            "auto_save": True,
        },
    )


def _configured_provider_names() -> list[str]:
    return sorted(provider.value for provider in ModelProvider if provider != ModelProvider.CUSTOM and registry.get(provider))


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "service": "xcopilot", "timestamp": datetime.now(UTC).isoformat()}


@app.get("/ready")
async def ready() -> dict[str, Any]:
    model_runtime = bool(registry._providers)
    return {"status": "ready" if model_runtime else "degraded", "checks": {"auth": True, "sessions": True, "model_runtime": model_runtime}}


@app.get("/api/status")
async def status() -> dict[str, Any]:
    return {"status": "ready", "version": "0.1.1", "service": "xcopilot", "timestamp": datetime.now(UTC).isoformat()}


@app.get("/api/config")
async def config() -> dict[str, Any]:
    return {
        "server": {"host": "0.0.0.0", "port": 8001, "base_url": "http://127.0.0.1:8001"},
        "default_model": DEFAULT_MODEL,
        "features": ["chat", "memory", "skills", "checkpoints", "auth", "websocket", "real_models"],
    }


@app.get("/api/models")
async def models() -> list[dict[str, Any]]:
    available = await registry.list_all_models()
    return [
        {"id": model.id, "name": model.name, "provider": provider.value}
        for provider, provider_models in available.items()
        for model in provider_models
        if ModelCapability.CHAT in model.capabilities
    ]


@app.get("/api/providers")
async def providers() -> dict[str, str]:
    result: dict[str, str] = {}
    for provider in ModelProvider:
        if provider == ModelProvider.CUSTOM:
            continue
        registered = registry.get(provider)
        result[provider.value] = "registered" if registered else "not_configured"
    return result


@app.get("/api/settings")
async def get_settings(user_id: str = Depends(require_auth)) -> dict[str, Any]:
    settings = _settings_for(user_id).copy()
    settings["configured_providers"] = _configured_provider_names()
    # Add model/provider/api_key from config.yaml
    from xcopilot.config import load_config
    config = load_config()
    settings["model"] = config.get("model", "gpt-4o-mini")
    settings["provider"] = config.get("provider", "openai")
    # Read API key from .env
    from xcopilot.config import get_secrets_path
    secrets_path = get_secrets_path()
    api_key = ""
    if secrets_path.exists():
        import re
        content = secrets_path.read_text(encoding="utf-8")
        match = re.search(r"^OPENAI_API_KEY=(.+)$", content, re.MULTILINE)
        if match:
            api_key = match.group(1)
    settings["api_key"] = api_key
    return settings


@app.put("/api/settings")
async def update_settings(payload: dict[str, Any], user_id: str = Depends(require_auth)) -> dict[str, Any]:
    settings = _settings_for(user_id)
    # Handle model/provider/api_key updates
    from xcopilot.config import load_config, save_config, get_secrets_path
    config = load_config()
    if "model" in payload:
        config["model"] = str(payload["model"])
    if "provider" in payload:
        config["provider"] = str(payload["provider"])
    if "api_key" in payload:
        api_key = str(payload["api_key"])
        secrets_path = get_secrets_path()
        secrets_path.parent.mkdir(parents=True, exist_ok=True)
        existing = ""
        if secrets_path.exists():
            existing = secrets_path.read_text(encoding="utf-8")
        lines = existing.splitlines()
        lines = [l for l in lines if not l.startswith("OPENAI_API_KEY=")]
        if api_key:
            lines.append(f"OPENAI_API_KEY={api_key}")
        secrets_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    save_config(config)
    api_keys = payload.get("provider_api_keys")
    if isinstance(api_keys, dict):
        provider_configs: dict[str, dict[str, str]] = {}
        for provider in ("openai", "anthropic", "openrouter", "nvidia"):
            api_key = api_keys.get(provider)
            if isinstance(api_key, str) and api_key.strip():
                provider_configs[provider] = {"api_key": api_key.strip()}
                if provider == "nvidia":
                    provider_configs[provider]["base_url"] = "https://integrate.api.nvidia.com/v1"
        if provider_configs:
            register_all_providers(provider_configs)
    if "default_model" in payload:
        model = str(payload["default_model"])
        available = await registry.list_all_models()
        model_ids = {item.id for items in available.values() for item in items}
        if model and model_ids and model not in model_ids:
            raise HTTPException(status_code=400, detail="Selected model is not available")
        settings["default_model"] = model
    if "temperature" in payload:
        temperature = float(payload["temperature"])
        if not 0 <= temperature <= 2:
            raise HTTPException(status_code=400, detail="Temperature must be between 0 and 2")
        settings["temperature"] = temperature
    if "max_tokens" in payload:
        max_tokens = int(payload["max_tokens"])
        if not 1 <= max_tokens <= 1_000_000:
            raise HTTPException(status_code=400, detail="Max tokens must be between 1 and 1000000")
        settings["max_tokens"] = max_tokens
    if "context_mode" in payload:
        context_mode = str(payload["context_mode"])
        if context_mode not in {"auto", "fixed"}:
            raise HTTPException(status_code=400, detail="Context mode must be auto or fixed")
        settings["context_mode"] = context_mode
    if "theme" in payload:
        theme = str(payload["theme"])
        if theme not in {"system", "light", "dark"}:
            raise HTTPException(status_code=400, detail="Theme must be system, light, or dark")
        settings["theme"] = theme
    if "auto_save" in payload:
        settings["auto_save"] = bool(payload["auto_save"])
    result = settings.copy()
    result["configured_providers"] = _configured_provider_names()
    return result


@app.post("/api/auth/login")
async def login(payload: dict[str, Any]) -> dict[str, str]:
    username = str(payload.get("username", DEFAULT_USERNAME))
    password = str(payload.get("password", ""))
    if username != DEFAULT_USERNAME or password != DEFAULT_PASSWORD:
        raise HTTPException(status_code=http_status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    return {"token": _issue_token(username), "user": username}


@app.get("/api/sessions")
async def list_sessions(user_id: str = Depends(require_auth)) -> list[dict[str, Any]]:
    return [asdict(session) for session in SESSIONS.values() if session.user_id == user_id]


@app.post("/api/sessions")
async def create_session(payload: dict[str, Any], user_id: str = Depends(require_auth)) -> dict[str, Any]:
    title = str(payload.get("title") or "New Session")
    session = _get_or_create_session(None, user_id, title)
    return asdict(session)


@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str, user_id: str = Depends(require_auth)) -> dict[str, Any]:
    session = SESSIONS.get(session_id)
    if not session:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Session not found")
    if session.user_id != user_id:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="Session does not belong to this user")
    return asdict(session)


@app.post("/api/chat")
async def chat_endpoint(
    payload: dict[str, Any],
    user_id: str = Depends(require_auth),
) -> dict[str, Any]:
    messages = payload.get("messages", [])
    user_settings = _settings_for(user_id)
    model = payload.get("model") or user_settings["default_model"]
    session_id = payload.get("session_id")
    session = _get_or_create_session(str(session_id) if session_id else None, user_id)

    converted = [ChatMessage(role=m.get("role", "user"), content=m.get("content", "")) for m in messages]
    try:
        response = await conversation_loop.process_prompt(
            session.id,
            converted,
            model,
            temperature=float(user_settings["temperature"]),
            max_tokens=int(user_settings["max_tokens"]),
            context_mode=str(user_settings["context_mode"]),
            stream=False,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    assistant_message = {
        "role": "assistant",
        "content": response.content,
        "model": response.model,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    session.messages.append({"role": "assistant", "content": response.content, "timestamp": assistant_message["timestamp"]})
    session.updated_at = datetime.now(UTC)

    return {
        "id": session.id,
        "role": "assistant",
        "content": response.content,
        "model": response.model,
        "provider": response.provider.value if hasattr(response.provider, "value") else str(response.provider),
    }


@app.post("/api/chat/stream")
async def chat_stream_endpoint(
    payload: dict[str, Any],
    user_id: str = Depends(require_auth),
) -> StreamingResponse:
    """Streaming chat endpoint — returns SSE chunks."""
    messages = payload.get("messages", [])
    user_settings = _settings_for(user_id)
    model = payload.get("model") or user_settings["default_model"]
    session_id = payload.get("session_id")
    session = _get_or_create_session(str(session_id) if session_id else None, user_id)

    converted = [ChatMessage(role=m.get("role", "user"), content=m.get("content", "")) for m in messages]

    async def generate() -> AsyncIterator[str]:
        try:
            response = await conversation_loop.process_prompt(
                session.id,
                converted,
                model,
                temperature=float(user_settings["temperature"]),
                max_tokens=int(user_settings["max_tokens"]),
                context_mode=str(user_settings["context_mode"]),
                stream=True,
            )
            if hasattr(response, "__aiter__"):
                async for chunk in response:
                    yield f"data: {json.dumps({'content': chunk.content, 'done': False})}\n\n"
                yield f"data: {json.dumps({'done': True, 'session_id': session.id})}\n\n"
            else:
                yield f"data: {json.dumps({'content': response.content, 'done': True, 'session_id': session.id})}\n\n"
        except RuntimeError as exc:
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")



# Memory API
@app.get("/api/memory")
async def get_memory(user_id: str = Depends(require_auth), type: str = "all", search: str = ""):
    """Get memory items."""
    try:
        engine = MemoryEngine()
        items = engine.search(user_id, type, search) if search else engine.list(user_id, type)
        return {"memories": [{"id": m.id, "type": m.type, "content": m.content, "timestamp": str(m.timestamp), "tags": m.tags} for m in items]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/memory")
async def clear_memory(user_id: str = Depends(require_auth)):
    """Clear all memory."""
    try:
        engine = MemoryEngine()
        engine.clear(user_id)
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Skills Marketplace API
@app.get("/api/skills/marketplace")
async def get_marketplace(user_id: str = Depends(require_auth)):
    """Get skills marketplace repos."""
    try:
        repos = marketplace.get_repos()
        return {"repos": repos}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/skills/install")
async def install_skill(user_id: str = Depends(require_auth), payload: dict[str, Any] = None):
    """Install a skill from marketplace."""
    try:
        repo_id = payload.get("repoId") if payload else None
        result = marketplace.install(repo_id)
        return {"success": True, "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Projects API
@app.get("/api/projects")
async def get_projects(user_id: str = Depends(require_auth)):
    """Get user projects."""
    try:
        graph = KnowledgeGraph()
        projects = graph.list_projects(user_id)
        return {"projects": projects}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/projects")
async def create_project(user_id: str = Depends(require_auth), payload: dict[str, Any] = None):
    """Create a new project."""
    try:
        name = payload.get("name", "") if payload else ""
        path = payload.get("path", "") if payload else ""
        description = payload.get("description", "") if payload else ""
        graph = KnowledgeGraph()
        project = graph.create_project(user_id, name, path, description)
        return {"success": True, "project": project}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.websocket("/api/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()

    try:
        auth_packet = await websocket.receive_json()
        token = str(auth_packet.get("token", "")) if isinstance(auth_packet, dict) else ""
        user_id = _validate_token(token) if token else "anonymous"
    except (WebSocketDisconnect, json.JSONDecodeError, ValueError):
        await websocket.send_json({"type": "error", "message": "Authentication required for WebSocket"})
        await websocket.close()
        return

    await websocket.send_json({"type": "connected", "status": "ok", "user": user_id})

    try:
        while True:
            raw = await websocket.receive_text()
            payload = json.loads(raw)
            method = payload.get("method")
            params = payload.get("params", {})

            if method == "prompt.submit":
                session_id = str(params.get("session_id", "default"))
                session = _get_or_create_session(session_id, user_id, params.get("title"))
                user_settings = _settings_for(user_id)
                messages = [
                    ChatMessage(role=item.get("role", "user"), content=item.get("content", ""))
                    for item in params.get("messages", [])
                ]
                model = params.get("model") or user_settings["default_model"]
                try:
                    response = await conversation_loop.process_prompt(
                        session.id,
                        messages,
                        model,
                        temperature=float(user_settings["temperature"]),
                        max_tokens=int(user_settings["max_tokens"]),
                        context_mode=str(user_settings["context_mode"]),
                        stream=True,
                    )
                except RuntimeError as exc:
                    await websocket.send_json({"type": "error", "message": str(exc)})
                    continue
                if hasattr(response, "__aiter__"):
                    async for chunk in response:
                        await websocket.send_json({"type": "message.delta", "content": chunk.content})
                    await websocket.send_json({"type": "message.complete", "session_id": session.id})
                else:
                    await websocket.send_json({"type": "message.complete", "content": response.content, "session_id": session.id})
            elif method == "session.create":
                session_id = str(params.get("session_id") or secrets.token_urlsafe(12))
                session = _get_or_create_session(session_id, user_id, params.get("title"))
                await websocket.send_json({"type": "session.created", "session_id": session.id})
            elif method == "session.list":
                await websocket.send_json({"type": "session.list", "sessions": [session.id for session in SESSIONS.values() if session.user_id == user_id]})
    except WebSocketDisconnect:
        return
    except json.JSONDecodeError:
        await websocket.send_json({"type": "error", "message": "Invalid JSON payload"})


# ── JSON-RPC WebSocket (desktop + web) ─────────────────

@app.websocket("/ws")
async def jsonrpc_websocket(websocket: WebSocket) -> None:
    """JSON-RPC WebSocket endpoint for desktop and web surfaces.

    Mirrors Hermes @hermes/shared JsonRpcClient pattern.
    Desktop and web both connect here for real-time communication.
    """
    await websocket.accept()

    try:
        auth_packet = await websocket.receive_json()
        token = str(auth_packet.get("token", "")) if isinstance(auth_packet, dict) else ""
        user_id = _validate_token(token) if token else "anonymous"
    except (WebSocketDisconnect, json.JSONDecodeError, ValueError):
        await websocket.send_json({"jsonrpc": "2.0", "error": {"code": -32600, "message": "Authentication required"}})
        await websocket.close()
        return

    await websocket.send_json({"jsonrpc": "2.0", "method": "connected", "params": {"user": user_id}})

    delegator = _delegator

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                request = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}})
                continue

            rpc_id = request.get("id")
            method = request.get("method")
            params = request.get("params", [])

            if method == "chat.send":
                session_id = str(params[0] if params else "default")
                message = str(params[1] if len(params) > 1 else "")
                session = _get_or_create_session(session_id, user_id)
                user_settings = _settings_for(user_id)
                model = user_settings.get("default_model", "gpt-4o-mini")
                try:
                    response = await conversation_loop.process_prompt(
                        session.id,
                        [ChatMessage(role="user", content=message)],
                        model,
                        temperature=float(user_settings.get("temperature", 0.7)),
                        max_tokens=int(user_settings.get("max_tokens", 4096)),
                        context_mode=str(user_settings.get("context_mode", "standard")),
                        stream=True,
                    )
                    if hasattr(response, "__aiter__"):
                        async for chunk in response:
                            await websocket.send_json({"jsonrpc": "2.0", "id": rpc_id, "result": chunk.content})
                        await websocket.send_json({"jsonrpc": "2.0", "method": "chat.complete", "params": {"session_id": session.id}})
                    else:
                        await websocket.send_json({"jsonrpc": "2.0", "id": rpc_id, "result": response.content})
                except RuntimeError as exc:
                    await websocket.send_json({"jsonrpc": "2.0", "id": rpc_id, "error": {"code": -32000, "message": str(exc)}})

            elif method == "session.list":
                sessions = [s.id for s in SESSIONS.values() if s.user_id == user_id]
                await websocket.send_json({"jsonrpc": "2.0", "id": rpc_id, "result": sessions})

            elif method == "session.create":
                session_id = secrets.token_urlsafe(12)
                session = _get_or_create_session(session_id, user_id)
                await websocket.send_json({"jsonrpc": "2.0", "id": rpc_id, "result": {"session_id": session.id}})

            elif method == "tasks.list":
                tasks = delegator.list_tasks()
                await websocket.send_json({"jsonrpc": "2.0", "id": rpc_id, "result": [{"task_id": t.task_id, "goal": t.goal, "status": t.status.value} for t in tasks]})

            elif method == "tasks.delegate":
                goal = str(params[0] if params else "")
                task = delegator.delegate(goal)
                await websocket.send_json({"jsonrpc": "2.0", "id": rpc_id, "result": {"task_id": task.task_id, "status": task.status.value}})

            elif method == "server.status":
                await websocket.send_json({"jsonrpc": "2.0", "id": rpc_id, "result": {"status": "running", "version": "0.1.1"}})

            elif method == "settings.models":
                provider_name = str(params[0] if params else "openai")
                try:
                    from xcopilot.core.model_providers import PROVIDER_API_MODES, register_all_providers
                    from xcopilot.core.models import ModelCapability

                    mode = PROVIDER_API_MODES.get(provider_name)
                    if not mode:
                        await websocket.send_json({"jsonrpc": "2.0", "id": rpc_id, "error": {"code": -32000, "message": f"Unknown provider: {provider_name}"}})
                        continue
                    secrets_path = get_secrets_path()
                    api_key = ""
                    if secrets_path.exists():
                        import re
                        content = secrets_path.read_text(encoding="utf-8")
                        match = re.search(r"^OPENAI_API_KEY=(.+)$", content, re.MULTILINE)
                        if match:
                            api_key = match.group(1)
                    if api_key:
                        register_all_providers({provider_name: {"api_key": api_key}})
                    available = await registry.list_all_models()
                    provider_models = available.get(provider_name, [])
                    models = [
                        {"id": m.id, "name": m.name}
                        for m in provider_models
                        if ModelCapability.CHAT in m.capabilities
                    ]
                    await websocket.send_json({"jsonrpc": "2.0", "id": rpc_id, "result": {"models": models}})
                except Exception as exc:
                    await websocket.send_json({"jsonrpc": "2.0", "id": rpc_id, "error": {"code": -32000, "message": str(exc)}})

            else:
                await websocket.send_json({"jsonrpc": "2.0", "id": rpc_id, "error": {"code": -32601, "message": f"Method not found: {method}"}})

    except WebSocketDisconnect:
        return


# ── Delegation API ────────────────────────────────────────

_delegator = TaskDelegator()


def _record_delegation_result(task_id: str, goal: str, status: str,
                               result: str | None = None, error: str | None = None) -> None:
    """Persist delegation result to memory."""
    try:
        mem = MemoryEngine()
        mem.record_delegation(task_id, goal, status, result, error)
    except Exception:
        pass  # best-effort; never fail the API


@app.post("/api/delegation/delegate")
async def delegation_delegate(payload: dict[str, Any], user_id: str = Depends(require_auth)):
    """Delegate a task to an X-Copilot subagent."""
    goal = payload.get("goal", "")
    if not goal:
        raise HTTPException(status_code=400, detail="goal is required")
    role = payload.get("role", "leaf")
    model = payload.get("model")
    toolsets = payload.get("allowed_toolsets")
    permission_mode = payload.get("permission_mode", "standard")
    metadata = payload.get("metadata", {})
    context = payload.get("context")

    task = _delegator.delegate(
        goal, context=context, role=role, model=model,
        allowed_toolsets=tuple(toolsets or []), metadata=metadata,
    )
    return {"task_id": task.task_id, "status": task.status.value, "role": role}


@app.post("/api/delegation/delegate/batch")
async def delegation_delegate_batch(payload: dict[str, Any], user_id: str = Depends(require_auth)):
    """Delegate multiple tasks in parallel."""
    goals = payload.get("goals", [])
    if not goals:
        raise HTTPException(status_code=400, detail="goals is required (non-empty list)")
    role = payload.get("role", "leaf")
    model = payload.get("model")
    toolsets = payload.get("allowed_toolsets")
    permission_mode = payload.get("permission_mode", "standard")
    context = payload.get("context")

    _delegator._pipeline.set_mode(PermissionMode(permission_mode.lower()))
    tasks = [_delegator.delegate(g, context=context, role=role, model=model,
                                 allowed_toolsets=tuple(toolsets or [])) for g in goals]
    results = await _delegator.run_all()
    return {
        "tasks": [
            {"task_id": t.task_id, "goal": t.goal, "status": results[t.task_id].status.value}
            for t in tasks
        ]
    }


@app.get("/api/delegation/status/{task_id}")
async def delegation_status(task_id: str, user_id: str = Depends(require_auth)):
    """Get the status of a delegated task."""
    task = _delegator.status(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return {
        "task_id": task.task_id, "goal": task.goal, "status": task.status.value,
        "role": task.role, "created_at": task.created_at.isoformat(),
        "result": task.result, "error": task.error,
    }


@app.get("/api/delegation/tasks")
async def delegation_list(user_id: str = Depends(require_auth)):
    """List all delegated tasks."""
    status_filter = None
    tasks = _delegator.list_tasks(status_filter)
    return {
        "tasks": [
            {
                "task_id": t.task_id, "goal": t.goal, "status": t.status.value,
                "role": t.role, "created_at": t.created_at.isoformat(),
            }
            for t in tasks
        ]
    }


@app.delete("/api/delegation/tasks/{task_id}")
async def delegation_cancel(task_id: str, user_id: str = Depends(require_auth)):
    """Cancel a delegated task."""
    if not _delegator.cancel(task_id):
        raise HTTPException(status_code=404, detail="Task not found or already terminal")
    return {"task_id": task_id, "status": "cancelled"}


@app.get("/api/delegation/summary")
async def delegation_summary(user_id: str = Depends(require_auth)):
    """Get aggregated delegation statistics."""
    return _delegator.summary()


@app.get("/api/delegation/history")
async def delegation_history(limit: int = 50, user_id: str = Depends(require_auth)):
    """Get delegation history from memory."""
    mem = MemoryEngine()
    return {"history": mem.get_delegation_history(limit)}
