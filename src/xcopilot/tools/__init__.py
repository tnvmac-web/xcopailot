"""Tools package — registry-based auto-discovery.

All tools register with the central registry at import time.
The registry handles schema collection, dispatch, availability checking,
and error wrapping — matching X-Copilot tools/registry.py pattern.

Usage:
    from xcopilot.tools.registry import registry
    specs = registry.list_tools()
    result = registry.dispatch("shell", cmd="ls", pipeline=pipeline)
"""

from __future__ import annotations

from xcopilot.tools.registry import registry, register_tool, ToolSpec
from xcopilot.tools.tool_base import BaseTool, ToolResult, _tool_specs

# Import all tool modules — each registers its factory at import time
from xcopilot.tools import shell, file, search, web, delegation  # noqa: F401

# Register all tools with the central registry
# Each tool module exports a <name>_tool_factory function
register_tool(
    name="shell",
    description="Execute shell commands with timeout and permission checks",
    toolset="terminal",
    schema=shell.ShellTool.schema,
    factory=shell.shell_tool_factory,
)
register_tool(
    name="file",
    description="Read, write, patch, and search files",
    toolset="file",
    schema=file.FileTool.schema,
    factory=file.file_tool_factory,
)
register_tool(
    name="search",
    description="Search files by pattern and perform web search",
    toolset="search",
    schema=search.SearchTool.schema,
    factory=search.search_tool_factory,
)
register_tool(
    name="web",
    description="Extract content from URLs",
    toolset="web",
    schema=web.WebTool.schema,
    factory=web.web_tool_factory,
)
register_tool(
    name="delegate_task",
    description="Delegate a task to an X-Copilot subagent (permission-aware)",
    toolset="delegation",
    schema=delegation.DelegationTool.schema,
    factory=delegation.delegation_tool_factory,
)

__all__ = [
    "registry",
    "register_tool",
    "ToolSpec",
    "BaseTool",
    "ToolResult",
    "shell",
    "file",
    "search",
    "web",
    "delegation",
]