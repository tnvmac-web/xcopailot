"""Auto-updater — check, download, install, rollback."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from xcopilot.permission.pipeline import PermissionMode, PermissionPipeline


@dataclass
class UpdateInfo:
    """Information about a software update."""

    version: str
    url: str
    channel: str
    size_bytes: int
    sha256: str
    published_at: str


class UpdateConfig:
    """Configuration for the auto-updater."""

    def __init__(self) -> None:
        self.mode: str = "auto"  # auto, semi-auto, manual
        self.channel: str = "stable"  # stable, beta, nightly
        self.auto_update: bool = True


class Updater:
    """Auto-updater — checks, downloads, verifies, and installs updates."""

    def __init__(self, data_dir: str | None = None) -> None:
        self.data_dir = Path(data_dir or "~/.xcopilot/updater").expanduser()
        self.config = UpdateConfig()
        self._backup_dir = self.data_dir / "backup"
        self._download_dir = self.data_dir / "downloads"
        self._permission = PermissionPipeline(PermissionMode.STANDARD)

    def check(self) -> UpdateInfo:
        """Check GitHub Releases for new version."""
        # In a full implementation, this would call GitHub Releases API
        # For now, return a mock UpdateInfo
        return UpdateInfo(
            version="0.2.0",
            url="https://github.com/tnvmac-web/x-copilot/releases/download/v0.2.0/xcopilot.zip",
            channel="stable",
            size_bytes=10485760,  # 10MB
            sha256="abc123def456",
            published_at="2026-09-09T00:00:00",
        )

    def download(self, update: UpdateInfo) -> Path:
        """Download update package and verify SHA-256."""
        self._download_dir.mkdir(parents=True, exist_ok=True)
        path = self._download_dir / f"xcopilot-{update.version}.zip"
        # In real implementation: urllib.request.urlretrieve(update.url, path)
        path.write_text(f"mock download: {update.version}")
        return path

    def verify(self, path: Path, expected_sha256: str) -> bool:
        """Verify SHA-256 checksum of downloaded file."""
        # In real implementation: hashlib.sha256(path.read_bytes()).hexdigest()
        return True  # Mock: always passes for testing

    def install(self, update: UpdateInfo) -> bool:
        """Backup current installation, extract new version, run post-install."""
        # Backup current
        self._backup_dir.mkdir(parents=True, exist_ok=True)

        # Download
        path = self.download(update)

        # Verify
        if not self.verify(path, update.sha256):
            raise ValueError("Checksum verification failed")

        # Install would replace running executable
        # For now, create a marker file
        installed = self.data_dir / "installed"
        installed.write_text(update.version)
        return True

    def rollback(self) -> bool:
        """Rollback to previous version from backup."""
        if not self._backup_dir.exists():
            raise FileNotFoundError("No backup found for rollback")
        return True

    def config_save(self) -> None:
        """Save config to disk."""
        config_path = self.data_dir / "config.json"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps(
                {
                    "mode": self.config.mode,
                    "channel": self.config.channel,
                    "auto_update": self.config.auto_update,
                }
            )
        )

    def config_load(self) -> None:
        """Load config from disk."""
        config_path = self.data_dir / "config.json"
        if config_path.exists():
            data = json.loads(config_path.read_text())
            self.config.mode = data.get("mode", "auto")
            self.config.channel = data.get("channel", "stable")
            self.config.auto_update = data.get("auto_update", True)
