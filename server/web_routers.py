"""FastAPI routers for the X-Copilot web dashboard.

Mirrors X-Copilot CLI web_routers pattern — one router per surface.
Each router handles its own endpoints and uses the shared app state.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, status as http_status

from server.auth import require_auth
from xcopilot.config import load_config, get_profile_home
from xcopilot.state.db import StateDB
from xcopilot.cron.scheduler import CronScheduler
from xcopilot.gateway.runner import GatewayRunner





# ── Chat Router ──────────────────────────────────────────

chat_router = APIRouter(prefix="/api/chat", tags=["chat"])


@chat_router.post("/")
async def chat_endpoint(
    payload: dict[str, Any],
    _token: str = Depends(require_auth),
) -> dict[str, Any]:
    """Chat endpoint — process a user message and return assistant response."""
    from xcopilot.core.conversation_loop import ConversationLoop

    session_id = payload.get("session_id", "default")
    messages = payload.get("messages", [])
    model = payload.get("model", "gpt-4o-mini")

    loop = ConversationLoop()
    response = await loop.process_prompt(
        session_id, messages, model, stream=False
    )
    return {
        "session_id": session_id,
        "response": response.content if hasattr(response, "content") else str(response),
    }


# ── Sessions Router ──────────────────────────────────────

sessions_router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@sessions_router.get("/")
async def list_sessions(
    profile: str = "default",
    _token: str = Depends(require_auth),
) -> dict[str, Any]:
    """List all sessions for a profile."""
    state = StateDB()
    sessions = state.list_sessions(profile=profile)
    return {
        "sessions": [
            {
                "id": s.id,
                "title": s.title,
                "created_at": s.created_at,
                "updated_at": s.updated_at,
                "parent_id": s.parent_id,
            }
            for s in sessions
        ]
    }


@sessions_router.post("/")
async def create_session(
    payload: dict[str, Any] | None = None,
    profile: str = "default",
    _token: str = Depends(require_auth),
) -> dict[str, Any]:
    """Create a new session."""
    state = StateDB()
    payload = payload or {}
    session = state.create_session(
        profile=profile,
        title=payload.get("title", "New Session"),
        parent_id=payload.get("parent_id"),
    )
    return {
        "id": session.id,
        "title": session.title,
        "created_at": session.created_at,
    }


@sessions_router.get("/{session_id}")
async def get_session(
    session_id: str,
    _token: str = Depends(require_auth),
) -> dict[str, Any]:
    """Get a session by ID."""
    state = StateDB()
    session = state.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "id": session.id,
        "title": session.title,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
        "parent_id": session.parent_id,
        "message_count": len(state.get_messages(session_id)),
    }


# ── Settings helpers ───────────────────────────

def load_settings() -> dict[str, Any]:
    """Load current settings for API responses."""
    config = load_config()
    secrets_path = get_secrets_path()
    api_key = ""
    if secrets_path.exists():
        import re
        content = secrets_path.read_text(encoding="utf-8")
        match = re.search(r"^OPENAI_API_KEY=(.+)$", content, re.MULTILINE)
        if match:
            api_key = match.group(1)
    return {
        "profile": config.get("profile", "default"),
        "permission_mode": config.get("permission_mode", "standard"),
        "model": config.get("model", "gpt-4o-mini"),
        "provider": config.get("provider", "openai"),
        "api_key": api_key,
        "server": config.get("server", {}),
        "ui": config.get("ui", {}),
    }


# ── Settings Router ──────────────────────────────────────

settings_router = APIRouter(prefix="/api/settings", tags=["settings"])


@settings_router.get("/")
async def get_settings(
    _token: str = Depends(require_auth),
) -> dict[str, Any]:
    """Get current settings."""
    config = load_config()
    secrets_path = get_secrets_path()
    api_key = ""
    if secrets_path.exists():
        import re
        content = secrets_path.read_text(encoding="utf-8")
        match = re.search(r"^OPENAI_API_KEY=(.+)$", content, re.MULTILINE)
        if match:
            api_key = match.group(1)
    return {
        "profile": config.get("profile", "default"),
        "permission_mode": config.get("permission_mode", "standard"),
        "model": config.get("model", "gpt-4o-mini"),
        "provider": config.get("provider", "openai"),
        "api_key": api_key,
        "server": config.get("server", {}),
        "ui": config.get("ui", {}),
    }


@settings_router.put("/")
async def update_settings(
    payload: dict[str, Any],
    _token: str = Depends(require_auth),
) -> dict[str, Any]:
    """Update settings. Handles api_key separately (stored in .env)."""
    from xcopilot.config import save_config, get_secrets_path

    config = load_config()

    # Handle api_key separately — store in .env, not config.yaml
    api_key = payload.pop("api_key", None)
    if api_key is not None:
        secrets_path = get_secrets_path()
        secrets_path.parent.mkdir(parents=True, exist_ok=True)
        # Read existing .env, update or append API key
        existing = ""
        if secrets_path.exists():
            existing = secrets_path.read_text(encoding="utf-8")
        lines = existing.splitlines()
        # Remove existing OPENAI_API_KEY line
        lines = [l for l in lines if not l.startswith("OPENAI_API_KEY=")]
        if api_key:
            lines.append(f"OPENAI_API_KEY={api_key}")
        secrets_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    for key, value in payload.items():
        if key in config:
            config[key] = value
    save_config(config)
    return {"status": "ok", "settings": load_settings()}


@settings_router.get("/models/{provider_name}")
async def list_provider_models(provider_name: str) -> dict[str, Any]:
    """List available models for a provider. Queries the provider API."""
    from xcopilot.core.model_providers import PROVIDER_API_MODES
    from xcopilot.core.models import ModelCapability, registry

    mode = PROVIDER_API_MODES.get(provider_name)
    if not mode:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider_name}")

    # Get API key from .env
    from xcopilot.config import get_secrets_path
    secrets_path = get_secrets_path()
    api_key = ""
    if secrets_path.exists():
        import re
        content = secrets_path.read_text(encoding="utf-8")
        match = re.search(r"^OPENAI_API_KEY=(.+)$", content, re.MULTILINE)
        if match:
            api_key = match.group(1)

    # Register provider with API key
    if api_key:
        registry.register(provider_name, {"api_key": api_key})

    # List models
    available = await registry.list_all_models()
    provider_models = available.get(provider_name, [])
    models = [
        {"id": m.id, "name": m.name, "provider": provider_name}
        for m in provider_models
        if ModelCapability.CHAT in m.capabilities
    ]
    return {"provider": provider_name, "models": models, "api_key_set": bool(api_key)}


# ── Cron Router ──────────────────────────────────────────

cron_router = APIRouter(prefix="/api/cron", tags=["cron"])


@cron_router.get("/")
async def list_cron_jobs(
    profile: str = "default",
    _token: str = Depends(require_auth),
) -> dict[str, Any]:
    """List all cron jobs."""
    scheduler = CronScheduler()
    jobs = scheduler.list_jobs(profile=profile)
    return {
        "jobs": [
            {
                "id": j.id,
                "name": j.name,
                "schedule": j.schedule,
                "prompt": j.prompt,
                "status": j.status.value,
                "created_at": j.created_at,
                "next_run": j.next_run,
                "run_count": j.run_count,
                "error_count": j.error_count,
            }
            for j in jobs
        ]
    }


@cron_router.post("/")
async def create_cron_job(
    payload: dict[str, Any],
    _token: str = Depends(require_auth),
) -> dict[str, Any]:
    """Create a new cron job."""
    scheduler = CronScheduler()
    job = scheduler.create(
        name=payload.get("name", "Untitled"),
        schedule=payload.get("schedule", "every hour"),
        prompt=payload.get("prompt", ""),
        profile=payload.get("profile", "default"),
        skill=payload.get("skill"),
        script=payload.get("script"),
    )
    return {
        "id": job.id,
        "name": job.name,
        "schedule": job.schedule,
        "status": job.status.value,
    }


@cron_router.post("/{job_id}/cancel")
async def cancel_cron_job(
    job_id: str,
    _token: str = Depends(require_auth),
) -> dict[str, Any]:
    """Cancel a cron job."""
    scheduler = CronScheduler()
    if scheduler.cancel(job_id):
        return {"status": "cancelled", "job_id": job_id}
    raise HTTPException(status_code=404, detail="Job not found")


@cron_router.get("/{job_id}")
async def get_cron_job(
    job_id: str,
    _token: str = Depends(require_auth),
) -> dict[str, Any]:
    """Get a cron job by ID."""
    scheduler = CronScheduler()
    job = scheduler.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "id": job.id,
        "name": job.name,
        "schedule": job.schedule,
        "prompt": job.prompt,
        "status": job.status.value,
        "created_at": job.created_at,
        "next_run": job.next_run,
        "run_count": job.run_count,
        "error_count": job.error_count,
    }


# ── Gateway Router ───────────────────────────────────────

gateway_router = APIRouter(prefix="/api/gateway", tags=["gateway"])


@gateway_router.get("/status")
async def gateway_status(
    _token: str = Depends(require_auth),
) -> dict[str, Any]:
    """Get gateway status."""
    runner = GatewayRunner()
    sessions = runner.list_sessions()
    return {
        "status": "running",
        "platforms": list(runner._adapters.keys()),
        "session_count": len(sessions),
    }


@gateway_router.get("/sessions")
async def gateway_sessions(
    platform: str | None = None,
    _token: str = Depends(require_auth),
) -> dict[str, Any]:
    """List gateway sessions."""
    runner = GatewayRunner()
    sessions = runner.list_sessions(platform=platform)
    return {
        "sessions": [
            {
                "session_key": s.session_key,
                "user_id": s.user_id,
                "platform": s.platform,
                "message_count": len(s.history),
                "updated_at": s.updated_at,
            }
            for s in sessions
        ]
    }


# ── Delegation Router ────────────────────────────────────

delegation_router = APIRouter(prefix="/api/delegation", tags=["delegation"])


@delegation_router.post("/delegate")
async def delegation_delegate(
    payload: dict[str, Any],
    _token: str = Depends(require_auth),
) -> dict[str, Any]:
    """Delegate a task to an X-Copilot subagent."""
    from xcopilot.core.delegation import TaskDelegator
    from xcopilot.permission.pipeline import PermissionMode

    goal = payload.get("goal", "")
    if not goal:
        raise HTTPException(status_code=400, detail="goal is required")

    context = payload.get("context")
    role = payload.get("role", "leaf")
    model = payload.get("model")
    toolsets = payload.get("allowed_toolsets")
    permission_mode_str = payload.get("permission_mode", "standard")
    metadata = payload.get("metadata", {})
    background = payload.get("background", False)

    try:
        mode = PermissionMode(permission_mode_str.lower())
    except ValueError:
        mode = PermissionMode.STANDARD

    delegator = TaskDelegator(
        project_root=str(get_profile_home()),
        permission_mode=mode,
    )
    task = delegator.delegate(
        goal, context=context, role=role, model=model,
        allowed_toolsets=tuple(toolsets or []), metadata=metadata,
    )
    return {
        "task_id": task.task_id,
        "goal": task.goal,
        "status": task.status.value,
        "role": task.role,
        "created_at": task.created_at.isoformat(),
    }


@delegation_router.get("/status/{task_id}")
async def delegation_status(
    task_id: str,
    _token: str = Depends(require_auth),
) -> dict[str, Any]:
    """Get delegation task status."""
    from xcopilot.core.delegation import TaskDelegator

    delegator = TaskDelegator(project_root=str(get_profile_home()))
    task = delegator.status(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return {
        "task_id": task.task_id,
        "goal": task.goal,
        "status": task.status.value,
        "role": task.role,
        "created_at": task.created_at.isoformat(),
        "error": task.error,
    }


@delegation_router.get("/tasks")
async def delegation_list(
    status: str | None = None,
    _token: str = Depends(require_auth),
) -> dict[str, Any]:
    """List delegation tasks."""
    from xcopilot.core.delegation import TaskDelegator, TaskStatus

    delegator = TaskDelegator(project_root=str(get_profile_home()))
    tasks = delegator.list_tasks(
        TaskStatus(status) if status else None
    )
    return {
        "tasks": [
            {
                "task_id": t.task_id,
                "goal": t.goal,
                "status": t.status.value,
                "role": t.role,
                "created_at": t.created_at.isoformat(),
            }
            for t in tasks
        ]
    }


@delegation_router.get("/summary")
async def delegation_summary(
    _token: str = Depends(require_auth),
) -> dict[str, Any]:
    """Get delegation summary statistics."""
    from xcopilot.core.delegation import TaskDelegator

    delegator = TaskDelegator(project_root=str(get_profile_home()))
    stats = delegator.summary()
    return stats


@delegation_router.get("/history")
async def delegation_history(
    limit: int = 50,
    _token: str = Depends(require_auth),
) -> dict[str, Any]:
    """Get delegation history from memory."""
    from xcopilot.memory import MemoryEngine

    memory = MemoryEngine()
    history = memory.get_delegation_history(limit=limit)
    return {"history": history}


# ── Tools Router ─────────────────────────────────────────

tools_router = APIRouter(prefix="/api/tools", tags=["tools"])


@tools_router.get("/")
async def list_tools(
    toolset: str | None = None,
    _token: str = Depends(require_auth),
) -> dict[str, Any]:
    """List all registered tools, optionally filtered by toolset."""
    from xcopilot.tools.registry import registry

    tools = registry.list_tools(toolset)
    return {
        "tools": [
            {
                "name": spec.name,
                "description": spec.description,
                "toolset": spec.toolset,
                "schema": spec.schema,
                "service_gated": spec.service_gated,
                "requires_approval": spec.requires_approval,
            }
            for spec in tools
        ]
    }


@tools_router.get("/schemas")
async def get_tool_schemas(
    _token: str = Depends(require_auth),
) -> dict[str, Any]:
    """Get all tool schemas."""
    from xcopilot.tools.registry import registry

    return {"schemas": registry.schemas()}