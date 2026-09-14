"""Project memory — AGENTS.md parser for architecture rules."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer


@dataclass
class ProjectRule:
    """A parsed rule from AGENTS.md."""

    title: str
    content: str
    level: int  # heading level (1-6)
    source_file: str
    line_start: int
    line_end: int


class _AGENTSFileHandler(FileSystemEventHandler):
    """Watchdog handler for AGENTS.md changes."""

    def __init__(self, memory: ProjectMemory) -> None:
        self.memory = memory

    def on_modified(self, event) -> None:
        if event.src_path.endswith("AGENTS.md"):
            self.memory.reload()


class ProjectMemory:
    """Parses and watches AGENTS.md for project architecture rules."""

    def __init__(self, project_root: str) -> None:
        self.project_root = Path(project_root)
        self.sections: dict[str, ProjectRule] = {}
        self._watcher: Observer | None = None
        self._handler: _AGENTSFileHandler | None = None

    def _find_agents_files(self) -> list[Path]:
        """Find all AGENTS.md files in project root and .xcopilot/."""
        files = []
        root_agents = self.project_root / "AGENTS.md"
        if root_agents.exists():
            files.append(root_agents)

        xcopilot_agents = self.project_root / ".xcopilot" / "AGENTS.md"
        if xcopilot_agents.exists():
            files.append(xcopilot_agents)

        return files

    def _parse_agents_file(self, file_path: Path) -> list[ProjectRule]:
        """Parse a single AGENTS.md file into ProjectRule objects."""
        content = file_path.read_text(encoding="utf-8")
        lines = content.split("\n")

        rules = []
        current_title = ""
        current_content = []
        current_level = 0
        start_line = 0

        for i, line in enumerate(lines):
            # Check for heading
            heading_match = re.match(r"^(#{1,6})\s+(.+)$", line)
            if heading_match:
                # Save previous rule if exists
                if current_title:
                    rules.append(
                        ProjectRule(
                            title=current_title,
                            content="\n".join(current_content).strip(),
                            level=current_level,
                            source_file=str(file_path),
                            line_start=start_line,
                            line_end=i - 1,
                        )
                    )

                # Start new rule
                current_level = len(heading_match.group(1))
                current_title = heading_match.group(2).strip()
                current_content = []
                start_line = i + 1
            else:
                current_content.append(line)

        # Save last rule
        if current_title:
            rules.append(
                ProjectRule(
                    title=current_title,
                    content="\n".join(current_content).strip(),
                    level=current_level,
                    source_file=str(file_path),
                    line_start=start_line,
                    line_end=len(lines) - 1,
                )
            )

        return rules

    def load(self) -> None:
        """Load and parse all AGENTS.md files."""
        self.sections.clear()

        for agents_file in self._find_agents_files():
            rules = self._parse_agents_file(agents_file)
            for rule in rules:
                self.sections[rule.title] = rule

    def get_rule(self, title: str) -> ProjectRule | None:
        """Get a rule by section title."""
        return self.sections.get(title)

    def reload(self) -> None:
        """Reload all AGENTS.md files."""
        self.load()

    def watch_changes(self) -> Observer:
        """Start watching AGENTS.md files for changes. Returns the observer."""
        if self._watcher is not None:
            self._watcher.stop()

        self._handler = _AGENTSFileHandler(self)
        self._watcher = Observer()

        for agents_file in self._find_agents_files():
            self._watcher.schedule(self._handler, str(agents_file.parent), recursive=False)

        self._watcher.start()
        return self._watcher

    def stop_watching(self) -> None:
        """Stop the file watcher."""
        if self._watcher is not None:
            self._watcher.stop()
            self._watcher.join(timeout=1.0)
            self._watcher = None
            self._handler = None
