"""Web tool — extract content from URLs with permission checks."""

from __future__ import annotations

from typing import Any

from xcopilot.permission.pipeline import PermissionAction, PermissionPipeline
from xcopilot.tools.tool_base import ToolResult


class WebTool:
    """Web extraction with permission checks."""

    name = "web"
    description = "Extract content from URLs"
    toolset = "web"
    requires_approval = True
    schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to extract"},
            "char_limit": {"type": "integer", "description": "Max characters", "default": 15000},
        },
        "required": ["url"],
    }

    def __init__(self, pipeline: PermissionPipeline) -> None:
        self.pipeline = pipeline

    def execute(self, url: str, char_limit: int = 15000) -> ToolResult:
        """Extract content from a URL."""
        decision = self.pipeline.check(PermissionAction.WEB, {"url": url})
        if not decision.approved:
            return ToolResult(
                success=False,
                error=f"Web access denied: {decision.reason}",
            )

        try:
            # web_extract available via X-Copilot tools if available
            result = web_extract([url], char_limit=char_limit)
            if result.get("results"):
                r = result["results"][0]
                content = r.get("content", "")[:char_limit]
                return ToolResult(
                    success=True,
                    output=content,
                    data={"url": url, "title": r.get("title", "")},
                )
            return ToolResult(success=False, error="No content extracted")
        except Exception as exc:
            return ToolResult(success=False, error=str(exc))


def web_tool_factory(**deps: Any) -> WebTool:
    """Factory to create WebTool with its dependencies."""
    return WebTool(pipeline=deps["pipeline"])