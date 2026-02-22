"""Pack job lifecycle helpers for China Lens."""

from __future__ import annotations

from datetime import UTC, datetime

from ..models import PIPELINE_STAGES, JobStatus, PackJob, PackStatus, PipelineStage


def create_stage_progress() -> dict[PipelineStage, int]:
    """Initialize stage progress map."""
    return {stage: 0 for stage in PIPELINE_STAGES}


def progress_job(job: PackJob, step: int = 25) -> PackJob:
    """Advance a running job by one progress step."""
    if job.status != JobStatus.RUNNING:
        return job

    current = job.stage
    current_value = job.stage_progress.get(current, 0)
    new_value = min(100, current_value + step)
    job.stage_progress[current] = new_value

    if new_value == 100:
        current_idx = PIPELINE_STAGES.index(current)
        if current_idx == len(PIPELINE_STAGES) - 1:
            job.status = JobStatus.COMPLETED
            job.finished_at = datetime.now(UTC)
        else:
            job.stage = PIPELINE_STAGES[current_idx + 1]

    total = sum(job.stage_progress.values())
    job.progress_pct = int(total / len(PIPELINE_STAGES))
    return job


def cancel_job(job: PackJob) -> PackJob:
    """Mark a job as canceled in a single place."""
    job.cancel_requested = True
    job.status = JobStatus.CANCELED
    job.finished_at = datetime.now(UTC)
    return job


def pack_status_from_job(job: PackJob) -> PackStatus:
    """Map job status to pack status."""
    if job.status == JobStatus.QUEUED:
        return PackStatus.QUEUED
    if job.status == JobStatus.RUNNING:
        return PackStatus.RUNNING
    if job.status == JobStatus.COMPLETED:
        return PackStatus.READY
    if job.status == JobStatus.CANCELED:
        return PackStatus.CANCELED
    return PackStatus.FAILED
