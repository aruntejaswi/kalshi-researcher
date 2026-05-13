"""Asyncio batch processor: runs N tickers through run_analysis, 3 at a time."""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

log = logging.getLogger(__name__)

Runner = Callable[[str], Awaitable[dict[str, Any]]]


@dataclass
class BatchJob:
    id: str
    total: int
    pending: list[str]
    in_progress: set[str] = field(default_factory=set)
    completed: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)
    results: dict[str, dict[str, Any]] = field(default_factory=dict)
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    status: str = "running"  # "running" | "done" | "cancelled"

    def snapshot(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "total": self.total,
            "pending": list(self.pending),
            "in_progress": sorted(self.in_progress),
            "completed": list(self.completed),
            "failed": dict(self.failed),
            "results": self.results,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "status": self.status,
            "progress": (len(self.completed) + len(self.failed)) / self.total if self.total else 1.0,
        }


class BatchProcessor:
    """In-memory batch coordinator with a fixed concurrency."""

    def __init__(self, concurrency: int = 3):
        self.concurrency = concurrency
        self.jobs: dict[str, BatchJob] = {}
        self._semaphore = asyncio.Semaphore(concurrency)
        self._tasks: dict[str, asyncio.Task[None]] = {}

    def submit(self, tickers: list[str], runner: Runner) -> BatchJob:
        job_id = uuid.uuid4().hex[:12]
        # Dedupe while preserving order.
        seen: set[str] = set()
        ordered = [t for t in tickers if not (t in seen or seen.add(t))]
        job = BatchJob(id=job_id, total=len(ordered), pending=list(ordered))
        self.jobs[job_id] = job
        self._tasks[job_id] = asyncio.create_task(self._run(job, runner))
        return job

    def get(self, job_id: str) -> BatchJob | None:
        return self.jobs.get(job_id)

    async def _run(self, job: BatchJob, runner: Runner) -> None:
        async def one(ticker: str) -> None:
            async with self._semaphore:
                if job.status == "cancelled":
                    return
                job.in_progress.add(ticker)
                try:
                    job.results[ticker] = await runner(ticker)
                    job.completed.append(ticker)
                except Exception as exc:  # noqa: BLE001
                    log.exception("batch run failed for %s", ticker)
                    job.failed[ticker] = f"{type(exc).__name__}: {exc}"
                finally:
                    job.in_progress.discard(ticker)
                    try:
                        job.pending.remove(ticker)
                    except ValueError:
                        pass

        try:
            await asyncio.gather(*(one(t) for t in job.pending), return_exceptions=True)
        finally:
            job.finished_at = time.time()
            if job.status != "cancelled":
                job.status = "done"

    async def shutdown(self) -> None:
        for t in self._tasks.values():
            t.cancel()
        for t in self._tasks.values():
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass
