"""Permission pipeline — 5-tier permission system with DENY → ASK → ALLOW chain."""

from __future__ import annotations

import re
from enum import Enum


class PermissionMode(Enum):
    """Permission modes controlling agent behavior."""

    STANDARD = "standard"  # Prompt before edits/commands
    AUTO_ASK = "auto_ask"  # Always prompts
    PLAN = "plan"  # Read-only, no side effects
    BYPASS = "bypass"  # Skip all prompts
    DONT_ASK = "dont_ask"  # Auto-allow (denies in bypass)


class PermissionResult(Enum):
    """Result of a permission check."""

    DENY = "deny"
    ASK = "ask"
    ALLOW = "allow"


class PermissionAction(Enum):
    """Actions that require permission checks."""

    READ_FILE = "read_file"
    WRITE_FILE = "write_file"
    EDIT_FILE = "edit_file"
    DELETE_FILE = "delete_file"
    SHELL_COMMAND = "shell_command"
    NETWORK_REQUEST = "network_request"
    PACKAGE_INSTALL = "package_install"
    GIT_PUSH = "git_push"
    DELEGATE = "delegate"


# Patterns that are always DENIED (destructive operations)
DESTRUCTIVE_PATTERNS = [
    r"rm\s+-rf\s+/",
    r"format\s+[cC]:",
    r"del\s+/[sqf]",
    r"shutdown\s+/s",
    r"mkfs\.",
    r"dd\s+if=.*of=/dev/",
    r">\s*/dev/sd[a-z]",
]

# Production paths where deletion is denied
PRODUCTION_PATHS = [
    r"/var/www/",
    r"/etc/",
    r"/usr/",
    r"/opt/",
    r"C:\\Windows\\",
    r"C:\\Program Files\\",
    r"C:\\inetpub\\",
]

# Known safe network domains
SAFE_DOMAINS = [
    "api.github.com",
    "api.openai.com",
    "api.anthropic.com",
    "api.nvidia.com",
    "localhost",
    "127.0.0.1",
    "raw.githubusercontent.com",
    "github.com",
]


class PermissionPipeline:
    """Permission check pipeline: DENY → ASK → ALLOW."""

    def __init__(self, mode: PermissionMode = PermissionMode.STANDARD) -> None:
        self.mode = mode

    def set_mode(self, mode: PermissionMode) -> None:
        """Change permission mode."""
        self.mode = mode

    def check(self, action: PermissionAction, context: dict) -> PermissionResult:
        """
        Check permission for an action.
        Returns DENY, ASK, or ALLOW based on mode and action.
        """
        # BYPASS mode allows everything, even destructive
        if self.mode == PermissionMode.BYPASS:
            return PermissionResult.ALLOW

        # Step 1: Check for always-DENY patterns (destructive ops)
        if self._is_destructive(action, context):
            return PermissionResult.DENY

        # Step 2: Mode-based decision
        return self._mode_decision(action, context)

    def _is_destructive(self, action: PermissionAction, context: dict) -> bool:
        """Check if action is a destructive operation that should always be denied."""
        # Shell commands with destructive patterns
        if action == PermissionAction.SHELL_COMMAND:
            cmd = context.get("cmd", "").lower()
            for pattern in DESTRUCTIVE_PATTERNS:
                if re.search(pattern, cmd, re.IGNORECASE):
                    return True

        # File deletion in production paths
        if action == PermissionAction.DELETE_FILE:
            path = context.get("path", "")
            for prod_path in PRODUCTION_PATHS:
                if path.startswith(prod_path):
                    return True

        return False

    def _mode_decision(self, action: PermissionAction, context: dict) -> PermissionResult:
        """Make decision based on current mode."""
        # PLAN mode: read-only
        if self.mode == PermissionMode.PLAN:
            if action in (PermissionAction.READ_FILE, PermissionAction.NETWORK_REQUEST):
                return PermissionResult.ALLOW
            return PermissionResult.DENY

        # BYPASS mode: allow everything
        if self.mode == PermissionMode.BYPASS:
            return PermissionResult.ALLOW

        # DONT_ASK mode: allow non-destructive, deny destructive (already checked above)
        if self.mode == PermissionMode.DONT_ASK:
            if action in (
                PermissionAction.READ_FILE,
                PermissionAction.WRITE_FILE,
                PermissionAction.EDIT_FILE,
                PermissionAction.SHELL_COMMAND,
            ):
                return PermissionResult.ALLOW
            return PermissionResult.DENY

        # AUTO_ASK mode: always ask
        if self.mode == PermissionMode.AUTO_ASK:
            return PermissionResult.ASK

        # STANDARD mode: allow reads, ask for writes/commands/delegation
        if self.mode == PermissionMode.STANDARD:
            if action == PermissionAction.READ_FILE:
                return PermissionResult.ALLOW
            if action in (PermissionAction.WRITE_FILE, PermissionAction.EDIT_FILE):
                return PermissionResult.ASK
            if action == PermissionAction.SHELL_COMMAND:
                # Safe commands allowed, others ask
                cmd = context.get("cmd", "").lower()
                safe_commands = [
                    "ls",
                    "dir",
                    "pwd",
                    "cd",
                    "cat",
                    "type",
                    "head",
                    "tail",
                    "grep",
                    "find",
                ]
                if any(cmd.startswith(safe + " ") or cmd == safe for safe in safe_commands):
                    return PermissionResult.ALLOW
                return PermissionResult.ASK
            if action == PermissionAction.NETWORK_REQUEST:
                url = context.get("url", "")
                if any(domain in url for domain in SAFE_DOMAINS):
                    return PermissionResult.ALLOW
                return PermissionResult.ASK
            if action in (
                PermissionAction.DELETE_FILE,
                PermissionAction.PACKAGE_INSTALL,
                PermissionAction.GIT_PUSH,
                PermissionAction.DELEGATE,
            ):
                return PermissionResult.ASK

        # AUTO_ASK mode: always ask for delegation
        if self.mode == PermissionMode.AUTO_ASK:
            if action == PermissionAction.DELEGATE:
                return PermissionResult.ASK

        return PermissionResult.ASK
