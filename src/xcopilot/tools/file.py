"""File tool — read, write, patch, search files with permission checks."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from xcopilot.permission.pipeline import PermissionAction, PermissionPipeline
from xcopilot.tools.tool_base import ToolResult


class FileTool:
    """File operations with permission checks."""

    name = "file"
    description = "Read, write, patch, and search files"
    toolset = "file"
    requires_approval = True
    schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["read", "write", "patch", "search"],
                "description": "File operation to perform",
            },
            "path": {"type": "string", "description": "File path"},
            "content": {"type": "string", "description": "Content for write/patch"},
            "pattern": {"type": "string", "description": "Search pattern (regex)"},
            "target": {"type": "string", "description": "Replacement text for patch"},
            "replace_all": {"type": "boolean", "description": "Replace all occurrences"},
        },
        "required": ["action"],
    }

    def __init__(self, pipeline: PermissionPipeline) -> None:
        self.pipeline = pipeline

    def execute(
        self, action: str, path: str = "", content: str = "",
        pattern: str = "", target: str = "", replace_all: bool = False,
    ) -> ToolResult:
        """Execute a file operation."""
        from xcopilot.tools.tool_base import ToolResult

        action_map = {
            "read": self._read,
            "write": self._write,
            "patch": self._patch,
            "search": self._search,
        }
        handler = action_map.get(action)
        if handler is None:
            return ToolResult(success=False, error=f"Unknown action: {action}")

        decision = self.pipeline.check(
            PermissionAction.EDIT_FILE if action in ("write", "patch") else PermissionAction.READ_FILE,
            {"path": path, "action": action},
        )
        if not decision.approved:
            return ToolResult(
                success=False,
                error=f"File {action} denied: {decision.reason}",
            )

        try:
            return handler(path, content, pattern, target, replace_all)
        except Exception as exc:
            return ToolResult(success=False, error=str(exc))

    def _read(self, path: str, _c: str, _p: str, _t: str, _r: bool) -> ToolResult:
        p = Path(path)
        if not p.exists():
            return ToolResult(success=False, error=f"File not found: {path}")
        text = p.read_text(encoding="utf-8")
        return ToolResult(success=True, output=text)

    def _write(self, path: str, content: str, _p: str, _t: str, _r: bool) -> ToolResult:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return ToolResult(success=True, output=f"Written {len(content)} bytes to {path}")

    def _patch(self, path: str, content: str, target: str, replace_all: bool, _p: str, _t: str, _r: bool) -> ToolResult:
        p = Path(path)
        old = p.read_text(encoding="utf-8")
        new = old.replace(content, target) if replace_all else old.replace(content, target, 1)
        p.write_text(new, encoding="utf-8")
        return ToolResult(success=True, output=f"Patched {path}")

    def _search(self, _path: str, _content: str, pattern: str, _t: str, _r: bool) -> ToolResult:
        import os
        matches = []
        for root, _, files in os.walk("."):
            for f in files:
                if f.endswith(('.py', '.md', '.txt', '.json', '.yaml', '.toml')):
                    fp = os.path.join(root, f)
                    try:
                        text = Path(fp).read_text(encoding="utf-8", errors="ignore")
                        if re.search(pattern, text):
                            matches.append(fp)
                    except Exception:
                        pass
        return ToolResult(success=True, output="\n".join(matches[:50]), data={"count": len(matches)})


def file_tool_factory(**deps: Any) -> FileTool:
    """Factory to create FileTool with its dependencies."""
    return FileTool(pipeline=deps["pipeline"])