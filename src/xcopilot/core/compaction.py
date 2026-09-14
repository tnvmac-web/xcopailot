"""Context compaction — token budget management and conversation compression."""

from __future__ import annotations

from dataclasses import dataclass

import tiktoken


@dataclass
class BudgetInfo:
    """Token budget breakdown."""

    total: int
    used: int
    memory: int
    skills: int
    conversation: int


class CompactionManager:
    """Manages context window budget and compaction."""

    def __init__(self, max_tokens: int = 8192) -> None:
        self.max_tokens = max_tokens
        self.conversation_history: list[str] = []
        self._encoding: tiktoken.Encoding | None = None
        self._encoding_name = "cl100k_base"

    def _get_encoding(self):
        """Lazily load tiktoken encoding; returns None if tiktoken unavailable."""
        if self._encoding is None:
            try:
                import tiktoken

                self._encoding = tiktoken.get_encoding(self._encoding_name)
            except ImportError:
                self._encoding = None
        return self._encoding

    def _count_tokens(self, text: str) -> int:
        """Count tokens in text. Returns 0 if tiktoken unavailable."""
        encoding = self._get_encoding()
        if encoding is None:
            # Fallback: ~1 token per 4 chars
            return len(text) // 4 + 1
        return len(encoding.encode(text))

    def get_budget(self) -> BudgetInfo:
        """Return current token budget breakdown."""
        conv_tokens = sum(self._count_tokens(t) for t in self.conversation_history)
        memory_tokens = 0  # Would sum memory files
        skills_tokens = 0  # Would sum skill files
        used = conv_tokens + memory_tokens + skills_tokens

        return BudgetInfo(
            total=self.max_tokens,
            used=used,
            memory=memory_tokens,
            skills=skills_tokens,
            conversation=conv_tokens,
        )

    def compact_if_needed(self, limit: int | None = None) -> bool:
        """Auto-compact if conversation exceeds threshold."""
        limit = limit or self.max_tokens
        budget = self.get_budget()
        if budget.used > limit * 0.8:  # 80% threshold
            self.compact(mode="default")
            return True
        return False

    def compact(self, mode: str = "default") -> str:
        """
        Compress conversation history.
        mode="default": summarize with key points
        mode="fast": truncate middle, keep start/end
        """
        if not self.conversation_history:
            return ""

        if mode == "fast":
            # Keep first 3 and last 3, summarize middle
            if len(self.conversation_history) <= 6:
                return "\n".join(self.conversation_history)
            kept = (
                self.conversation_history[:3]
                + ["... [compacted] ..."]
                + self.conversation_history[-3:]
            )
            self.conversation_history = kept
            return "\n".join(kept)
        else:
            # Default: summarize
            summary = f"[Compacted {len(self.conversation_history)} turns]"
            self.conversation_history = [summary] + self.conversation_history[-3:]
            return "\n".join(self.conversation_history)

    def memory_cost(self) -> dict:
        """Return token cost per memory file."""
        # In real implementation, would scan memory files
        return {
            "session": 0,
            "episodic": 0,
            "semantic": 0,
            "procedural": 0,
            "project": 0,
        }

    def add_to_history(self, text: str) -> None:
        """Add a turn to conversation history."""
        self.conversation_history.append(text)
