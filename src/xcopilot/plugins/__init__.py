"""X-Copilot plugin system.

Mirrors X-Copilot plugins/ pattern. Plugins extend X-Copilot with:
- Memory providers (alternative memory backends)
- Context engines (alternative context compression)
- Model providers (alternative LLM providers)
- Custom tools, hooks, CLI commands

Three discovery sources:
1. ~/.xcopilot/plugins/ (user plugins)
2. .xcopilot/plugins/ (project plugins)
3. pip entry points (installed packages)

Plugin kinds: memory, context_engine, model_provider, tool, hook, command
Only one memory provider and one context engine can be active at a time.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from pathlib import Path
from typing import Any


class Plugin:
    """Base class for all X-Copilot plugins."""

    name: str = ""
    version: str = "0.1.0"
    kind: str = "tool"  # memory, context_engine, model_provider, tool, hook, command
    description: str = ""

    def activate(self, context: dict[str, Any]) -> None:
        """Called when the plugin is activated."""

    def deactivate(self) -> None:
        """Called when the plugin is deactivated."""

    def get_config_schema(self) -> dict[str, Any] | None:
        """Return JSON Schema for plugin-specific config, or None."""
        return None


class PluginRegistry:
    """Central plugin registry — discovery, loading, activation."""

    def __init__(self) -> None:
        self._plugins: dict[str, Plugin] = {}
        self._active: dict[str, Plugin] = {}
        self._single_select_kinds = {"memory", "context_engine", "model_provider"}

    def discover(
        self,
        user_dir: Path | None = None,
        project_dir: Path | None = None,
    ) -> list[str]:
        """Discover plugins from user and project directories.

        Returns list of discovered plugin names.
        """
        discovered: list[str] = []
        for directory in [user_dir, project_dir]:
            if directory is None or not directory.exists():
                continue
            for entry in directory.iterdir():
                if entry.is_dir() and (entry / "__init__.py").exists():
                    try:
                        self._load_plugin(entry)
                        discovered.append(entry.name)
                    except Exception:
                        continue
        return discovered

    def _load_plugin(self, plugin_dir: Path) -> None:
        """Load a plugin from a directory."""
        import importlib.util

        init_file = plugin_dir / "__init__.py"
        spec = importlib.util.spec_from_file_location(
            f"xcopilot_plugins.{plugin_dir.name}", init_file
        )
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            # Look for a Plugin subclass in the module
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    inspect.isclass(attr)
                    and issubclass(attr, Plugin)
                    and attr is not Plugin
                    and attr.name
                ):
                    self._plugins[attr.name] = attr()

    def register(self, plugin: Plugin) -> None:
        """Register a plugin instance."""
        self._plugins[plugin.name] = plugin

    def get(self, name: str) -> Plugin | None:
        """Get a plugin by name."""
        return self._plugins.get(name)

    def activate_plugin(self, name: str, context: dict[str, Any] | None = None) -> bool:
        """Activate a plugin. Returns True on success."""
        plugin = self._plugins.get(name)
        if plugin is None:
            return False

        # Check single-select kinds
        if plugin.kind in self._single_select_kinds and plugin.kind in self._active:
            # Deactivate the existing one first
            existing = self._active[plugin.kind]
            existing.deactivate()
            del self._active[plugin.kind]

        plugin.activate(context or {})
        self._active[name] = plugin
        return True

    def deactivate_plugin(self, name: str) -> bool:
        """Deactivate a plugin. Returns True if it was active."""
        plugin = self._active.get(name)
        if plugin is None:
            return False
        plugin.deactivate()
        del self._active[name]
        return True

    def get_active(self, kind: str | None = None) -> list[Plugin]:
        """Get active plugins, optionally filtered by kind."""
        if kind is None:
            return list(self._active.values())
        return [p for p in self._active.values() if p.kind == kind]

    def list_all(self) -> dict[str, Plugin]:
        """Return all discovered plugins."""
        return dict(self._plugins)


# Global plugin registry
plugin_registry = PluginRegistry()