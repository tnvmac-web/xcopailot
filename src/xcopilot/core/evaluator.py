"""Evaluator — scores output against criteria, detects improvement."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class EvaluationResult:
    """Result of an evaluation."""

    score: float
    breakdown: dict[str, float]
    passed: bool


class Evaluator:
    """Scores agent output against quality criteria."""

    def __init__(
        self,
        criteria: dict[str, float] | None = None,
        threshold: float = 0.7,
    ) -> None:
        self.criteria = criteria or self.default_criteria()
        self.threshold = threshold
        self._history: dict[str, list[float]] = {}

    def default_criteria(self) -> dict[str, float]:
        """Default evaluation criteria weights."""
        return {
            "correctness": 0.4,
            "style": 0.2,
            "safety": 0.4,
        }

    def score(self, output: str, criteria: dict[str, float] | None = None) -> float:
        """Score output against criteria. Returns 0.0-1.0."""
        eval_criteria = criteria or self.criteria
        breakdown = {}

        for criterion in eval_criteria:
            if criterion == "correctness":
                breakdown[criterion] = self._score_correctness(output)
            elif criterion == "style":
                breakdown[criterion] = self._score_style(output)
            elif criterion == "safety":
                breakdown[criterion] = self._score_safety(output)
            else:
                breakdown[criterion] = 0.5

        # Weighted average
        total = sum(breakdown[c] * w for c, w in eval_criteria.items())
        return min(max(total, 0.0), 1.0)

    def evaluate(
        self,
        output: str,
        criteria: dict[str, float] | None = None,
    ) -> EvaluationResult:
        """Evaluate output and return detailed result."""
        eval_criteria = criteria or self.criteria
        breakdown = {}
        for criterion in eval_criteria:
            if criterion == "correctness":
                breakdown[criterion] = self._score_correctness(output)
            elif criterion == "style":
                breakdown[criterion] = self._score_style(output)
            elif criterion == "safety":
                breakdown[criterion] = self._score_safety(output)
            else:
                breakdown[criterion] = 0.5

        total = sum(breakdown[c] * w for c, w in eval_criteria.items())
        score = min(max(total, 0.0), 1.0)

        return EvaluationResult(
            score=score,
            breakdown=breakdown,
            passed=score >= self.threshold,
        )

    def _score_correctness(self, output: str) -> float:
        """Score code correctness indicators."""
        score = 0.5  # baseline

        # Type hints present
        if re.search(r":\s*\w+\s*(?:->|,|\))", output):
            score += 0.15

        # Docstrings
        if '"""' in output or "'''" in output:
            score += 0.1

        # No obvious syntax errors (basic check)
        if not re.search(r"\b(import|from)\s+\w+\s*;\s*(?:import|from)", output):
            score += 0.1

        # Has function definitions
        if re.search(r"def\s+\w+\s*\(", output):
            score += 0.15

        return min(score, 1.0)

    def _score_style(self, output: str) -> float:
        """Score code style indicators."""
        score = 0.5

        # Consistent indentation (4 spaces)
        lines = output.split("\n")
        indents = [len(line) - len(line.lstrip()) for line in lines if line.strip()]
        if indents and all(i % 4 == 0 for i in indents):
            score += 0.2

        # No trailing whitespace
        if not any(line.rstrip() != line for line in lines):
            score += 0.1

        # Reasonable line length
        if all(len(line) <= 100 for line in lines):
            score += 0.1

        # Snake_case for functions/variables
        if re.search(r"def\s+[a-z_][a-z0-9_]*\s*\(", output):
            score += 0.1

        return min(score, 1.0)

    def _score_safety(self, output: str) -> float:
        """Score safety - penalize dangerous patterns."""
        score = 1.0

        dangerous_patterns = [
            (r"os\.system\s*\(", 0.3),
            (r"subprocess\.(run|call|Popen)\s*\(.*shell\s*=\s*True", 0.25),
            (r"eval\s*\(", 0.3),
            (r"exec\s*\(", 0.3),
            (r"__import__\s*\(", 0.2),
            (r"rm\s+-rf\s+/", 0.4),
            (r"format\s+[cC]:", 0.4),
            (r"del\s+/[sqf]", 0.3),
            (r"pickle\.loads?\s*\(", 0.15),
            (r"yaml\.load\s*\(.*Loader\s*=\s*yaml\.CLoader", 0.15),
        ]

        for pattern, penalty in dangerous_patterns:
            if re.search(pattern, output, re.IGNORECASE):
                score -= penalty

        # Network calls to unknown endpoints
        if re.search(
            r"(requests|urllib|httpx)\.(get|post|put|delete)\s*\(\s*[\"'][^\"']*[\"']", output
        ):
            # Allow known safe domains
            safe_domains = [
                "api.github.com",
                "api.openai.com",
                "api.anthropic.com",
                "localhost",
                "127.0.0.1",
            ]
            if not any(domain in output for domain in safe_domains):
                score -= 0.15

        return max(score, 0.0)

    def improved(self, pattern_id: str, old_score: float, new_score: float) -> bool:
        """Check if new score represents improvement over old."""
        if pattern_id not in self._history:
            self._history[pattern_id] = []

        self._history[pattern_id].append(new_score)
        return new_score > old_score

    def should_adapt(self, score: float, threshold: float | None = None) -> bool:
        """Return True if score is below adaptation threshold."""
        t = threshold or self.threshold
        return score < t
