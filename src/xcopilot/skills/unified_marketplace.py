"""Unified Skills Marketplace - integrates multiple skill sources."""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

import httpx


@dataclass
class MarketplaceSkill:
    """A skill from any marketplace."""

    name: str
    source: str  # github, anthropic, scientific, diagram, langchain
    repo: str
    description: str
    triggers: list[str] = field(default_factory=list)
    compatible_agents: list[str] = field(default_factory=list)
    url: str = ""
    metadata: dict = field(default_factory=dict)


class SkillSource:
    """Base class for skill sources."""

    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    async def search(self, query: str) -> list[MarketplaceSkill]:
        """Search for skills matching query."""
        raise NotImplementedError

    async def install(self, skill_name: str, project_root: str) -> str | None:
        """Install a skill to project."""
        raise NotImplementedError

    async def sync(self) -> None:
        """Sync skills from source."""
        raise NotImplementedError


class GitHubSkillsSource(SkillSource):
    """Skills from GitHub repositories (addyosmani/agent-skills, etc.)."""

    REPOS: ClassVar[list[str]] = [
        "addyosmani/agent-skills",
        "anthropics/skills",
        "vercel-labs/agent-skills",
        "voltagent/awesome-agent-skills",
    ]

    def __init__(self, cache_dir: Path):
        super().__init__(cache_dir)
        self._cache_file = cache_dir / "github_skills.json"
        self._skills_cache: list[MarketplaceSkill] = []
        self._github_token = os.environ.get("GITHUB_TOKEN")

    async def _fetch_repo_skills(self, repo: str) -> list[MarketplaceSkill]:
        """Fetch skills from a GitHub repo."""
        skills = []
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                headers = {}
                if self._github_token:
                    headers["Authorization"] = f"Bearer {self._github_token}"

                # Get repo contents
                url = f"https://api.github.com/repos/{repo}/contents/skills"
                response = await client.get(url, headers=headers)
                if response.status_code != 200:
                    # Try alternative structure
                    url = f"https://api.github.com/repos/{repo}/contents/"
                    response = await client.get(url, headers=headers)

                if response.status_code == 200:
                    contents = response.json()
                    for item in contents:
                        if item["type"] == "dir":
                            skill_name = item["name"]
                            # Try to read SKILL.md
                            skill_url = f"https://api.github.com/repos/{repo}/contents/skills/{skill_name}/SKILL.md"
                            skill_resp = await client.get(skill_url, headers=headers)
                            if skill_resp.status_code == 200:
                                import base64

                                content = base64.b64decode(skill_resp.json()["content"]).decode()
                                skill = self._parse_skill_md(content, skill_name, repo)
                                if skill:
                                    skills.append(skill)
                elif response.status_code == 403:
                    print(f"GitHub API rate limited for {repo}. Using cached skills if available.")
        except (httpx.HTTPError, ValueError, KeyError) as e:
            print(f"Error fetching skills from {repo}: {e}")
        return skills

    def _parse_skill_md(self, content: str, skill_name: str, repo: str) -> MarketplaceSkill | None:
        """Parse SKILL.md content."""
        try:
            if not content.startswith("---"):
                return None
            parts = content.split("---", 2)
            if len(parts) < 3:
                return None

            import yaml

            frontmatter = yaml.safe_load(parts[1])
            instructions = parts[2].strip()

            return MarketplaceSkill(
                name=frontmatter.get("name", skill_name),
                source="github",
                repo=repo,
                description=frontmatter.get("description", ""),
                triggers=frontmatter.get("triggers", [skill_name]),
                compatible_agents=frontmatter.get("compatible_agents", ["xcopilot"]),
                url=f"https://github.com/{repo}/tree/main/skills/{skill_name}",
                metadata={"instructions": instructions, "frontmatter": frontmatter},
            )
        except (yaml.YAMLError, ValueError, KeyError):
            return None

    async def search(self, query: str) -> list[MarketplaceSkill]:
        """Search cached skills."""
        if not self._skills_cache:
            await self.sync()

        query_lower = query.lower()
        return [
            s
            for s in self._skills_cache
            if query_lower in s.name.lower() or query_lower in s.description.lower()
        ]

    async def sync(self) -> None:
        """Sync skills from all GitHub repos."""
        all_skills = []
        for repo in self.REPOS:
            skills = await self._fetch_repo_skills(repo)
            all_skills.extend(skills)

        self._skills_cache = all_skills

        # Save cache
        cache_data = [
            {
                "name": s.name,
                "source": s.source,
                "repo": s.repo,
                "description": s.description,
                "triggers": s.triggers,
                "compatible_agents": s.compatible_agents,
                "url": s.url,
                "metadata": s.metadata,
            }
            for s in all_skills
        ]
        self._cache_file.write_text(json.dumps(cache_data, indent=2))

    async def install(self, skill_name: str, project_root: str) -> str | None:
        """Install a skill from GitHub."""
        # Find the skill
        skill = next((s for s in self._skills_cache if s.name == skill_name), None)
        if not skill:
            return None

        # Create skill directory
        skill_dir = Path(project_root) / ".xcopilot" / "skills" / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)

        # Write SKILL.md
        skill_md = "---\n"
        import yaml

        frontmatter = skill.metadata.get("frontmatter", {})
        frontmatter["name"] = skill.name
        skill_md += yaml.dump(frontmatter, default_flow_style=False, sort_keys=False)
        skill_md += "---\n"
        skill_md += skill.metadata.get("instructions", "") + "\n"

        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text(skill_md)

        return str(skill_file)


class AnthropicCybersecuritySkillsSource(SkillSource):
    """Cybersecurity skills from mukul975/anthropic-cybersecurity-skills."""

    REPO = "mukul975/anthropic-cybersecurity-skills"

    def __init__(self, cache_dir: Path):
        super().__init__(cache_dir)
        self._cache_file = cache_dir / "cybersecurity_skills.json"
        self._skills_cache: list[MarketplaceSkill] = []
        self._github_token = os.environ.get("GITHUB_TOKEN")

    async def search(self, query: str) -> list[MarketplaceSkill]:
        if not self._skills_cache:
            await self.sync()

        query_lower = query.lower()
        return [
            s
            for s in self._skills_cache
            if query_lower in s.name.lower() or query_lower in s.description.lower()
        ]

    async def sync(self) -> None:
        """Fetch cybersecurity skills."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                headers = {}
                if self._github_token:
                    headers["Authorization"] = f"Bearer {self._github_token}"

                # Get repo tree
                url = f"https://api.github.com/repos/{self.REPO}/git/trees/main?recursive=1"
                response = await client.get(url, headers=headers)
                if response.status_code == 200:
                    tree = response.json()["tree"]
                    for item in tree:
                        if item["path"].endswith("SKILL.md") or item["path"].endswith(".md"):
                            # Fetch skill content
                            skill_url = (
                                f"https://raw.githubusercontent.com/{self.REPO}/main/{item['path']}"
                            )
                            skill_resp = await client.get(skill_url)
                            if skill_resp.status_code == 200:
                                skill = self._parse_skill(skill_resp.text, item["path"])
                                if skill:
                                    self._skills_cache.append(skill)
                elif response.status_code == 403:
                    print(
                        f"GitHub API rate limited for {self.REPO}. Using cached skills if available."
                    )
        except (httpx.HTTPError, ValueError, KeyError) as e:
            print(f"Error fetching cybersecurity skills: {e}")

        # Save cache
        cache_data = [
            {
                "name": s.name,
                "source": s.source,
                "repo": s.repo,
                "description": s.description,
                "triggers": s.triggers,
                "compatible_agents": s.compatible_agents,
                "url": s.url,
                "metadata": s.metadata,
            }
            for s in self._skills_cache
        ]
        self._cache_file.write_text(json.dumps(cache_data, indent=2))

    def _parse_skill(self, content: str, path: str) -> MarketplaceSkill | None:
        """Parse skill from markdown."""
        try:
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    import yaml

                    frontmatter = yaml.safe_load(parts[1])
                    return MarketplaceSkill(
                        name=frontmatter.get("name", path.split("/")[-2]),
                        source="anthropic_cybersecurity",
                        repo=self.REPO,
                        description=frontmatter.get("description", ""),
                        triggers=frontmatter.get("triggers", []),
                        compatible_agents=frontmatter.get("compatible_agents", ["xcopilot"]),
                        url=f"https://github.com/{self.REPO}/blob/main/{path}",
                        metadata={"instructions": parts[2].strip(), "frontmatter": frontmatter},
                    )
        except (yaml.YAMLError, ValueError, KeyError):
            return None
        return None

    async def install(self, skill_name: str, project_root: str) -> str | None:
        skill = next((s for s in self._skills_cache if s.name == skill_name), None)
        if not skill:
            return None

        skill_dir = Path(project_root) / ".xcopilot" / "skills" / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)

        skill_md = "---\n"
        import yaml

        frontmatter = skill.metadata.get("frontmatter", {})
        frontmatter["name"] = skill.name
        skill_md += yaml.dump(frontmatter, default_flow_style=False, sort_keys=False)
        skill_md += "---\n"
        skill_md += skill.metadata.get("instructions", "") + "\n"

        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text(skill_md)

        return str(skill_file)


class ScientificSkillsSource(SkillSource):
    """Scientific skills from K-Dense-AI/scientific-agent-skills."""

    REPO = "K-Dense-AI/scientific-agent-skills"

    def __init__(self, cache_dir: Path):
        super().__init__(cache_dir)
        self._cache_file = cache_dir / "scientific_skills.json"
        self._skills_cache: list[MarketplaceSkill] = []
        self._github_token = os.environ.get("GITHUB_TOKEN")

    async def search(self, query: str) -> list[MarketplaceSkill]:
        if not self._skills_cache:
            await self.sync()

        query_lower = query.lower()
        return [
            s
            for s in self._skills_cache
            if query_lower in s.name.lower() or query_lower in s.description.lower()
        ]

    async def sync(self) -> None:
        """Fetch scientific skills."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                headers = {}
                if self._github_token:
                    headers["Authorization"] = f"Bearer {self._github_token}"

                url = f"https://api.github.com/repos/{self.REPO}/git/trees/main?recursive=1"
                response = await client.get(url, headers=headers)
                if response.status_code == 200:
                    tree = response.json()["tree"]
                    for item in tree:
                        if item["path"].endswith(".md") and "skills" in item["path"]:
                            skill_url = (
                                f"https://raw.githubusercontent.com/{self.REPO}/main/{item['path']}"
                            )
                            skill_resp = await client.get(skill_url)
                            if skill_resp.status_code == 200:
                                skill = self._parse_skill(skill_resp.text, item["path"])
                                if skill:
                                    self._skills_cache.append(skill)
                elif response.status_code == 403:
                    print(
                        f"GitHub API rate limited for {self.REPO}. Using cached skills if available."
                    )
        except (httpx.HTTPError, ValueError, KeyError) as e:
            print(f"Error fetching scientific skills: {e}")

        cache_data = [
            {
                "name": s.name,
                "source": s.source,
                "repo": s.repo,
                "description": s.description,
                "triggers": s.triggers,
                "compatible_agents": s.compatible_agents,
                "url": s.url,
                "metadata": s.metadata,
            }
            for s in self._skills_cache
        ]
        self._cache_file.write_text(json.dumps(cache_data, indent=2))

    def _parse_skill(self, content: str, path: str) -> MarketplaceSkill | None:
        try:
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    import yaml

                    frontmatter = yaml.safe_load(parts[1])
                    return MarketplaceSkill(
                        name=frontmatter.get("name", path.split("/")[-1].replace(".md", "")),
                        source="scientific",
                        repo=self.REPO,
                        description=frontmatter.get("description", ""),
                        triggers=frontmatter.get("triggers", []),
                        compatible_agents=frontmatter.get("compatible_agents", ["xcopilot"]),
                        url=f"https://github.com/{self.REPO}/blob/main/{path}",
                        metadata={"instructions": parts[2].strip(), "frontmatter": frontmatter},
                    )
        except (yaml.YAMLError, ValueError, KeyError):
            return None
        return None

    async def install(self, skill_name: str, project_root: str) -> str | None:
        skill = next((s for s in self._skills_cache if s.name == skill_name), None)
        if not skill:
            return None

        skill_dir = Path(project_root) / ".xcopilot" / "skills" / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)

        skill_md = "---\n"
        import yaml

        frontmatter = skill.metadata.get("frontmatter", {})
        frontmatter["name"] = skill.name
        skill_md += yaml.dump(frontmatter, default_flow_style=False, sort_keys=False)
        skill_md += "---\n"
        skill_md += skill.metadata.get("instructions", "") + "\n"

        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text(skill_md)

        return str(skill_file)


class DiagramDesignSource(SkillSource):
    """Diagram design skills from cathrynlavery/diagram-design."""

    REPO = "cathrynlavery/diagram-design"

    def __init__(self, cache_dir: Path):
        super().__init__(cache_dir)
        self._cache_file = cache_dir / "diagram_skills.json"
        self._skills_cache: list[MarketplaceSkill] = []

    async def search(self, query: str) -> list[MarketplaceSkill]:
        if not self._skills_cache:
            await self.sync()

        query_lower = query.lower()
        return [
            s
            for s in self._skills_cache
            if query_lower in s.name.lower() or query_lower in s.description.lower()
        ]

    async def sync(self) -> None:
        """Fetch diagram design skills (38 diagram types)."""
        diagram_types = [
            "architecture",
            "flowchart",
            "sequence",
            "state",
            "er",
            "timeline",
            "swimlane",
            "quadrant",
            "nested",
            "tree",
            "org-chart",
            "layers",
            "venn",
            "pyramid",
            "radar",
            "polar",
            "loop",
            "funnel",
            "gantt",
            "kanban",
            "mindmap",
            "network",
            "sankey",
            "sunburst",
            "treemap",
            "chord",
            "force-directed",
            "hierarchical",
            "matrix",
            "parallel",
            "radial",
            "spiral",
            "stream",
            "word-cloud",
            "heatmap",
            "scatter",
            "bar-chart",
            "line-chart",
            "pie-chart",
        ]

        for dtype in diagram_types:
            self._skills_cache.append(
                MarketplaceSkill(
                    name=f"diagram-{dtype}",
                    source="diagram_design",
                    repo=self.REPO,
                    description=f"Create {dtype.replace('-', ' ')} diagrams (HTML+SVG)",
                    triggers=[f"diagram {dtype}", f"create {dtype}", dtype],
                    compatible_agents=["xcopilot", "claude-code", "cursor"],
                    url=f"https://github.com/{self.REPO}/blob/main/{dtype}.html",
                    metadata={"diagram_type": dtype, "is_visual": True},
                )
            )

        cache_data = [
            {
                "name": s.name,
                "source": s.source,
                "repo": s.repo,
                "description": s.description,
                "triggers": s.triggers,
                "compatible_agents": s.compatible_agents,
                "url": s.url,
                "metadata": s.metadata,
            }
            for s in self._skills_cache
        ]
        self._cache_file.write_text(json.dumps(cache_data, indent=2))

    async def install(self, skill_name: str, project_root: str) -> str | None:
        skill = next((s for s in self._skills_cache if s.name == skill_name), None)
        if not skill:
            return None

        skill_dir = Path(project_root) / ".xcopilot" / "skills" / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)

        skill_md = f"""---
name: {skill.name}
description: {skill.description}
triggers: {json.dumps(skill.triggers)}
compatible_agents: {json.dumps(skill.compatible_agents)}
tags: [diagram, visualization, {skill.metadata.get("diagram_type", "")}]
---
# {skill.name} Diagram Skill

## Overview
{skill.description}

## Usage
This skill generates {skill.metadata.get("diagram_type", "").replace("-", " ")} diagrams using the Diagram Design library.

## Examples
```bash
# Generate a {skill.metadata.get("diagram_type", "").replace("-", " ")} diagram
xcopilot skill run {skill.name} --data "your data"
```

## Reference
Source: {skill.url}
"""
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text(skill_md)

        return str(skill_file)


class LangChainSkillsSource(SkillSource):
    """LangChain/LangGraph skills from langchain-ai/langchain-skills."""

    REPO = "langchain-ai/langchain-skills"

    def __init__(self, cache_dir: Path):
        super().__init__(cache_dir)
        self._cache_file = cache_dir / "langchain_skills.json"
        self._skills_cache: list[MarketplaceSkill] = []

    async def search(self, query: str) -> list[MarketplaceSkill]:
        if not self._skills_cache:
            await self.sync()

        query_lower = query.lower()
        return [
            s
            for s in self._skills_cache
            if query_lower in s.name.lower() or query_lower in s.description.lower()
        ]

    async def sync(self) -> None:
        """Fetch LangChain skills including deepagents quickstart."""
        # Known LangChain skills
        known_skills = [
            MarketplaceSkill(
                name="deepagents-python-quickstart",
                source="langchain",
                repo=self.REPO,
                description="Deep Agents Python quickstart - research agent with web search, sub-agents, and memory",
                triggers=["deepagents", "research agent", "deep research"],
                compatible_agents=["xcopilot", "langchain", "langgraph"],
                url="https://github.com/langchain-ai/langchain-skills/tree/main/deepagents-python-quickstart",
                metadata={"template": "deepagents_quickstart", "framework": "langgraph"},
            ),
            MarketplaceSkill(
                name="langgraph-python-quickstart",
                source="langchain",
                repo=self.REPO,
                description="LangGraph Python quickstart - math agent with tool calling",
                triggers=["langgraph", "math agent", "tool calling"],
                compatible_agents=["xcopilot", "langchain", "langgraph"],
                url="https://github.com/langchain-ai/langchain-skills/tree/main/langgraph-python-quickstart",
                metadata={"template": "langgraph_quickstart", "framework": "langgraph"},
            ),
            MarketplaceSkill(
                name="langchain-python-quickstart",
                source="langchain",
                repo=self.REPO,
                description="LangChain Python quickstart - weather agent with tool calling",
                triggers=["langchain", "weather agent", "tool calling"],
                compatible_agents=["xcopilot", "langchain"],
                url="https://github.com/langchain-ai/langchain-skills/tree/main/langchain-python-quickstart",
                metadata={"template": "langchain_quickstart", "framework": "langchain"},
            ),
        ]

        self._skills_cache = known_skills

        cache_data = [
            {
                "name": s.name,
                "source": s.source,
                "repo": s.repo,
                "description": s.description,
                "triggers": s.triggers,
                "compatible_agents": s.compatible_agents,
                "url": s.url,
                "metadata": s.metadata,
            }
            for s in known_skills
        ]
        self._cache_file.write_text(json.dumps(cache_data, indent=2))

    async def install(self, skill_name: str, project_root: str) -> str | None:
        skill = next((s for s in self._skills_cache if s.name == skill_name), None)
        if not skill:
            return None

        skill_dir = Path(project_root) / ".xcopilot" / "skills" / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)

        skill_md = "---\n"
        import yaml

        frontmatter = {
            "name": skill.name,
            "description": skill.description,
            "triggers": skill.triggers,
            "compatible_agents": skill.compatible_agents,
            "tags": ["langchain", "langgraph", skill.metadata.get("template", "")],
        }
        skill_md += yaml.dump(frontmatter, default_flow_style=False, sort_keys=False)
        skill_md += "---\n"
        skill_md += f"""# {skill.name}

## Overview
{skill.description}

## Template
This skill uses the `{skill.metadata.get("template", "")}` template from LangChain Skills.

## Setup
```bash
pip install langchain langgraph langchain-openai tavily-python
```

## Quickstart
See: {skill.url}

## Configuration
Set required API keys:
- OPENAI_API_KEY (or ANTHROPIC_API_KEY)
- TAVILY_API_KEY (for web search)
"""
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text(skill_md)

        # Also create a template agent file
        template_dir = skill_dir / "templates"
        template_dir.mkdir(exist_ok=True)

        if skill.metadata.get("template") == "deepagents_quickstart":
            agent_code = '''"""Deep Agents Quickstart - Research Agent."""
from deepagents import create_deep_agent
from langchain_core.tools import tool


@tool
def get_weather(city: str) -> str:
    """Get weather for a given city."""
    # Replace with real API call
    return f"It's always sunny in {city}!"


agent = create_deep_agent(
    model="openai:gpt-4o-mini",
    tools=[get_weather],
    system_prompt="You are a helpful research assistant.",
)

# Run the agent
result = agent.invoke({
    "messages": [{"role": "user", "content": "what is the weather in sf"}]
})
print(result)
'''
            (template_dir / "research_agent.py").write_text(agent_code)

        return str(skill_file)


class OpenVikingSkillsSource(SkillSource):
    """Skills from OpenViking (volcengine/OpenViking)."""

    REPO = "volcengine/OpenViking"

    def __init__(self, cache_dir: Path):
        super().__init__(cache_dir)
        self._cache_file = cache_dir / "openviking_skills.json"
        self._skills_cache: list[MarketplaceSkill] = []

    async def search(self, query: str) -> list[MarketplaceSkill]:
        if not self._skills_cache:
            await self.sync()

        query_lower = query.lower()
        return [
            s
            for s in self._skills_cache
            if query_lower in s.name.lower() or query_lower in s.description.lower()
        ]

    async def sync(self) -> None:
        """Fetch OpenViking skills/connectors."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                url = f"https://api.github.com/repos/{self.REPO}/git/trees/main?recursive=1"
                response = await client.get(url)
                if response.status_code == 200:
                    tree = response.json()["tree"]
                    for item in tree:
                        if (
                            "connector" in item["path"].lower() or "skill" in item["path"].lower()
                        ) and item["path"].endswith((".yaml", ".yml", ".json")):
                            skill_url = (
                                f"https://raw.githubusercontent.com/{self.REPO}/main/{item['path']}"
                            )
                            skill_resp = await client.get(skill_url)
                            if skill_resp.status_code == 200:
                                skill = self._parse_openviking(skill_resp.text, item["path"])
                                if skill:
                                    self._skills_cache.append(skill)
        except (httpx.HTTPError, ValueError, KeyError) as e:
            print(f"Error fetching OpenViking skills: {e}")

        cache_data = [
            {
                "name": s.name,
                "source": s.source,
                "repo": s.repo,
                "description": s.description,
                "triggers": s.triggers,
                "compatible_agents": s.compatible_agents,
                "url": s.url,
                "metadata": s.metadata,
            }
            for s in self._skills_cache
        ]
        self._cache_file.write_text(json.dumps(cache_data, indent=2))

    def _parse_openviking(self, content: str, path: str) -> MarketplaceSkill | None:
        try:
            import yaml

            data = yaml.safe_load(content)
            if isinstance(data, dict) and "name" in data:
                return MarketplaceSkill(
                    name=data["name"],
                    source="openviking",
                    repo=self.REPO,
                    description=data.get("description", ""),
                    triggers=data.get("triggers", [data["name"]]),
                    compatible_agents=["xcopilot", "openviking"],
                    url=f"https://github.com/{self.REPO}/blob/main/{path}",
                    metadata={"connector_config": data},
                )
        except (yaml.YAMLError, ValueError, KeyError):
            return None
        return None

    async def install(self, skill_name: str, project_root: str) -> str | None:
        skill = next((s for s in self._skills_cache if s.name == skill_name), None)
        if not skill:
            return None

        skill_dir = Path(project_root) / ".xcopilot" / "skills" / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)

        skill_md = "---\n"
        import yaml

        frontmatter = {
            "name": skill.name,
            "description": skill.description,
            "triggers": skill.triggers,
            "compatible_agents": skill.compatible_agents,
            "tags": ["openviking", "connector"],
        }
        skill_md += yaml.dump(frontmatter, default_flow_style=False, sort_keys=False)
        skill_md += "---\n"
        skill_md += f"""# {skill.name} OpenViking Connector

## Overview
{skill.description}

## Configuration
```yaml
{json.dumps(skill.metadata.get("connector_config", {}), indent=2)}
```

## Reference
Source: {skill.url}
"""
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text(skill_md)

        return str(skill_file)


class AgentMemorySource(SkillSource):
    """AgentMemory integration (rohitg00/agentmemory)."""

    REPO = "rohitg00/agentmemory"

    def __init__(self, cache_dir: Path):
        super().__init__(cache_dir)
        self._cache_file = cache_dir / "agentmemory_skills.json"
        self._skills_cache: list[MarketplaceSkill] = []

    async def search(self, query: str) -> list[MarketplaceSkill]:
        if not self._skills_cache:
            await self.sync()

        query_lower = query.lower()
        return [
            s
            for s in self._skills_cache
            if query_lower in s.name.lower() or query_lower in s.description.lower()
        ]

    async def sync(self) -> None:
        """AgentMemory provides memory backend, not skills per se."""
        self._skills_cache = [
            MarketplaceSkill(
                name="agentmemory-backend",
                source="agentmemory",
                repo=self.REPO,
                description="Persistent memory backend for AI agents with benchmarked performance",
                triggers=["memory", "persistent memory", "agentmemory"],
                compatible_agents=["xcopilot"],
                url="https://github.com/rohitg00/agentmemory",
                metadata={"type": "memory_backend"},
            ),
        ]

        cache_data = [
            {
                "name": s.name,
                "source": s.source,
                "repo": s.repo,
                "description": s.description,
                "triggers": s.triggers,
                "compatible_agents": s.compatible_agents,
                "url": s.url,
                "metadata": s.metadata,
            }
            for s in self._skills_cache
        ]
        self._cache_file.write_text(json.dumps(cache_data, indent=2))

    async def install(self, skill_name: str, project_root: str) -> str | None:
        # AgentMemory is a backend, not a skill - install as dependency
        return None


class UnifiedMarketplace:
    """Unified marketplace combining all skill sources."""

    def __init__(self, cache_dir: str | None = None):
        cache_path = Path(cache_dir or "~/.xcopilot/marketplace").expanduser()
        cache_path.mkdir(parents=True, exist_ok=True)

        self.sources = {
            "github": GitHubSkillsSource(cache_path / "github"),
            "anthropic": AnthropicCybersecuritySkillsSource(cache_path / "anthropic"),
            "scientific": ScientificSkillsSource(cache_path / "scientific"),
            "diagram": DiagramDesignSource(cache_path / "diagram"),
            "langchain": LangChainSkillsSource(cache_path / "langchain"),
            "openviking": OpenVikingSkillsSource(cache_path / "openviking"),
            "agentmemory": AgentMemorySource(cache_path / "agentmemory"),
        }

    async def search(self, query: str, source: str | None = None) -> list[MarketplaceSkill]:
        """Search across all or specific source."""
        if source:
            if source in self.sources:
                return await self.sources[source].search(query)
            return []

        # Search all sources in parallel
        tasks = [src.search(query) for src in self.sources.values()]
        results = await asyncio.gather(*tasks)
        all_skills = []
        for skill_list in results:
            all_skills.extend(skill_list)
        return all_skills

    async def install(
        self, skill_name: str, project_root: str, source: str | None = None
    ) -> str | None:
        """Install a skill from marketplace."""
        if source:
            if source in self.sources:
                return await self.sources[source].install(skill_name, project_root)
            return None

        # Try all sources
        for src in self.sources.values():
            result = await src.install(skill_name, project_root)
            if result:
                return result
        return None

    async def sync_all(self) -> None:
        """Sync all sources."""
        tasks = [src.sync() for src in self.sources.values()]
        await asyncio.gather(*tasks)

    def list_sources(self) -> list[str]:
        """List available sources."""
        return list(self.sources.keys())


# Global instance
unified_marketplace = UnifiedMarketplace()
