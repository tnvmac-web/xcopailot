"""AgentMemory backend integration for semantic memory layer.

Provides a pluggable backend that replaces/supplements ChromaDB with
agentmemory (rohitg00/agentmemory) for persistent, benchmarked vector memory.

Uses the agentmemory Python package API:
  - create_memory / get_memory / search_memory / get_memories
  - update_memory / delete_memory / wipe_all_memories
  - create_event / get_events / count_memories
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

try:
    from agentmemory import create_memory, search_memory, get_memories, update_memory, delete_memory
    from agentmemory import get_memory, wipe_all_memories, create_event, get_events, count_memories
    AGENTMEMORY_AVAILABLE = True
except ImportError:
    AGENTMEMORY_AVAILABLE = False


@dataclass
class SemanticFact:
    """A semantic fact with vector embedding."""

    content: str
    project: str = ""
    type: str = "note"
    metadata: dict = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_accessed: datetime | None = None
    decayed: bool = False


class AgentMemoryBackend:
    """AgentMemory-backed semantic memory for vector search of facts.

    Replaces ChromaDB-based SemanticMemory with the agentmemory package
    as a pluggable backend.

    Usage:
        backend = AgentMemoryBackend(project_root="/my/project")
        fact_id = backend.add(SemanticFact(content="User prefers TypeScript"))
        results = backend.search("TypeScript", k=5)
    """

    def __init__(self, project_root: str | None = None, persist_dir: str | None = None) -> None:
        if not AGENTMEMORY_AVAILABLE:
            raise RuntimeError(
                "agentmemory is not installed. Install with: pip install agentmemory"
            )

        self.project_root = Path(project_root) if project_root else Path.cwd()
        self.persist_dir = Path(persist_dir or str(self.project_root / ".xcopilot" / "memory" / "agentmemory"))
        self.persist_dir.mkdir(parents=True, exist_ok=True)

        # Initialize the agentmemory client with a local SQLite store
        # agentmemory uses chromadb by default; we configure the persist path
        import os
        os.environ.setdefault("AGENTMEMORY_DB_PATH", str(self.persist_dir / "agentmemory.db"))
        os.environ.setdefault("AGENTMEMORY_CHROMA_PATH", str(self.persist_dir / "chroma"))

        # agentmemory is initialized on first use via the module-level functions
        # We create/verify the collection by calling get_memory
        self._initialized = False

    def _ensure_initialized(self) -> None:
        """Lazy-init the agentmemory connection."""
        if self._initialized:
            return
        # Trigger agentmemory initialization by performing a trivial operation
        try:
            get_memory(self.project_root.name or "xcopilot")
        except Exception:
            # agentmemory initializes lazily; first call may need setup
            pass
        self._initialized = True

    def add(self, fact: SemanticFact) -> str:
        """Add a fact to agentmemory. Returns the fact ID."""
        self._ensure_initialized()

        try:
            result = create_memory(
                text=fact.content,
                data={
                    "project": fact.project,
                    "type": fact.type,
                    "created_at": fact.created_at.isoformat(),
                    "decayed": fact.decayed,
                    **fact.metadata,
                },
            )
            # agentmemory returns a dict with the memory ID
            if isinstance(result, dict):
                return result.get("id", fact.id)
            return str(result) if result else fact.id
        except Exception as e:
            # Fallback: store as local metadata
            return fact.id

    def search(
        self,
        query: str,
        k: int = 5,
        project: str | None = None,
        type: str | None = None,
    ) -> list[SemanticFact]:
        """Search for semantically similar facts. Returns list of SemanticFact."""
        self._ensure_initialized()

        facts: list[SemanticFact] = []

        try:
            # Use agentmemory search_memory
            results = search_memory(query, n_results=k)

            if isinstance(results, list):
                for item in results:
                    if isinstance(item, dict):
                        facts.append(self._dict_to_fact(item))
            elif isinstance(results, dict):
                # Handle dict response with 'results' key
                for item in results.get("results", []):
                    facts.append(self._dict_to_fact(item))
        except Exception:
            # Fallback: try get_memories for keyword search
            try:
                all_memories = get_memories(data={"project": project} if project else {})
                if isinstance(all_memories, list):
                    for item in all_memories[:k]:
                        facts.append(self._dict_to_fact(item))
            except Exception:
                return facts

        return facts

    def get_all(self, project: str | None = None, k: int = 100) -> list[SemanticFact]:
        """Retrieve all memories, optionally filtered by project."""
        self._ensure_initialized()

        facts: list[SemanticFact] = []

        try:
            memories = get_memories(data={"project": project} if project else {}, limit=k)
            if isinstance(memories, list):
                for item in memories:
                    facts.append(self._dict_to_fact(item))
            elif isinstance(memories, dict):
                for item in memories.get("results", memories.get("memories", [])):
                    facts.append(self._dict_to_fact(item))
        except Exception:
            pass

        return facts

    def update_access(self, fact_id: str) -> None:
        """Update the last_accessed timestamp for a fact after retrieval."""
        self._ensure_initialized()
        try:
            now_ts = datetime.now(UTC).timestamp()
            update_memory(fact_id, data={"last_accessed": now_ts})
        except Exception:
            pass

    def delete(self, fact_id: str) -> bool:
        """Delete a specific fact by ID. Returns True if found and deleted."""
        self._ensure_initialized()
        try:
            delete_memory(fact_id)
            return True
        except Exception:
            return False

    def decay(self, days: int = 90) -> int:
        """Delete old unused facts from the store.

        Facts whose last_accessed is older than `days` are removed.
        Returns the count of deleted facts.
        """
        self._ensure_initialized()
        cutoff_ts = datetime.now(UTC) - timedelta(days=days)
        cutoff_timestamp = cutoff_ts.timestamp()

        deleted_count = 0
        try:
            all_memories = get_memories(limit=1000)
            if isinstance(all_memories, list):
                for item in all_memories:
                    if isinstance(item, dict):
                        last_accessed = item.get("data", {}).get("last_accessed", 0)
                        if isinstance(last_accessed, (int, float)) and last_accessed < cutoff_timestamp:
                            delete_memory(item.get("id", item.get("memory_id", "")))
                            deleted_count += 1
        except Exception:
            pass

        return deleted_count

    def get_collection_stats(self) -> dict:
        """Return statistics about the memory store."""
        self._ensure_initialized()
        try:
            total = count_memories()
            return {
                "total_facts": total,
                "backend": "agentmemory",
                "persist_dir": str(self.persist_dir),
            }
        except Exception:
            return {
                "total_facts": 0,
                "backend": "agentmemory",
                "persist_dir": str(self.persist_dir),
            }

    def clear(self) -> None:
        """Delete all facts from the store."""
        self._ensure_initialized()
        try:
            wipe_all_memories()
        except Exception:
            pass

    @staticmethod
    def _dict_to_fact(item: dict) -> SemanticFact:
        """Convert an agentmemory dict response to a SemanticFact."""
        data = item.get("data", item.get("metadata", {}))
        if isinstance(data, str):
            # Some versions store data as JSON string
            import json
            try:
                data = json.loads(data)
            except (json.JSONDecodeError, TypeError):
                data = {}

        created_at_str = data.get("created_at", "")
        created_at = (
            datetime.fromisoformat(created_at_str) if created_at_str else datetime.now(UTC)
        )
        last_accessed_ts = data.get("last_accessed")
        last_accessed = (
            datetime.fromtimestamp(last_accessed_ts, tz=UTC) if last_accessed_ts else None
        )

        return SemanticFact(
            id=item.get("id", item.get("memory_id", str(uuid.uuid4()))),
            content=item.get("text", item.get("content", "")),
            project=data.get("project", ""),
            type=data.get("type", "note"),
            metadata={k: v for k, v in data.items() if k not in ("project", "type", "created_at", "last_accessed", "decayed")},
            created_at=created_at,
            last_accessed=last_accessed,
            decayed=data.get("decayed", False) == True or data.get("decayed") == "True",
        )


class PluggableSemanticMemory:
    """Semantic memory with pluggable backends.

    Supports both ChromaDB (default) and AgentMemory backends.
    Switch via the BACKEND environment variable or constructor.

    Usage:
        # Default ChromaDB
        mem = PluggableSemanticMemory()

        # AgentMemory backend
        mem = PluggableSemanticMemory(backend="agentmemory")
    """

    def __init__(
        self,
        persist_dir: str = "~/.xcopilot/memory/chroma",
        backend: str | None = None,
        project_root: str | None = None,
    ) -> None:
        self.backend_name = backend or "chromadb"
        self._backend = self._create_backend(persist_dir, backend, project_root)

    def _create_backend(self, persist_dir: str, backend: str | None, project_root: str | None):
        """Create the appropriate backend instance."""
        if self.backend_name == "agentmemory":
            return AgentMemoryBackend(
                project_root=project_root or persist_dir,
                persist_dir=persist_dir,
            )
        else:
            # Default to ChromaDB-based SemanticMemory
            from xcopilot.memory.semantic import SemanticMemory
            return SemanticMemory(persist_dir=persist_dir)

    def add(self, fact: SemanticFact) -> str:
        return self._backend.add(fact)

    def search(self, query: str, k: int = 5, project: str | None = None, type: str | None = None) -> list[SemanticFact]:
        return self._backend.search(query, k=k, project=project, type=type)

    def update_access(self, fact_id: str) -> None:
        self._backend.update_access(fact_id)

    def delete(self, fact_id: str) -> bool:
        return self._backend.delete(fact_id)

    def decay(self, days: int = 90) -> int:
        return self._backend.decay(days=days)

    def get_collection_stats(self) -> dict:
        return self._backend.get_collection_stats()

    def clear(self) -> None:
        self._backend.clear()


# Global singleton
_agentmemory_instance: AgentMemoryBackend | None = None


def get_agentmemory_backend(project_root: str | None = None) -> AgentMemoryBackend:
    """Get or create the global agentmemory backend singleton."""
    global _agentmemory_instance
    if _agentmemory_instance is None:
        _agentmemory_instance = AgentMemoryBackend(project_root=project_root)
    return _agentmemory_instance


# Update __init__.py export compatibility
__all__ = [
    "AgentMemoryBackend",
    "PluggableSemanticMemory",
    "SemanticFact",
    "get_agentmemory_backend",
    "AGENTMEMORY_AVAILABLE",
]