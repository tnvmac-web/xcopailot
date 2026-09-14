"""Tool registry — auto-discovery, schema collection, dispatch, availability.

Mirrors X-Copilot tools/registry.py pattern. Every tool file self-registers
at import time via registry.register(). No manual import list needed.
"""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolSpec:
    """Metadata for a registered tool."""

    name: str
    description: str
    toolset: str
    schema: dict[str, Any]
    factory: Callable[..., Any]  # factory function that creates the tool instance
    service_gated: bool = False
    check_fn: Callable[[], bool] | None = None
    requires_approval: bool = True


class ToolRegistry:
    """Central tool registry — auto-discovery via pkgutil.iter_modules."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}
        self._toolsets: dict[str, list[str]] = {}

    def register(self, spec: ToolSpec) -> None:
        """Register a tool. Called at import time by tool files."""
        self._tools[spec.name] = spec
        if spec.toolset not in self._toolsets:
            self._toolsets[spec.toolset] = []
        if spec.name not in self._toolsets[spec.toolset]:
            self._toolsets[spec.toolset].append(spec.name)

    def discover(self, package: str = "xcopilot.tools") -> int:
        """Auto-discover tools in a package by importing all submodules.

        Returns the number of tools registered.
        """
        count = 0
        try:
            package_obj = importlib.import_module(package)
            for _, name, is_pkg in pkgutil.iter_modules(package_obj.__path__):
                if name.startswith("_"):
                    continue
                module_name = f"{package}.{name}"
                try:
                    module = importlib.import_module(module_name)
                    if hasattr(module, "_tool_specs"):
                        for spec in module._tool_specs:
                            self.register(spec)
                            count += 1
                except Exception:
                    continue
        except ImportError:
            pass
        return count

    def get(self, name: str) -> ToolSpec | None:
        """Get a tool spec by name."""
        return self._tools.get(name)

    def list_tools(self, toolset: str | None = None) -> list[ToolSpec]:
        """List all tools, optionally filtered by toolset."""
        if toolset is None:
            return list(self._tools.values())
        names = self._toolsets.get(toolset, [])
        return [self._tools[n] for n in names if n in self._tools]

    def list_toolsets(self) -> dict[str, list[str]]:
        """Return all toolsets and their tool names."""
        return dict(self._toolsets)

    def dispatch(self, name: str, **kwargs: Any) -> Any:
        """Call a tool by name with the given arguments.
        
        Creates the tool instance via its factory function and calls execute().
        """
        spec = self._tools.get(name)
        if spec is None:
            raise KeyError(f"Tool {name!r} not registered")
        if spec.service_gated and spec.check_fn and not spec.check_fn():
            raise RuntimeError(f"Service gated: {name} — dependency not available")
        tool = spec.factory(**kwargs)
        return tool.execute(**kwargs)

    def schemas(self) -> dict[str, dict[str, Any]]:
        """Return all tool schemas keyed by tool name."""
        return {name: spec.schema for name, spec in self._tools.items()}

    def __len__(self) -> int:
        return len(self._tools)


# Global registry instance — imported by all tool files at module level
registry = ToolRegistry()


def register_tool(
    name: str,
    description: str,
    toolset: str,
    schema: dict[str, Any],
    factory: Callable[..., Any],
    service_gated: bool = False,
    check_fn: Callable[[], bool] | None = None,
    requires_approval: bool = True,
) -> None:
    """Convenience function for tool files to register at import time."""
    spec = ToolSpec(
        name=name,
        description=description,
        toolset=toolset,
        schema=schema,
        factory=factory,
        service_gated=service_gated,
        check_fn=check_fn,
        requires_approval=requires_approval,
    )
    registry.register(spec)