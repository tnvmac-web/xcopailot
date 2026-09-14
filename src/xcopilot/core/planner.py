"""Taste/Plan profile — learns and applies user working style preferences."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from xcopilot.memory import MemoryEngine


@dataclass
class TasteProfile:
    """User's learned working style preferences."""

    preferred_tools: list[str] = field(default_factory=list)
    code_style: dict = field(default_factory=dict)
    conventions: dict = field(default_factory=dict)
    anti_patterns: list[str] = field(default_factory=list)


class PlannerEngine:
    """Manages user taste profile and applies it to task planning."""

    def __init__(self, memory: MemoryEngine) -> None:
        self.memory = memory
        self.profile = TasteProfile()
        self._config_path = memory.project_root / ".xcopilot" / "config.json"
        self._global_config_path = Path.home() / ".xcopilot" / "config.json"

    def learn_from_edit(self, before: str, after: str, context: dict) -> None:
        """Infer preferences from a code edit (before -> after)."""
        # Detect type hints addition
        if self._added_type_hints(before, after):
            self.profile.code_style["type_hints"] = True

        # Detect money-as-cents pattern
        if self._detect_money_as_cents(before, after):
            self.profile.conventions["money_as_cents"] = True

        # Detect indentation changes
        indent = self._detect_indent_change(before, after)
        if indent:
            self.profile.code_style["indent"] = indent

        # Detect tool usage from context
        if "tool" in context:
            tool = context["tool"]
            if tool not in self.profile.preferred_tools:
                self.profile.preferred_tools.append(tool)

    def _added_type_hints(self, before: str, after: str) -> bool:
        """Check if type hints were added.

        Matches only PEP 484-style annotations: name: Type or def name(...): Type
        """
        # Match: identifier : whitespace *type* — must be preceded by a valid name start
        hint_pattern = r"\b\w+\s*:\s*(?:int|str|bool|float|list|dict|set|tuple|None|Callable|Iterable|AsyncIterator|Path|dict\[|list\[|\|)"
        before_hints = len(re.findall(hint_pattern, before))
        after_hints = len(re.findall(hint_pattern, after))
        return after_hints > before_hints

    def _detect_money_as_cents(self, before: str, after: str) -> bool:
        """Check if float money was converted to cents.

        Matches patterns like: variable = float_var * 100, variable_cents = int(...)
        """
        # Before: has a float assignment (price * 100, cost * 1.0, etc.)
        before_has_float = bool(
            re.search(r"\w+\s*=\s*\d+\.\d+", before)  # price = 19.99
            or re.search(r"\w+\s*=\s*\w+\s*\*\s*100", before)  # price = cost * 100
            or re.search(r"\w+\s*=\s*\d+\.\d+\s*(\*|/)\s*\d+", before)  # price = 19.99 * 100
        )
        # After: has a _cents = int(...) or _cents = ... * 100 pattern
        after_has_cents = bool(
            re.search(r"\w+_cents\s*=\s*int\(", after)
            or re.search(r"\w+_cents\s*=\s*\w+\s*\*\s*100", after)
            or re.search(r"\w+_cents\s*=\s*\d+", after)
        )
        return before_has_float and after_has_cents

    def _detect_indent_change(self, before: str, after: str) -> int | None:
        """Detect indentation style from code."""
        for line in after.split("\n"):
            match = re.match(r"^(\s+)", line)
            if match:
                indent = len(match.group(1))
                if indent in (2, 4, 8):
                    return indent
        return None

    def apply_profile(self, task_context: dict) -> dict:
        """Return configuration based on learned preferences for a task."""
        return {
            "preferred_tools": self.profile.preferred_tools.copy(),
            "code_style": self.profile.code_style.copy(),
            "conventions": self.profile.conventions.copy(),
            "anti_patterns": self.profile.anti_patterns.copy(),
        }

    def save(self) -> None:
        """Save profile to project and global config files."""
        # Save project-specific config
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        project_config = {
            "preferred_tools": self.profile.preferred_tools,
            "code_style": self.profile.code_style,
            "conventions": self.profile.conventions,
            "anti_patterns": self.profile.anti_patterns,
        }
        self._config_path.write_text(json.dumps(project_config, indent=2))

        # Also update global config (merge)
        global_config = {}
        if self._global_config_path.exists():
            try:
                global_config = json.loads(self._global_config_path.read_text())
            except json.JSONDecodeError:
                pass

        # Merge: project overrides global
        for key in ("preferred_tools", "code_style", "conventions", "anti_patterns"):
            if key in project_config:
                if key in ("preferred_tools", "anti_patterns"):
                    # Merge lists uniquely
                    merged = list(dict.fromkeys(global_config.get(key, []) + project_config[key]))
                    global_config[key] = merged
                else:
                    global_config[key] = {**global_config.get(key, {}), **project_config[key]}

        self._global_config_path.parent.mkdir(parents=True, exist_ok=True)
        self._global_config_path.write_text(json.dumps(global_config, indent=2))

    def load(self) -> None:
        """Load profile from project and global config files."""
        # Load global first
        if self._global_config_path.exists():
            try:
                global_config = json.loads(self._global_config_path.read_text())
                self._apply_config(global_config)
            except json.JSONDecodeError:
                pass

        # Load project (overrides global)
        if self._config_path.exists():
            try:
                project_config = json.loads(self._config_path.read_text())
                self._apply_config(project_config)
            except json.JSONDecodeError:
                pass

    def _apply_config(self, config: dict) -> None:
        """Apply config dict to profile."""
        if "preferred_tools" in config:
            # Merge uniquely
            existing = set(self.profile.preferred_tools)
            for tool in config["preferred_tools"]:
                if tool not in existing:
                    self.profile.preferred_tools.append(tool)
                    existing.add(tool)
        if "code_style" in config:
            self.profile.code_style.update(config["code_style"])
        if "conventions" in config:
            self.profile.conventions.update(config["conventions"])
        if "anti_patterns" in config:
            # Merge uniquely
            existing = set(self.profile.anti_patterns)
            for pattern in config["anti_patterns"]:
                if pattern not in existing:
                    self.profile.anti_patterns.append(pattern)
                    existing.add(pattern)
