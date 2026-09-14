"""Skills marketplace — GitHub skills ecosystem integration."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar


@dataclass
class MarketplaceSkill:
    """A skill from the marketplace."""

    repo: str
    name: str
    description: str
    triggers: list[str]
    compatible_agents: list[str]
    url: str


class SkillsMarketplace:
    """Client for the agent-skills marketplace (GitHub-based)."""

    # Known skill repositories
    REPOS: ClassVar[list[str]] = [
        "anthropics/skills",
        "addyosmani/agent-skills",
        "vercel-labs/agent-skills",
        "voltagent/awesome-agent-skills",
    ]

    def __init__(self, cache_dir: str | None = None) -> None:
        self.cache_dir = Path(cache_dir or "~/.xcopilot/marketplace").expanduser()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache_file = self.cache_dir / "skills_cache.json"
        self._github_token = os.environ.get("GITHUB_TOKEN")

    def search(self, query: str) -> list[MarketplaceSkill]:
        """Search marketplace for skills matching query."""
        # In a full implementation, this would query GitHub API
        # For now, return mock results
        return self._mock_search(query)

    def _mock_search(self, query: str) -> list[MarketplaceSkill]:
        """Mock search results."""
        mock_skills = [
            MarketplaceSkill(
                repo="addyosmani/agent-skills",
                name="code-review",
                description="Review code for bugs, security, best practices",
                triggers=["review", "code-review", "PR review"],
                compatible_agents=["xcopilot", "claude-code", "codex", "cursor"],
                url="https://github.com/addyosmani/agent-skills/tree/main/skills/code-review",
            ),
            MarketplaceSkill(
                repo="anthropics/skills",
                name="debug",
                description="Debugging workflow for errors and issues",
                triggers=["bug", "error", "fix"],
                compatible_agents=["xcopilot", "claude-code"],
                url="https://github.com/anthropics/skills/tree/main/skills/debug",
            ),
            MarketplaceSkill(
                repo="vercel-labs/agent-skills",
                name="deploy",
                description="Build and deploy applications",
                triggers=["deploy", "ship", "release"],
                compatible_agents=["xcopilot", "cursor", "windsurf"],
                url="https://github.com/vercel-labs/agent-skills/tree/main/skills/deploy",
            ),
        ]
        return [
            s
            for s in mock_skills
            if query.lower() in s.name.lower() or query.lower() in s.description.lower()
        ]

    def install(self, repo: str, skill_name: str, project_root: str) -> str | None:
        """Install a skill from marketplace to project."""
        # In real implementation: fetch from GitHub, write SKILL.md
        project_path = Path(project_root)
        skills_dir = project_path / ".xcopilot" / "skills" / skill_name
        skills_dir.mkdir(parents=True, exist_ok=True)

        # Create a basic SKILL.md
        skill_content = f"""---
name: {skill_name}
description: Installed from {repo}
triggers: [{skill_name}]
compatible_agents: [xcopilot]
---
# {skill_name} Skill

Installed from marketplace: {repo}

Refer to: https://github.com/{repo}/tree/main/skills/{skill_name}
"""
        skill_file = skills_dir / "SKILL.md"
        skill_file.write_text(skill_content)

        return str(skill_file)

    def list_marketplace(self) -> list[MarketplaceSkill]:
        """List all available skills from all repos."""
        all_skills = []
        for repo in self.REPOS:
            all_skills.extend(self._mock_search(repo.split("/")[-1]))
        return all_skills

    def export(self) -> str:
        """Export installed skills to JSON."""
        return json.dumps([])

    def import_skills(self, json_data: str) -> None:
        """Import skills from JSON."""

    def clear_cache(self) -> None:
        """Clear local cache."""
        if self._cache_file.exists():
            self._cache_file.unlink()
