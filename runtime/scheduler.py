"""Scheduler de fondo, neutral respecto del framework.

Un solo loop que despierta cada segundo y dispara los jobs vencidos. No sabe
nada de Telegram: recibe un `context` opaco en la construcción y se lo pasa tal
cual a cada job, así que sirve igual para el bot, un worker o un test.

Vive en `runtime/` y no en `bot/` justamente por eso — la versión anterior
(`bot/jobs/base.py`) importaba `telegram.ext.Application` sólo para anotar, y
eso ataba el motor de scheduling a la interfaz.
"""
from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


class ScheduledJob(ABC):
    """Tarea de fondo que el scheduler corre cada cierto intervalo."""

    def __init__(self, name: str, initial_delay: float = 0.0) -> None:
        self.name = name
        self.next_run = time.time() + initial_delay
        self.is_running = False

    @abstractmethod
    def get_interval(self, context: Any) -> float:
        """Segundos hasta la próxima corrida, resueltos después de cada ciclo."""

    @abstractmethod
    async def run(self, context: Any) -> None:
        """Ejecuta la tarea."""


class OrchestratedScheduler:
    """Loop único por ticks que corre los jobs registrados."""

    def __init__(self, context: Any) -> None:
        self.context = context
        self._running = False
        self._task: asyncio.Task | None = None
        self._jobs: list[ScheduledJob] = []

    @property
    def application(self) -> Any:
        """Alias del contexto para los llamadores que lo tratan como Application."""

        return self.context

    def register_job(self, job: ScheduledJob) -> None:
        self._jobs.append(job)

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="orchestrated-scheduler-loop")
        logger.info("OrchestratedScheduler started.")

    async def stop(self) -> None:
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
            except Exception as exc:  # el loop nunca muere por un job roto
                logger.exception("Error in OrchestratedScheduler main loop: %s", exc)
            await asyncio.sleep(1.0)

    async def _run_job(self, job: ScheduledJob) -> None:
        try:
            logger.debug("Executing orchestrated job: %s", job.name)
            await job.run(self.context)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Unhandled error inside orchestrated job %s: %s", job.name, exc)
        finally:
            interval = job.get_interval(self.context)
            job.next_run = time.time() + interval
            job.is_running = False
            logger.debug("Scheduled next run for job %s in %.1fs", job.name, interval)
