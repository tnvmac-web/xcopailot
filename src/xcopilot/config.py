"""X-Copilot configuration system.

Profile-aware configuration following X-Copilot patterns:
- Config: ~/.xcopilot/config.yaml (settings, never secrets)
- Secrets: ~/.xcopilot/.env (API keys only)
- State: ~/.xcopilot/state.db (SQLite session store)
- Auth: ~/.xcopilot/auth.json (OAuth tokens, credential pools)
- Skills: ~/.xcopilot/skills/ (installed skills)
- Plugins: ~/.xcopilot/plugins/ (installed plugins)
- Logs: ~/.xcopilot/logs/ (agent.log, errors.log, gateway.log)

All paths are profile-aware via get_profile_home().
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml

DEFAULT_PROFILE = "default"

# Default configuration values
DEFAULT_CONFIG: dict[str, Any] = {
    "profile": DEFAULT_PROFILE,
    "project_root": ".",
    "permission_mode": "standard",
    "model": "gpt-4o-mini",
    "provider": "openai",
    "server": {
        "host": "127.0.0.1",
        "port": 8001,
        "auth_secret": "xcopilot-local-dev-secret",
    },
    "memory": {
        "episodic_db": "episodic.db",
        "semantic_store": "chroma",
        "max_sessions": 1000,
    },
    "tools": {
        "shell_timeout": 30,
        "web_char_limit": 15000,
        "max_delegation_tasks": 50,
    },
    "delegation": {
        "default_role": "leaf",
        "default_model": None,
        "allowed_toolsets": ["shell", "file"],
    },
    "logging": {
        "level": "INFO",
        "dir": "logs",
    },
    "ui": {
        "theme": "dark",
        "font_size": 14,
        "show_tool_preview": True,
    },
}


def get_profile_home(profile: str = DEFAULT_PROFILE) -> Path:
    """Get the profile-aware home directory for X-Copilot."""
    base = Path(os.environ.get("XCOPILOT_HOME", Path.home() / ".xcopilot"))
    if profile and profile != DEFAULT_PROFILE:
        return base / "profiles" / profile
    return base


def get_config_path(profile: str = DEFAULT_PROFILE) -> Path:
    """Get the config file path for a profile."""
    return get_profile_home(profile) / "config.yaml"


def get_state_db_path(profile: str = DEFAULT_PROFILE) -> Path:
    """Get the SQLite state database path."""
    return get_profile_home(profile) / "state.db"


def get_secrets_path(profile: str = DEFAULT_PROFILE) -> Path:
    """Get the secrets (.env) file path."""
    return get_profile_home(profile) / ".env"


def get_auth_path(profile: str = DEFAULT_PROFILE) -> Path:
    """Get the auth tokens file path."""
    return get_profile_home(profile) / "auth.json"


def get_skills_dir(profile: str = DEFAULT_PROFILE) -> Path:
    """Get the skills directory."""
    return get_profile_home(profile) / "skills"


def get_plugins_dir(profile: str = DEFAULT_PROFILE) -> Path:
    """Get the plugins directory."""
    return get_profile_home(profile) / "plugins"


def get_logs_dir(profile: str = DEFAULT_PROFILE) -> Path:
    """Get the logs directory."""
    return get_profile_home(profile) / "logs"


def load_config(profile: str = DEFAULT_PROFILE) -> dict[str, Any]:
    """Load configuration from YAML, merging with defaults."""
    config_path = get_config_path(profile)
    config = dict(DEFAULT_CONFIG)

    if config_path.exists():
        with open(config_path, encoding="utf-8") as f:
            file_config = yaml.safe_load(f)
        if file_config:
            _deep_merge(config, file_config)

    return config


def save_config(config: dict[str, Any], profile: str = DEFAULT_PROFILE) -> None:
    """Save configuration to YAML file."""
    config_path = get_config_path(profile)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)


def get_setting(key: str, default: Any = None, profile: str = DEFAULT_PROFILE) -> Any:
    """Get a nested config setting by dot-separated key (e.g., 'server.port')."""
    config = load_config(profile)
    parts = key.split(".")
    value = config
    for part in parts:
        if isinstance(value, dict) and part in value:
            value = value[part]
        else:
            return default
    return value


def set_setting(key: str, value: Any, profile: str = DEFAULT_PROFILE) -> None:
    """Set a nested config setting by dot-separated key."""
    config = load_config(profile)
    parts = key.split(".")
    target = config
    for part in parts[:-1]:
        if part not in target or not isinstance(target[part], dict):
            target[part] = {}
        target = target[part]
    target[parts[-1]] = value
    save_config(config, profile)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> None:
    """Deep merge override into base (mutates base)."""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value