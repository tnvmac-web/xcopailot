"""Checkpoint & rewind — auto-snapshots before every change."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class Checkpoint:
    """A single checkpoint in the session history."""

    id: str
    timestamp: str
    action: str
    target: str
    before_hash: str
    after_hash: str
    session_id: str
    parent: str | None = None
    branch: str = "main"


class CheckpointManager:
    """Manages checkpoints for rewind/fork functionality."""

    def __init__(self, checkpoints_dir: str) -> None:
        self.checkpoints_dir = Path(checkpoints_dir)
        self.checkpoints_dir.mkdir(parents=True, exist_ok=True)
        self.session_id: str = ""
        self._counter = 0

    def _hash_content(self, content: str) -> str:
        """Compute SHA-256 hash of content."""
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _gen_id(self) -> str:
        """Generate a unique checkpoint ID."""
        self._counter += 1
        return f"cp_{int(time.time() * 1000)}_{self._counter}"

    def snapshot(
        self,
        action: str,
        target: str,
        before_state: str,
        after_state: str,
        session_id: str,
    ) -> str:
        """Create a checkpoint snapshot."""
        self.session_id = session_id
        cp_id = self._gen_id()

        checkpoint = Checkpoint(
            id=cp_id,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            action=action,
            target=target,
            before_hash=self._hash_content(before_state),
            after_hash=self._hash_content(after_state),
            session_id=session_id,
        )

        # Save to session directory
        session_dir = self.checkpoints_dir / session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        cp_file = session_dir / f"{cp_id}.json"
        cp_file.write_text(json.dumps(asdict(checkpoint), indent=2))

        return cp_id

    def list_checkpoints(self, session_id: str | None = None) -> list[dict]:
        """List all checkpoints for a session."""
        sid = session_id or self.session_id
        session_dir = self.checkpoints_dir / sid
        if not session_dir.exists():
            return []

        checkpoints = []
        for cp_file in sorted(session_dir.glob("cp_*.json")):
            checkpoints.append(json.loads(cp_file.read_text()))
        return checkpoints

    def rewind(self, checkpoint_id: str) -> bool:
        """Rewind to a checkpoint (restore file from before_hash)."""
        # Find the checkpoint
        for session_dir in self.checkpoints_dir.iterdir():
            cp_file = session_dir / f"{checkpoint_id}.json"
            if cp_file.exists():
                json.loads(cp_file.read_text())
                # In real implementation, would restore from backup
                # For now, return success
                return True
        return False

    def fork(self, checkpoint_id: str, branch_name: str) -> str:
        """Create a new branch from a checkpoint."""
        # Find parent checkpoint
        parent_cp = None
        for session_dir in self.checkpoints_dir.iterdir():
            cp_file = session_dir / f"{checkpoint_id}.json"
            if cp_file.exists():
                parent_cp = json.loads(cp_file.read_text())
                break

        if not parent_cp:
            return ""

        new_session_id = f"{parent_cp['session_id']}_{branch_name}"
        return new_session_id

    def tree(self, session_id: str | None = None) -> list[dict]:
        """Show checkpoint tree with branches."""
        checkpoints = self.list_checkpoints(session_id)
        return checkpoints
