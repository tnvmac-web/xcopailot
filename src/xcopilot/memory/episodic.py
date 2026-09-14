"""Episodic memory — SQLite + JSONL event store."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass
class EpisodicEvent:
    """A single episodic memory event."""

    id: int | None = None
    timestamp: datetime | None = None
    type: str = ""
    payload: dict = None
    project: str = ""
    session_id: str = ""

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(UTC)
        if self.payload is None:
            self.payload = {}


class EpisodicMemory:
    """SQLite-backed episodic memory with JSONL backup."""

    def __init__(
        self,
        db_path: str = "episodic.db",
        jsonl_path: str = "episodic.jsonl",
    ) -> None:
        self.db_path = Path(db_path)
        self.jsonl_path = Path(jsonl_path)
        self._init_db()

    def _init_db(self) -> None:
        """Initialize SQLite database with events table and index."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    project TEXT,
                    session_id TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_events_project_time
                ON events(project, timestamp)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_events_session
                ON events(session_id)
            """)
            conn.commit()

    def _row_to_event(self, row: tuple) -> EpisodicEvent:
        """Convert SQLite row to EpisodicEvent."""
        return EpisodicEvent(
            id=row[0],
            timestamp=datetime.fromisoformat(row[1]),
            type=row[2],
            payload=json.loads(row[3]),
            project=row[4] or "",
            session_id=row[5],
        )

    def append(self, event: EpisodicEvent) -> int:
        """Append an event to SQLite and JSONL. Returns the event ID."""
        timestamp = event.timestamp.isoformat()
        payload_json = json.dumps(event.payload, ensure_ascii=False)

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO events (timestamp, type, payload, project, session_id)
                VALUES (?, ?, ?, ?, ?)
                """,
                (timestamp, event.type, payload_json, event.project, event.session_id),
            )
            conn.commit()
            event_id = cursor.lastrowid

        # Write to JSONL backup
        jsonl_record = {
            "id": event_id,
            "timestamp": timestamp,
            "type": event.type,
            "payload": event.payload,
            "project": event.project,
            "session_id": event.session_id,
        }
        with self.jsonl_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(jsonl_record, ensure_ascii=False) + "\n")

        return event_id

    def query(
        self,
        project: str = "",
        type: str | None = None,
        session_id: str | None = None,
        limit: int = 100,
    ) -> list[EpisodicEvent]:
        """Query events with optional filters. Returns newest first."""
        conditions = []
        params = []

        if project:
            conditions.append("project = ?")
            params.append(project)

        if type:
            conditions.append("type = ?")
            params.append(type)

        if session_id:
            conditions.append("session_id = ?")
            params.append(session_id)

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
        params.append(limit)

        sql = f"""
            SELECT id, timestamp, type, payload, project, session_id
            FROM events
            {where_clause}
            ORDER BY timestamp DESC
            LIMIT ?
        """

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(sql, params)
            return [self._row_to_event(tuple(row)) for row in cursor.fetchall()]

    def prune(self, days: int = 90) -> int:
        """Remove events older than specified days. Returns count removed."""
        from datetime import timedelta

        cutoff = datetime.now(UTC) - timedelta(days=days)
        cutoff_iso = cutoff.isoformat()

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM events WHERE timestamp < ?",
                (cutoff_iso,),
            )
            conn.commit()
            return cursor.rowcount
