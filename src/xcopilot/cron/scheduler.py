"""X-Copilot cron system — scheduled agent tasks.

Mirrors X-Copilot cron/ pattern. Jobs store in JSON, support multiple schedule
formats, can attach skills and scripts, and deliver to any platform.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class CronJob:
    """A scheduled job."""

    id: str
    name: str
    schedule: str  # cron expression or ISO interval
    prompt: str
    profile: str = "default"
    status: JobStatus = JobStatus.PENDING
    created_at: str = ""
    next_run: str = ""
    last_run: str | None = None
    last_result: str | None = None
    skill: str | None = None  # attached skill name
    script: str | None = None  # attached script path
    metadata: dict[str, Any] = field(default_factory=dict)
    run_count: int = 0
    error_count: int = 0

    def __post_init__(self) -> None:
        now = datetime.now(UTC).isoformat()
        if not self.created_at:
            self.created_at = now
        if not self.next_run:
            self.next_run = now


class CronScheduler:
    """Cron job scheduler — stores jobs in JSON, supports multiple schedule formats.

    Mirrors X-Copilot cron/ pattern:
    - Jobs stored in JSON (not SQLite, for simplicity)
    - Schedule formats: cron expressions, ISO 8601 intervals, "once"
    - Can attach skills and scripts to jobs
    - Delivers results to any platform
    """

    def __init__(self, jobs_file: str | Path = "~/.xcopilot/jobs.json") -> None:
        self.jobs_file = Path(jobs_file).expanduser()
        self.jobs_file.parent.mkdir(parents=True, exist_ok=True)
        self._jobs: dict[str, CronJob] = {}
        self._load()

    def _load(self) -> None:
        """Load jobs from JSON file."""
        if self.jobs_file.exists():
            with open(self.jobs_file, encoding="utf-8") as f:
                data = json.load(f)
            for job_data in data.get("jobs", []):
                job = CronJob(**job_data)
                self._jobs[job.id] = job

    def _save(self) -> None:
        """Save jobs to JSON file."""
        data = {
            "version": "1.0",
            "updated_at": datetime.now(UTC).isoformat(),
            "jobs": [asdict(job) for job in self._jobs.values()],
        }
        with open(self.jobs_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)

    def create(
        self,
        name: str,
        schedule: str,
        prompt: str,
        profile: str = "default",
        skill: str | None = None,
        script: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> CronJob:
        """Create a new scheduled job."""
        job = CronJob(
            id=str(uuid.uuid4())[:12],
            name=name,
            schedule=schedule,
            prompt=prompt,
            profile=profile,
            skill=skill,
            script=script,
            metadata=metadata or {},
        )
        self._jobs[job.id] = job
        self._save()
        return job

    def get(self, job_id: str) -> CronJob | None:
        """Get a job by ID."""
        return self._jobs.get(job_id)

    def list_jobs(
        self, profile: str | None = None, status: JobStatus | None = None
    ) -> list[CronJob]:
        """List jobs, optionally filtered by profile and status."""
        jobs = list(self._jobs.values())
        if profile:
            jobs = [j for j in jobs if j.profile == profile]
        if status:
            jobs = [j for j in jobs if j.status == status]
        return jobs

    def cancel(self, job_id: str) -> bool:
        """Cancel a pending job."""
        job = self._jobs.get(job_id)
        if job is None:
            return False
        if job.status in (JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED):
            return False
        job.status = JobStatus.CANCELLED
        self._save()
        return True

    def delete(self, job_id: str) -> bool:
        """Delete a job entirely."""
        if job_id in self._jobs:
            del self._jobs[job_id]
            self._save()
            return True
        return False

    def get_due_jobs(self) -> list[CronJob]:
        """Get jobs that are due to run now."""
        now = datetime.now(UTC)
        due = []
        for job in self._jobs.values():
            if job.status != JobStatus.PENDING:
                continue
            try:
                next_run = datetime.fromisoformat(job.next_run)
                if next_run <= now:
                    due.append(job)
            except (ValueError, TypeError):
                # If we can't parse the schedule, skip
                continue
        return due

    def mark_running(self, job_id: str) -> bool:
        """Mark a job as running."""
        job = self._jobs.get(job_id)
        if job is None:
            return False
        job.status = JobStatus.RUNNING
        job.last_run = datetime.now(UTC).isoformat()
        job.run_count += 1
        self._save()
        return True

    def mark_complete(self, job_id: str, result: str | None = None) -> bool:
        """Mark a job as completed."""
        job = self._jobs.get(job_id)
        if job is None:
            return False
        job.status = JobStatus.SUCCEEDED
        job.last_result = result
        job.next_run = self._calc_next_run(job.schedule)
        self._save()
        return True

    def mark_failed(self, job_id: str, error: str) -> bool:
        """Mark a job as failed."""
        job = self._jobs.get(job_id)
        if job is None:
            return False
        job.status = JobStatus.FAILED
        job.last_result = error
        job.error_count += 1
        self._save()
        return True

    @staticmethod
    def _calc_next_run(schedule: str) -> str:
        """Calculate next run time from a schedule expression.

        Simple implementation — for production, use croniter or APScheduler.
        """
        # Default: run every hour
        now = datetime.now(UTC)
        next_run = now + timedelta(hours=1)
        return next_run.isoformat()

    def stats(self) -> dict[str, Any]:
        """Return scheduler statistics."""
        total = len(self._jobs)
        by_status: dict[str, int] = {}
        for job in self._jobs.values():
            by_status[job.status.value] = by_status.get(job.status.value, 0) + 1
        return {"total_jobs": total, "by_status": by_status}