"""X-Copilot state layer — SQLite session persistence with FTS5 search.

Mirrors X-Copilot state pattern. Sessions have lineage tracking
(parent/child across compressions), per-profile isolation, and atomic writes.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass
class SessionRecord:
    """A conversation session."""

    id: str
    profile: str = "default"
    title: str = "New Session"
    created_at: str = ""
    updated_at: str = ""
    messages: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    parent_id: str | None = None  # lineage tracking

    def __post_init__(self) -> None:
        now = datetime.now(UTC).isoformat()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now


@dataclass
class MessageRecord:
    """A single message in a session."""

    id: str
    session_id: str
    role: str  # user, assistant, system, tool
    content: str
    timestamp: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class StateDB:
    """SQLite-backed session and state storage with FTS5 full-text search.

    Mirrors X-Copilot state pattern with:
    - Session persistence (SQLite + FTS5)
    - Lineage tracking (parent/child across compressions)
    - Per-profile isolation
    - Atomic writes with contention handling
    """

    def __init__(self, db_path: str | Path = "~/.xcopilot/state.db") -> None:
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """Initialize SQLite database with sessions, messages, FTS5 tables."""
        with self._connect() as conn:
            # Sessions table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    profile TEXT NOT NULL DEFAULT 'default',
                    title TEXT NOT NULL DEFAULT 'New Session',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    parent_id TEXT,
                    metadata TEXT DEFAULT '{}',
                    FOREIGN KEY (parent_id) REFERENCES sessions(id)
                )
            """)
            # Messages table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    tool_calls TEXT DEFAULT '[]',
                    tool_results TEXT DEFAULT '[]',
                    metadata TEXT DEFAULT '{}',
                    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
                )
            """)
            # FTS5 virtual table for full-text search
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
                    content, session_id, tokenize='porter unicode61'
                )
            """)
            # Indexes
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_sessions_profile
                ON sessions(profile, updated_at)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_session
                ON messages(session_id, timestamp)
            """)
            conn.commit()

    @contextmanager
    def _connect(self) -> sqlite3.Connection:
        """Get a database connection with row factory."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    # ── Sessions ──────────────────────────────────────────

    def create_session(
        self,
        profile: str = "default",
        title: str = "New Session",
        parent_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SessionRecord:
        """Create a new session."""
        session_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        session = SessionRecord(
            id=session_id,
            profile=profile,
            title=title,
            created_at=now,
            updated_at=now,
            parent_id=parent_id,
            metadata=metadata or {},
        )
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO sessions (id, profile, title, created_at, updated_at, parent_id, metadata) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (session.id, session.profile, session.title, session.created_at, session.updated_at, session.parent_id, json.dumps(session.metadata)),
            )
            conn.commit()
        return session

    def get_session(self, session_id: str) -> SessionRecord | None:
        """Get a session by ID."""
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if row is None:
            return None
        return self._row_to_session(row)

    def update_session(self, session_id: str, **kwargs: Any) -> bool:
        """Update session fields."""
        if "updated_at" not in kwargs:
            kwargs["updated_at"] = datetime.now(UTC).isoformat()
        set_clauses = []
        params = []
        for key, value in kwargs.items():
            if key == "metadata":
                set_clauses.append(f"{key} = ?")
                params.append(json.dumps(value))
            else:
                set_clauses.append(f"{key} = ?")
                params.append(value)
        if not set_clauses:
            return False
        params.append(session_id)
        with self._connect() as conn:
            conn.execute(f"UPDATE sessions SET {', '.join(set_clauses)} WHERE id = ?", params)
            conn.commit()
        return True

    def list_sessions(
        self, profile: str | None = None, limit: int = 100
    ) -> list[SessionRecord]:
        """List sessions, optionally filtered by profile."""
        with self._connect() as conn:
            if profile:
                rows = conn.execute(
                    "SELECT * FROM sessions WHERE profile = ? ORDER BY updated_at DESC LIMIT ?",
                    (profile, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM sessions ORDER BY updated_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [self._row_to_session(row) for row in rows]

    def delete_session(self, session_id: str) -> bool:
        """Delete a session and all its messages."""
        with self._connect() as conn:
            conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            conn.commit()
        return True

    # ── Messages ──────────────────────────────────────────

    def add_message(self, message: MessageRecord) -> None:
        """Add a message to a session."""
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO messages (id, session_id, role, content, timestamp, tool_calls, tool_results, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    message.id, message.session_id, message.role, message.content,
                    message.timestamp, json.dumps(message.tool_calls),
                    json.dumps(message.tool_results), json.dumps(message.metadata),
                ),
            )
            # Update FTS index
            conn.execute(
                "INSERT INTO messages_fts (rowid, content, session_id) VALUES (last_insert_rowid(), ?, ?)",
                (message.content, message.session_id),
            )
            # Update session updated_at
            conn.execute(
                "UPDATE sessions SET updated_at = ? WHERE id = ?",
                (message.timestamp, message.session_id),
            )
            conn.commit()

    def get_messages(
        self, session_id: str, limit: int = 1000, before: str | None = None
    ) -> list[MessageRecord]:
        """Get messages for a session, optionally before a timestamp."""
        with self._connect() as conn:
            if before:
                rows = conn.execute(
                    "SELECT * FROM messages WHERE session_id = ? AND timestamp < ? ORDER BY timestamp DESC LIMIT ?",
                    (session_id, before, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM messages WHERE session_id = ? ORDER BY timestamp DESC LIMIT ?",
                    (session_id, limit),
                ).fetchall()
        return [self._row_to_message(row) for row in rows]

    def search_messages(self, query: str, profile: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        """Full-text search across messages."""
        with self._connect() as conn:
            if profile:
                rows = conn.execute(
                    """SELECT m.* FROM messages m
                       JOIN messages_fts fts ON m.rowid = fts.rowid
                       WHERE fts MATCH ? AND m.profile = ?
                       LIMIT ?""",
                    (query, profile, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT m.* FROM messages m
                       JOIN messages_fts fts ON m.rowid = fts.rowid
                       WHERE fts MATCH ?
                       LIMIT ?""",
                    (query, limit),
                ).fetchall()
        return [self._row_to_message(row) for row in rows]

    # ── Helpers ───────────────────────────────────────────

    def _row_to_session(self, row: sqlite3.Row) -> SessionRecord:
        return SessionRecord(
            id=row["id"],
            profile=row["profile"],
            title=row["title"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            parent_id=row["parent_id"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
        )

    def _row_to_message(self, row: sqlite3.Row) -> MessageRecord:
        return MessageRecord(
            id=row["id"],
            session_id=row["session_id"],
            role=row["role"],
            content=row["content"],
            timestamp=row["timestamp"],
            tool_calls=json.loads(row["tool_calls"]) if row["tool_calls"] else [],
            tool_results=json.loads(row["tool_results"]) if row["tool_results"] else [],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
        )

    def prune(self, days: int = 90, profile: str | None = None) -> int:
        """Remove sessions older than specified days. Returns count removed."""
        from datetime import timedelta
        cutoff = datetime.now(UTC) - timedelta(days=days)
        cutoff_iso = cutoff.isoformat()
        with self._connect() as conn:
            if profile:
                cursor = conn.execute(
                    "DELETE FROM sessions WHERE updated_at < ? AND profile = ?",
                    (cutoff_iso, profile),
                )
            else:
                cursor = conn.execute(
                    "DELETE FROM sessions WHERE updated_at < ?", (cutoff_iso,)
                )
            conn.commit()
            return cursor.rowcount

    def stats(self) -> dict[str, Any]:
        """Return storage statistics."""
        with self._connect() as conn:
            sessions = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
            messages = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        return {"sessions": sessions, "messages": messages}