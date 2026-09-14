"""Search tool — grep files and web search with permission checks."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from xcopilot.permission.pipeline import PermissionAction, PermissionPipeline
from xcopilot.tools.tool_base import ToolResult


class SearchTool:
    """Search files and the web with permission checks."""

    name = "search"
    description = "Search files by pattern and perform web search"
    toolset = "search"
    requires_approval = True
    schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search pattern (regex)"},
            "path": {"type": "string", "description": "Directory to search (default: current)"},
            "web": {"type": "boolean", "description": "Also search the web"},
            "limit": {"type": "integer", "description": "Max results", "default": 50},
        },
        "required": ["query"],
    }

    def __init__(self, pipeline: PermissionPipeline) -> None:
        self.pipeline = pipeline

    def execute(self, query: str, path: str = ".", web: bool = False, limit: int = 50) -> ToolResult:
        """Search files and optionally the web."""
        results: list[str] = []

        # File search
        search_path = Path(path)
        if search_path.exists():
            for root, _, files in os.walk(str(search_path)):
                for f in files:
                    fp = os.path.join(root, f)
                    try:
                        text = Path(fp).read_text(encoding="utf-8", errors="ignore")
                        if re.search(query, text):
                            results.append(fp)
                    except Exception:
                        pass
        else:
            return ToolResult(success=False, error=f"Path not found: {path}")

        # Web search if requested
        if web:
            decision = self.pipeline.check(PermissionAction.WEB, {"query": query})
            if not decision.approved:
                return ToolResult(
                    success=False,
                    error=f"Web search denied: {decision.reason}",
                )
            try:
                # web_search available via X-Copilot tools if available
                web_results = web_search(query, limit=limit)
                return ToolResult(
                    success=True,
                    output=f"Files: {len(results)}\nWeb: {len(web_results.get('data', {}).get('web', []))}",
                    data={"files": results[:limit], "web": web_results},
                )
            except Exception as exc:
                return ToolResult(success=False, error=str(exc), data={"files": results[:limit]})

        return ToolResult(
            success=True,
            output=f"Found {len(results)} files matching '{query}'",
            data={"files": results[:limit]},
        )


def search_tool_factory(**deps: Any) -> SearchTool:
    """Factory to create SearchTool with its dependencies."""
    return SearchTool(pipeline=deps["pipeline"])