"""Learner engine — observes signals, distills patterns, stores to memory."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum

from xcopilot.memory import MemoryEngine


class SignalType(Enum):
    """Types of observable signals."""

    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    USER_EDIT = "user_edit"
    USER_ACCEPT = "user_accept"
    USER_REJECT = "user_reject"
    ERROR = "error"
    CORRECTION = "correction"


class PatternType(Enum):
    """Types of distilled patterns."""

    PREFERENCE = "preference"
    MISTAKE = "mistake"
    PATTERN = "pattern"
    WORKFLOW = "workflow"


@dataclass
class Signal:
    """An observed interaction signal."""

    type: SignalType
    payload: dict
    context: dict
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class Pattern:
    """A distilled pattern from signals."""

    id: str
    type: PatternType
    description: str
    evidence: list[Signal]
    confidence: float  # 0.0 - 1.0
    created_at: datetime
    last_reinforced: datetime
    applications: int = 0


class LearnerEngine:
    """Observes signals, distills patterns, stores to memory layers."""

    def __init__(self, memory: MemoryEngine) -> None:
        self.memory = memory
        self._signal_buffer: list[Signal] = []
        self._patterns: dict[str, Pattern] = {}
        self._pattern_counter = 0

    def observe(self, signal: Signal) -> None:
        """Capture a signal and buffer it for distillation."""
        self._signal_buffer.append(signal)

        # Also store in episodic memory for persistence
        from xcopilot.memory.episodic import EpisodicEvent

        self.memory.episodic.append(
            EpisodicEvent(
                type=signal.type.value,
                payload=signal.payload,
                project=signal.context.get("project", ""),
                session_id=signal.context.get("session_id", ""),
                timestamp=signal.timestamp,
            )
        )

    def distill(self) -> list[Pattern]:
        """Distill buffered signals into patterns."""
        if not self._signal_buffer:
            return []

        patterns = []

        # Group signals by type and context
        by_type: dict[SignalType, list[Signal]] = {}
        for signal in self._signal_buffer:
            by_type.setdefault(signal.type, []).append(signal)

        # Detect preferences from USER_ACCEPT
        if SignalType.USER_ACCEPT in by_type:
            prefs = self._extract_preferences(by_type[SignalType.USER_ACCEPT])
            patterns.extend(prefs)

        # Detect mistakes from ERROR
        if SignalType.ERROR in by_type:
            mistakes = self._extract_mistakes(by_type[SignalType.ERROR])
            patterns.extend(mistakes)

        # Detect workflows from TOOL_CALL sequences
        if SignalType.TOOL_CALL in by_type:
            workflows = self._extract_workflows(by_type[SignalType.TOOL_CALL])
            patterns.extend(workflows)

        # Store new patterns
        for pattern in patterns:
            self._patterns[pattern.id] = pattern

        # Clear buffer after distillation
        self._signal_buffer.clear()

        return patterns

    def _extract_preferences(self, signals: list[Signal]) -> list[Pattern]:
        """Extract user preferences from accept signals."""
        patterns = []
        suggestions = Counter()

        for signal in signals:
            suggestion = signal.payload.get("suggestion", "")
            context = signal.payload.get("context", "")
            if suggestion:
                suggestions[f"{context}: {suggestion}"] += 1

        for desc, count in suggestions.items():
            if count >= 3:  # Threshold for pattern
                self._pattern_counter += 1
                pattern = Pattern(
                    id=f"pat_{self._pattern_counter}",
                    type=PatternType.PREFERENCE,
                    description=f"User prefers: {desc}",
                    evidence=signals[:3],  # Keep first 3 as evidence
                    confidence=min(0.5 + (count * 0.1), 0.95),
                    created_at=datetime.now(UTC),
                    last_reinforced=datetime.now(UTC),
                )
                patterns.append(pattern)

        return patterns

    def _extract_mistakes(self, signals: list[Signal]) -> list[Pattern]:
        """Extract repeated mistakes from error signals."""
        patterns = []
        errors = Counter()

        for signal in signals:
            error_msg = signal.payload.get("error", "")
            context = signal.payload.get("context", "")
            if error_msg:
                errors[f"{context}: {error_msg}"] += 1

        for desc, count in errors.items():
            if count >= 3:
                self._pattern_counter += 1
                pattern = Pattern(
                    id=f"pat_{self._pattern_counter}",
                    type=PatternType.MISTAKE,
                    description=f"Repeated error: {desc}",
                    evidence=signals[:3],
                    confidence=min(0.5 + (count * 0.1), 0.95),
                    created_at=datetime.now(UTC),
                    last_reinforced=datetime.now(UTC),
                )
                patterns.append(pattern)

        return patterns

    def _extract_workflows(self, signals: list[Signal]) -> list[Pattern]:
        """Extract workflow patterns from tool call sequences."""
        patterns = []
        tools = [s.payload.get("tool", "") for s in signals if s.payload.get("tool")]

        if len(tools) >= 3:
            # Look for repeated 3-tool sequences
            sequences = []
            for i in range(len(tools) - 2):
                seq = tuple(tools[i : i + 3])
                sequences.append(seq)

            seq_counts = Counter(sequences)
            for seq, count in seq_counts.items():
                if count >= 2:  # Repeated at least twice
                    self._pattern_counter += 1
                    pattern = Pattern(
                        id=f"pat_{self._pattern_counter}",
                        type=PatternType.WORKFLOW,
                        description=f"Repeated workflow: {' -> '.join(seq)}",
                        evidence=signals[:3],
                        confidence=min(0.5 + (count * 0.15), 0.9),
                        created_at=datetime.now(UTC),
                        last_reinforced=datetime.now(UTC),
                    )
                    patterns.append(pattern)

        return patterns

    def store(self, pattern: Pattern) -> None:
        """Store a pattern to the appropriate memory layer."""
        project_str = str(self.memory.project_root)

        if pattern.type == PatternType.PREFERENCE:
            # Store as semantic fact
            from xcopilot.memory.semantic import SemanticFact

            fact = SemanticFact(
                content=pattern.description,
                project=project_str,
                type="preference",
                metadata={"pattern_id": pattern.id, "confidence": str(pattern.confidence)},
            )
            self.memory.semantic.add(fact)

            # Also create a skill for strong preferences
            if pattern.confidence > 0.8:
                self._create_skill_from_pattern(pattern)

        elif pattern.type == PatternType.MISTAKE:
            # Store as semantic fact for avoidance
            from xcopilot.memory.semantic import SemanticFact

            fact = SemanticFact(
                content=f"Avoid: {pattern.description}",
                project=project_str,
                type="anti_pattern",
                metadata={"pattern_id": pattern.id, "confidence": str(pattern.confidence)},
            )
            self.memory.semantic.add(fact)

        elif pattern.type == PatternType.WORKFLOW:
            # Create a skill for the workflow
            self._create_skill_from_pattern(pattern)

    def _create_skill_from_pattern(self, pattern: Pattern) -> None:
        """Create a skill from a high-confidence pattern."""
        skill_name = pattern.id.replace("pat_", "skill_")
        self.memory.procedural.create_skill(
            name=skill_name,
            description=pattern.description,
            instructions=f"Automatically generated from pattern: {pattern.description}\n\nEvidence: {len(pattern.evidence)} signals",
            triggers=[pattern.type.value],
            compatible_agents=["xcopilot"],
        )

    def decay_old_patterns(self, days: int = 90) -> int:
        """Mark old patterns for pruning. Returns count."""
        # In a full implementation, would scan semantic memory for old facts
        # For now, just prune episodic memory
        return self.memory.episodic.prune(days=days)
