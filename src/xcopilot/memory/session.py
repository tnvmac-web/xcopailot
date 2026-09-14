"""Session memory — in-memory dict for current conversation context."""

from __future__ import annotations


class SessionMemory:
    """In-memory session store."""

    def __init__(self) -> None:
        self._data: dict[str, object] = {}

    def get(self, key: str) -> object:
        return self._data.get(key)

    def set(self, key: str, value: object) -> None:
        self._data[key] = value

    def clear(self) -> None:
        self._data.clear()
