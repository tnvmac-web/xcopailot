"""Toolsets — group tools by capability for platform presets.

Mirrors X-Copilot toolsets.py pattern. Each toolset is a named group of tools
that can be enabled/disabled together per platform or per permission mode.
"""

from __future__ import annotations

# Toolset definitions: name → list of tool names
# These are used by permission pipeline and platform presets.

TOOLSETS: dict[str, list[str]] = {
    "core": ["shell", "file", "search", "web"],
    "development": ["shell", "file", "search", "web", "delegate_task"],
    "research": ["web", "search", "file"],
    "automation": ["shell", "file", "web"],
    "delegation": ["delegate_task"],
    "all": ["shell", "file", "search", "web", "delegate_task"],
}

# Core tools that are always available regardless of toolset
_CORE_TOOLSETS = {"shell", "file", "search", "web", "delegate_task"}

# Platform presets — which toolsets are enabled by default per platform
PLATFORM_PRESETS: dict[str, list[str]] = {
    "cli": ["core"],
    "desktop": ["core", "development"],
    "webapp": ["core", "research"],
    "gateway": ["core", "automation"],
    "acp": ["development"],
    "batch": ["core", "development"],
}


def get_toolset_tools(toolset: str) -> list[str]:
    """Get all tool names in a toolset (recursively expands nested toolsets)."""
    result: list[str] = []
    seen: set[str] = set()
    _expand_toolset(toolset, result, seen)
    return result


def _expand_toolset(toolset: str, result: list[str], seen: set[str]) -> None:
    """Recursively expand a toolset, avoiding cycles."""
    if toolset in seen:
        return
    seen.add(toolset)
    tools = TOOLSETS.get(toolset, [])
    for item in tools:
        if item in TOOLSETS:
            _expand_toolset(item, result, seen)
        elif item not in result:
            result.append(item)


def get_platform_tools(platform: str) -> list[str]:
    """Get all tool names enabled for a platform."""
    presets = PLATFORM_PRESETS.get(platform, ["core"])
    tools: list[str] = []
    for preset in presets:
        tools.extend(get_toolset_tools(preset))
    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for t in tools:
        if t not in seen:
            seen.add(t)
            unique.append(t)
    return unique