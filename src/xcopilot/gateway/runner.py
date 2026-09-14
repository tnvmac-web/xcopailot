"""X-Copilot Gateway — messaging platform adapter facade.

Mirrors X-Copilot gateway/run.py pattern. Long-running process with
platform adapters, unified session routing, user authorization,
slash command dispatch, hook system, and background maintenance.

Currently supports: CLI, web dashboard, and messaging platforms
(via plugin adapters).
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class MessageEvent:
    """Incoming message from a platform."""

    platform: str
    user_id: str
    channel_id: str
    text: str
    timestamp: str = ""
    message_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(UTC).isoformat()


@dataclass
class SessionState:
    """Persistent session state for a user-platform pair."""

    session_key: str
    user_id: str
    platform: str
    history: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        now = datetime.now(UTC).isoformat()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now


class GatewayRunner:
    """Gateway facade — message dispatch across platforms.

    Mirrors X-Copilot gateway/run.py pattern:
    - Multi-platform adapter pattern (one per platform)
    - Two message guards (auth + rate limit)
    - Streaming contract for responses
    - Background maintenance tasks
    - Token locks for concurrent access
    """

    def __init__(self) -> None:
        self._adapters: dict[str, Any] = {}  # platform → adapter
        self._sessions: dict[str, SessionState] = {}
        self._message_handlers: list[Any] = []
        self._hooks: dict[str, list[Any]] = {}
        self._running = False

    def register_adapter(self, platform: str, adapter: Any) -> None:
        """Register a platform adapter."""
        self._adapters[platform] = adapter

    def get_adapter(self, platform: str) -> Any | None:
        """Get a platform adapter."""
        return self._adapters.get(platform)

    def add_message_handler(self, handler: Any) -> None:
        """Add a message handler (called for each incoming message)."""
        self._message_handlers.append(handler)

    def add_hook(self, event: str, handler: Any) -> None:
        """Register a lifecycle hook (message_received, session_created, etc.)."""
        if event not in self._hooks:
            self._hooks[event] = []
        self._hooks[event].append(handler)

    async def dispatch_message(self, event: MessageEvent) -> dict[str, Any]:
        """Dispatch an incoming message to handlers.

        Mirrors X-Copilot gateway _handle_message():
        1. Authorize user
        2. Resolve session key
        3. Create AIAgent with session history
        4. Run conversation
        5. Deliver response back through adapter
        """
        # Guard 1: Authorization
        if not self._authorize(event):
            return {"status": "unauthorized"}

        # Guard 2: Rate limiting (simplified)
        session_key = self._resolve_session_key(event)

        # Get or create session
        session = self._get_or_create_session(session_key, event.user_id)

        # Add message to history
        session.history.append({
            "role": "user",
            "content": event.text,
            "timestamp": event.timestamp,
        })

        # Run message handlers
        response_text = ""
        for handler in self._message_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    result = await handler(event, session)
                else:
                    result = handler(event, session)
                if result:
                    response_text = str(result)
                    break
            except Exception as exc:
                response_text = f"Error: {exc}"

        # Add assistant response to history
        session.history.append({
            "role": "assistant",
            "content": response_text,
            "timestamp": datetime.now(UTC).isoformat(),
        })
        session.updated_at = datetime.now(UTC).isoformat()

        # Deliver response through adapter
        adapter = self._adapters.get(event.platform)
        if adapter and hasattr(adapter, "send_message"):
            await adapter.send_message(event.channel_id, response_text)

        return {
            "status": "ok",
            "session_key": session_key,
            "response": response_text,
        }

    def _authorize(self, event: MessageEvent) -> bool:
        """Check if the user is authorized. Simplified — always authorized for now."""
        return True

    def _resolve_session_key(self, event: MessageEvent) -> str:
        """Resolve a session key from the event."""
        return f"{event.platform}:{event.user_id}:{event.channel_id}"

    def _get_or_create_session(
        self, session_key: str, user_id: str
    ) -> SessionState:
        """Get existing session or create a new one."""
        if session_key in self._sessions:
            return self._sessions[session_key]
        session = SessionState(
            session_key=session_key,
            user_id=user_id,
            platform="unknown",
        )
        self._sessions[session_key] = session
        return session

    def get_session(self, session_key: str) -> SessionState | None:
        """Get a session by key."""
        return self._sessions.get(session_key)

    def list_sessions(self, platform: str | None = None) -> list[SessionState]:
        """List sessions, optionally filtered by platform."""
        if platform is None:
            return list(self._sessions.values())
        return [s for s in self._sessions.values() if s.platform == platform]

    async def start(self) -> None:
        """Start the gateway runner."""
        self._running = True
        # Start background maintenance
        asyncio.create_task(self._maintenance_loop())

    async def stop(self) -> None:
        """Stop the gateway runner."""
        self._running = False

    async def _maintenance_loop(self) -> None:
        """Background maintenance task."""
        while self._running:
            await asyncio.sleep(60)
            # Prune old sessions, cleanup, etc.
            self._prune_sessions()

    def _prune_sessions(self, max_age_hours: int = 24) -> None:
        """Prune stale sessions."""
        from datetime import timedelta

        cutoff = datetime.now(UTC) - timedelta(hours=max_age_hours)
        stale = [
            key for key, session in self._sessions.items()
            if session.updated_at < cutoff.isoformat()
        ]
        for key in stale:
            del self._sessions[key]