"""Procedural memory — SKILL.md loader and manager."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class SkillData(BaseModel):
    """Parsed SKILL.md content with YAML frontmatter."""

    name: str
    description: str
    triggers: list[str] = Field(default_factory=list)
    compatible_agents: list[str] = Field(default_factory=list)
    instructions: str = ""
    path: str = ""


class ProceduralMemory:
    """Loads, discovers, and creates SKILL.md files from project and global directories."""

    def __init__(self, project_root: str | None = None) -> None:
        self.project_root = Path(project_root) if project_root else Path.cwd()
        self.global_skills_dir = Path.home() / ".xcopilot" / "skills"
        # Built-in skills directory (from package)
        self.builtin_skills_dir = Path(__file__).parent.parent / "skills"

    def _parse_skill_file(self, skill_path: Path) -> SkillData:
        """Parse a single SKILL.md file with YAML frontmatter."""
        content = skill_path.read_text(encoding="utf-8")

        if not content.startswith("---"):
            raise ValueError(f"Missing YAML frontmatter in {skill_path}")

        parts = content.split("---", 2)
        if len(parts) < 3:
            raise ValueError(f"Invalid frontmatter format in {skill_path}")

        frontmatter_str = parts[1].strip()
        instructions = parts[2].strip()

        try:
            frontmatter = yaml.safe_load(frontmatter_str)
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in {skill_path}: {e}") from e

        if not isinstance(frontmatter, dict):
            raise TypeError(f"Frontmatter must be a dict in {skill_path}")

        return SkillData(
            name=frontmatter.get("name", skill_path.parent.name),
            description=frontmatter.get("description", ""),
            triggers=frontmatter.get("triggers", []),
            compatible_agents=frontmatter.get("compatible_agents", []),
            instructions=instructions,
            path=str(skill_path),
        )

    def load_skill(self, skill_path: str) -> SkillData:
        """Load and parse a SKILL.md file from the given path."""
        path = Path(skill_path)
        if not path.exists():
            raise FileNotFoundError(f"SKILL.md not found: {skill_path}")
        return self._parse_skill_file(path)

    def _discover_skills(self, skills_dir: Path) -> list[SkillData]:
        """Discover all SKILL.md files under a skills directory."""
        skills = []
        if not skills_dir.exists():
            return skills

        for skill_dir in skills_dir.iterdir():
            if not skill_dir.is_dir():
                continue
            skill_file = skill_dir / "SKILL.md"
            if skill_file.exists():
                try:
                    skill = self._parse_skill_file(skill_file)
                    skills.append(skill)
                except (ValueError, yaml.YAMLError):
                    continue
        return skills

    def list_skills(self) -> list[SkillData]:
        """List all skills from project, global, and built-in directories."""
        skills = []
        project_skills_dir = self.project_root / ".xcopilot" / "skills"
        skills.extend(self._discover_skills(project_skills_dir))
        skills.extend(self._discover_skills(self.global_skills_dir))
        skills.extend(self._discover_skills(self.builtin_skills_dir))
        return skills

    def create_skill(
        self,
        name: str,
        description: str,
        instructions: str,
        triggers: list[str] | None = None,
        compatible_agents: list[str] | None = None,
    ) -> str:
        """Create a new SKILL.md file in the project skills directory."""
        triggers = triggers or []
        compatible_agents = compatible_agents or ["xcopilot"]

        skill_dir = self.project_root / ".xcopilot" / "skills" / name
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_path = skill_dir / "SKILL.md"

        frontmatter = {
            "name": name,
            "description": description,
            "triggers": triggers,
            "compatible_agents": compatible_agents,
        }

        content = "---\n"
        content += yaml.dump(frontmatter, default_flow_style=False, sort_keys=False)
        content += "---\n"
        content += instructions + "\n"

        skill_path.write_text(content, encoding="utf-8")
        return str(skill_path)
