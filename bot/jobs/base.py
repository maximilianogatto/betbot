"""Base interfaces and execution loop for OrchestratedScheduler."""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from telegram.ext import Application

logger = logging.getLogger(__name__)

class ScheduledJob(ABC):
    """Abstract base class representing a background scheduled task."""

    def __init__(self, name: str, initial_delay: float = 0.0) -> None:
        self.name = name
        self.next_run = time.time() + initial_delay
        self.is_running = False

    @abstractmethod
    def get_interval(self, application: Application) -> float:
        """Resolve the interval (in seconds) before the next execution cycle."""
        pass

    @abstractmethod
    async def run(self, application: Application) -> None:
        """Execute the task logic."""
        pass


class OrchestratedScheduler:
    """A tick-based single-loop background job scheduler for BetBot."""

    def __init__(self, application: Application) -> None:
        self.application = application
        self._running = False
        self._task: asyncio.Task | None = None
        self._jobs: list[ScheduledJob] = []

    def register_job(self, job: ScheduledJob) -> None:
        """Register a background ScheduledJob instance."""
        self._jobs.append(job)

    async def start(self) -> None:
        """Start the scheduler loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="orchestrated-scheduler-loop")
        logger.info("OrchestratedScheduler started.")

    async def stop(self) -> None:
        """Stop the scheduler loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("OrchestratedScheduler stopped.")

    async def _loop(self) -> None:
        while self._running:
            try:
                now = time.time()
                for job in self._jobs:
                    if now >= job.next_run and not job.is_running:
                        job.is_running = True
                        asyncio.create_task(self._run_job(job))
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.exception("Error in OrchestratedScheduler main loop: %s", e)
            await asyncio.sleep(1.0)

    async def _run_job(self, job: ScheduledJob) -> None:
        try:
            logger.debug("Executing orchestrated job: %s", job.name)
            await job.run(self.application)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.exception("Unhandled error inside orchestrated job %s: %s", job.name, e)
        finally:
            interval = job.get_interval(self.application)
            job.next_run = time.time() + interval
            job.is_running = False
            logger.debug("Scheduled next run for job %s in %.1fs", job.name, interval)
