"""Memory engine — facade composing all 5 memory layers."""

from __future__ import annotations

from pathlib import Path

from xcopilot.memory.agentmemory_backend import AgentMemoryBackend, PluggableSemanticMemory, AGENTMEMORY_AVAILABLE
from xcopilot.memory.episodic import EpisodicEvent, EpisodicMemory
from xcopilot.memory.procedural import ProceduralMemory
from xcopilot.memory.project import ProjectMemory
from xcopilot.memory.semantic import SemanticMemory
from xcopilot.memory.session import SessionMemory

__all__ = [
    "MemoryEngine",
    "EpisodicEvent",
    "EpisodicMemory",
    "ProceduralMemory",
    "ProjectMemory",
    "SemanticMemory",
    "SessionMemory",
    "AgentMemoryBackend",
    "PluggableSemanticMemory",
    "AGENTMEMORY_AVAILABLE",
]


class MemoryEngine:
    """Composes all 5 memory layers: Session, Episodic, Semantic, Procedural, Project.

    The Semantic layer can optionally use agentmemory as a backend
    instead of ChromaDB by setting backend="agentmemory".
    """

    def __init__(
        self,
        project_root: str | None = None,
        session: SessionMemory | None = None,
        episodic: EpisodicMemory | None = None,
        semantic: SemanticMemory | None = None,
        procedural: ProceduralMemory | None = None,
        project: ProjectMemory | None = None,
        backend: str | None = None,
    ) -> None:
        self.project_root = Path(project_root) if project_root else Path.cwd()

        # Session memory (in-memory, per conversation)
        self.session = session or SessionMemory()

        # Episodic memory (SQLite + JSONL)
        episodic_db = self.project_root / ".xcopilot" / "memory" / "episodic.db"
        episodic_jsonl = self.project_root / ".xcopilot" / "memory" / "episodic.jsonl"
        self.episodic = episodic or EpisodicMemory(
            db_path=str(episodic_db),
            jsonl_path=str(episodic_jsonl),
        )

        # Semantic memory (pluggable: ChromaDB or agentmemory)
        chroma_dir = self.project_root / ".xcopilot" / "memory" / "chroma"
        if backend == "agentmemory" or (backend is None and AGENTMEMORY_AVAILABLE):
            self.semantic = PluggableSemanticMemory(
                persist_dir=str(chroma_dir),
                backend="agentmemory",
                project_root=str(self.project_root),
            )
        else:
            self.semantic = semantic or SemanticMemory(persist_dir=str(chroma_dir))

        # Procedural memory (SKILL.md files)
        self.procedural = procedural or ProceduralMemory(project_root=str(self.project_root))

        # Project memory (AGENTS.md)
        self.project = project or ProjectMemory(project_root=str(self.project_root))

    # ── delegation helpers ─────────────────────────────────

    def record_delegation(self, task_id: str, goal: str, status: str,
                          result: str | None = None, error: str | None = None) -> None:
        """Append a delegation event to episodic memory."""
        from xcopilot.memory.episodic import EpisodicEvent
        event = EpisodicEvent(
            type="delegation",
            payload={
                "task_id": task_id, "goal": goal, "status": status,
                "result": result, "error": error,
            },
            project=str(self.project_root),
        )
        self.episodic.append(event)

    def get_delegation_history(self, limit: int = 50) -> list[dict[str, object]]:
        """Return recent delegation events."""
        events = self.episodic.query(type="delegation", limit=limit)
        return [
            {
                "id": e.id,
                "timestamp": e.timestamp.isoformat() if e.timestamp else None,
                "task_id": (e.payload or {}).get("task_id", ""),
                "goal": (e.payload or {}).get("goal", ""),
                "status": (e.payload or {}).get("status", ""),
                "result": (e.payload or {}).get("result"),
                "error": (e.payload or {}).get("error"),
            }
            for e in events
        ]
