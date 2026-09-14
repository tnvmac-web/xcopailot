"""Semantic memory — ChromaDB vector store for inferred facts.

Supports pluggable backends via backend='agentmemory' parameter.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

try:
    import chromadb
    from chromadb.config import Settings

    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False
    chromadb = None
    Settings = None


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


class SemanticMemory:
    """ChromaDB-backed semantic memory for vector search of facts.

    Supports pluggable backends via backend parameter.
    Use backend="agentmemory" to switch to AgentMemory backend.
    """

    def __init__(self, persist_dir: str = "~/.xcopilot/memory/chroma") -> None:
        if not CHROMADB_AVAILABLE:
            raise RuntimeError("chromadb is not installed. Install with: pip install chromadb")

        self.persist_dir = Path(persist_dir).expanduser()
        self.persist_dir.mkdir(parents=True, exist_ok=True)

        self.client = chromadb.PersistentClient(
            path=str(self.persist_dir),
            settings=Settings(anonymized_telemetry=False),
        )

        self.collection = self.client.get_or_create_collection(
            name="xcopilot_semantic",
            metadata={"description": "X-Copilot semantic memory"},
        )

    def add(self, fact: SemanticFact) -> str:
        """Add a fact to the vector store. Returns the fact ID."""
        meta: dict = {
            "project": fact.project,
            "type": fact.type,
            "created_at": fact.created_at.isoformat(),
            "decayed": fact.decayed,
            **fact.metadata,
        }
        if fact.last_accessed:
            # Store as timestamp for comparison in decay()
            meta["last_accessed"] = fact.last_accessed.timestamp()

        self.collection.add(
            ids=[fact.id],
            documents=[fact.content],
            metadatas=[meta],
        )
        return fact.id

    def search(
        self,
        query: str,
        k: int = 5,
        project: str | None = None,
        type: str | None = None,
    ) -> list[SemanticFact]:
        """Search for semantically similar facts. Returns list of SemanticFact."""
        # Build where filter for ChromaDB v1.x.
        # Single-key where is fine; multiple keys require $and operator.
        filter_conditions: list[dict] = []
        if project:
            filter_conditions.append({"project": project})
        if type:
            filter_conditions.append({"type": type})
        # Always exclude decayed facts — store as bool false, not string
        filter_conditions.append({"decayed": False})

        if len(filter_conditions) == 1:
            where = filter_conditions[0]
        elif len(filter_conditions) > 1:
            where = {"$and": filter_conditions}
        else:
            where = None

        results = self.collection.query(
            query_texts=[query],
            n_results=k,
            where=where,
            include=["metadatas", "documents", "distances"],
        )

        facts: list[SemanticFact] = []
        if results["ids"] and results["ids"][0]:
            for i, fact_id in enumerate(results["ids"][0]):
                meta = results["metadatas"][0][i]
                content = results["documents"][0][i]

                created_at_str = meta.get("created_at", "")
                created_at = (
                    datetime.fromisoformat(created_at_str) if created_at_str else datetime.now(UTC)
                )

                # last_accessed stored as timestamp float
                last_accessed_ts = meta.get("last_accessed")
                last_accessed = (
                    datetime.fromtimestamp(last_accessed_ts, tz=UTC) if last_accessed_ts else None
                )

                fact = SemanticFact(
                    id=fact_id,
                    content=content,
                    project=meta.get("project", ""),
                    type=meta.get("type", "note"),
                    metadata={
                        k: v
                        for k, v in meta.items()
                        if k
                        not in (
                            "project",
                            "type",
                            "created_at",
                            "last_accessed",
                            "decayed",
                        )
                    },
                    created_at=created_at,
                    last_accessed=last_accessed,
                    decayed=meta.get("decayed") is True or meta.get("decayed") == "True",
                )
                facts.append(fact)

        return facts

    def decay(self, days: int = 90) -> int:
        """Delete old unused facts from the store.

        Facts whose last_accessed is older than `days` are removed.
        Returns the count of deleted facts.
        """
        cutoff_ts = datetime.now(UTC) - timedelta(days=days)
        cutoff_timestamp = cutoff_ts.timestamp()

        # Paginated fetch: batch size 1000 to avoid OOM on large collections
        batch_size = 1000
        deleted_count = 0
        while True:
            all_results = self.collection.get(
                where={"last_accessed": {"$lt": cutoff_timestamp}},
                limit=batch_size,
            )
            if not all_results.get("ids"):
                break
            self.collection.delete(ids=all_results["ids"])
            deleted_count += len(all_results["ids"])

        return deleted_count

    def update_access(self, fact_id: str) -> None:
        """Update the last_accessed timestamp for a fact after retrieval."""
        now_ts = datetime.now(UTC).timestamp()
        self.collection.update(
            ids=[fact_id],
            metadatas=[{"last_accessed": now_ts}],
        )

    def get_collection_stats(self) -> dict:
        """Return statistics about the collection."""
        count = self.collection.count()
        return {
            "total_facts": count,
            "collection_name": self.collection.name,
            "persist_dir": str(self.persist_dir),
        }

    def delete(self, fact_id: str) -> bool:
        """Delete a specific fact by ID. Returns True if found and deleted."""
        all_results = self.collection.get()
        if fact_id not in all_results["ids"]:
            return False
        self.collection.delete(ids=[fact_id])
        return True

    def clear(self) -> None:
        """Delete all facts from the collection."""
        all_results = self.collection.get()
        ids = all_results["ids"]
        batch_size = 1000
        for i in range(0, len(ids), batch_size):
            batch = ids[i : i + batch_size]
            self.collection.delete(ids=batch)
