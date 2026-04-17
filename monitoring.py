"""Lightweight runtime metrics for the Bet365 bot.

This module focuses first on the bot process tree:

- the current Python process
- its child and descendant processes
- Chromium processes that belong to that same tree
- the current SQLite file size

System-wide RAM metrics are still exposed as a secondary section, but the main
numbers are intentionally scoped to this program so they are easier to reason
about in production.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from storage.bet365_tracking import DB_FILE_PATH

logger = logging.getLogger(__name__)

MB = 1024 * 1024
CHROMIUM_NAME_TOKENS = ("chromium", "chromium-browser", "chrome", "headless", "msedge")
DEFAULT_SYSTEM_RAM_WARNING_PERCENT = 90.0
DEFAULT_CHROMIUM_RAM_WARNING_MB = 800.0
MONITOR_LOG_PATH = Path(__file__).resolve().parent / "monitor.log"

_PROCESS = None
_PSUTIL_WARNING_EMITTED = False
_CHILD_PROCESS_WARNING_EMITTED = False


def get_system_metrics() -> dict[str, float | int]:
    """Return current runtime metrics without raising on collection errors."""

    metrics: dict[str, float | int] = {
        "bot_process_ram_mb": 0.0,
        "bot_process_cpu_percent": 0.0,
        "child_processes_count": 0,
        "child_processes_ram_mb": 0.0,
        "chromium_child_processes_count": 0,
        "chromium_child_processes_ram_mb": 0.0,
        "total_app_ram_mb": 0.0,
        "system_ram_percent": 0.0,
        "system_ram_used_mb": 0.0,
        "db_size_mb": 0.0,
    }

    metrics["db_size_mb"] = _get_db_size_mb()

    psutil_module = _get_psutil()
    if psutil_module is None:
        return metrics

    try:
        process = _get_current_process(psutil_module)
        with process.oneshot():
            bot_process_ram_mb = _bytes_to_mb(process.memory_info().rss)
            metrics["bot_process_ram_mb"] = bot_process_ram_mb
            metrics["bot_process_cpu_percent"] = float(process.cpu_percent(interval=None))
            metrics["total_app_ram_mb"] = bot_process_ram_mb
    except Exception:
        logger.exception("No pude leer métricas del proceso principal.")

    global _CHILD_PROCESS_WARNING_EMITTED

    try:
        process = _get_current_process(psutil_module)
        child_processes = process.children(recursive=True)
        child_processes_count = 0
        child_processes_ram_mb = 0.0
        chromium_child_processes_count = 0
        chromium_child_processes_ram_mb = 0.0

        for child_process in child_processes:
            try:
                with child_process.oneshot():
                    child_name = str(child_process.name() or "").lower()
                    child_ram_mb = _bytes_to_mb(child_process.memory_info().rss)

                child_processes_count += 1
                child_processes_ram_mb += child_ram_mb

                if _is_chromium_process_name(child_name):
                    chromium_child_processes_count += 1
                    chromium_child_processes_ram_mb += child_ram_mb
            except (
                psutil_module.NoSuchProcess,
                psutil_module.AccessDenied,
                psutil_module.ZombieProcess,
            ):
                continue

        metrics["child_processes_count"] = child_processes_count
        metrics["child_processes_ram_mb"] = child_processes_ram_mb
        metrics["chromium_child_processes_count"] = chromium_child_processes_count
        metrics["chromium_child_processes_ram_mb"] = chromium_child_processes_ram_mb
        metrics["total_app_ram_mb"] = float(metrics.get("bot_process_ram_mb", 0.0)) + child_processes_ram_mb
    except Exception as error:
        if not _CHILD_PROCESS_WARNING_EMITTED:
            logger.warning(
                "No pude leer métricas completas de procesos hijos del bot; continúo con métricas parciales. "
                "Detalle: %s",
                error,
            )
            _CHILD_PROCESS_WARNING_EMITTED = True

    try:
        virtual_memory = psutil_module.virtual_memory()
        metrics["system_ram_percent"] = float(virtual_memory.percent)
        metrics["system_ram_used_mb"] = _bytes_to_mb(virtual_memory.used)
    except Exception:
        logger.exception("No pude leer métricas de RAM del sistema.")

    return metrics


def format_system_metrics_message(metrics: dict[str, float | int]) -> str:
    """Build a Telegram-friendly status message from current metrics."""

    return (
        "📊 Estado del bot\n\n"
        "Proceso bot:\n"
        f"- RAM: {metrics.get('bot_process_ram_mb', 0.0):.1f} MB\n"
        f"- CPU: {metrics.get('bot_process_cpu_percent', 0.0):.1f} %\n\n"
        "Procesos hijos:\n"
        f"- Total: {int(metrics.get('child_processes_count', 0))}\n"
        f"- RAM total: {metrics.get('child_processes_ram_mb', 0.0):.1f} MB\n\n"
        "Chromium del bot:\n"
        f"- Procesos: {int(metrics.get('chromium_child_processes_count', 0))}\n"
        f"- RAM: {metrics.get('chromium_child_processes_ram_mb', 0.0):.1f} MB\n\n"
        "Aplicación completa:\n"
        f"- RAM total: {metrics.get('total_app_ram_mb', 0.0):.1f} MB\n\n"
        "Base de datos:\n"
        f"- Tamaño: {metrics.get('db_size_mb', 0.0):.1f} MB\n\n"
        "Sistema:\n"
        f"- RAM total usada: {metrics.get('system_ram_percent', 0.0):.1f} %\n"
        f"- RAM usada: {metrics.get('system_ram_used_mb', 0.0):.1f} MB"
    )


def format_monitor_log_block(metrics: dict[str, float | int]) -> str:
    """Build the periodic monitor block used in logs and optional file output."""

    return (
        "[MONITOR]\n"
        f"RAM bot: {metrics.get('bot_process_ram_mb', 0.0):.1f} MB\n"
        f"CPU bot: {metrics.get('bot_process_cpu_percent', 0.0):.1f} %\n"
        f"Hijos: {int(metrics.get('child_processes_count', 0))} procesos "
        f"({metrics.get('child_processes_ram_mb', 0.0):.1f} MB)\n"
        f"Chromium del bot: {int(metrics.get('chromium_child_processes_count', 0))} procesos "
        f"({metrics.get('chromium_child_processes_ram_mb', 0.0):.1f} MB)\n"
        f"RAM app total: {metrics.get('total_app_ram_mb', 0.0):.1f} MB\n"
        f"DB: {metrics.get('db_size_mb', 0.0):.1f} MB\n"
        f"RAM sistema: {metrics.get('system_ram_percent', 0.0):.1f} % "
        f"({metrics.get('system_ram_used_mb', 0.0):.1f} MB)"
    )


def get_metric_warnings(
    metrics: dict[str, float | int],
    *,
    system_ram_warning_percent: float = DEFAULT_SYSTEM_RAM_WARNING_PERCENT,
    chromium_ram_warning_mb: float = DEFAULT_CHROMIUM_RAM_WARNING_MB,
) -> list[str]:
    """Return human-readable warnings when metrics exceed configured thresholds."""

    warnings: list[str] = []

    if metrics.get("system_ram_percent", 0.0) > system_ram_warning_percent:
        warnings.append(
            "Uso de RAM del sistema por encima del umbral: "
            f"{metrics['system_ram_percent']:.1f}% > {system_ram_warning_percent:.1f}%."
        )

    if metrics.get("chromium_child_processes_ram_mb", 0.0) > chromium_ram_warning_mb:
        warnings.append(
            "Uso de RAM de Chromium del bot por encima del umbral: "
            f"{metrics['chromium_child_processes_ram_mb']:.1f} MB > {chromium_ram_warning_mb:.1f} MB."
        )

    return warnings


def append_monitor_log(log_text: str, log_path: Path | None = None) -> None:
    """Append one metrics block to a local monitor log file."""

    target_path = log_path or MONITOR_LOG_PATH

    try:
        with target_path.open("a", encoding="utf-8") as file_handle:
            file_handle.write(log_text)
            file_handle.write("\n\n")
    except OSError:
        logger.exception("No pude escribir monitor.log en %s.", target_path)


def _get_psutil():
    """Import psutil lazily and warn once if it is not installed."""

    global _PSUTIL_WARNING_EMITTED

    try:
        import psutil  # type: ignore
    except ImportError:
        if not _PSUTIL_WARNING_EMITTED:
            logger.warning(
                "psutil no está instalado; el monitoreo de recursos devolverá métricas parciales."
            )
            _PSUTIL_WARNING_EMITTED = True
        return None

    return psutil


def _get_current_process(psutil_module):
    """Return a cached psutil process for the current bot runtime."""

    global _PROCESS

    if _PROCESS is None or getattr(_PROCESS, "pid", None) != os.getpid():
        _PROCESS = psutil_module.Process(os.getpid())
        _PROCESS.cpu_percent(interval=None)

    return _PROCESS


def _get_db_size_mb() -> float:
    """Return the SQLite file size in MB."""

    try:
        if DB_FILE_PATH.exists():
            return _bytes_to_mb(DB_FILE_PATH.stat().st_size)
    except OSError:
        logger.exception("No pude leer el tamaño de la base SQLite.")

    return 0.0


def _bytes_to_mb(value: int | float) -> float:
    """Convert bytes into megabytes."""

    return float(value) / MB


def _is_chromium_process_name(process_name: str) -> bool:
    """Return whether a process name looks like Chromium/Chrome."""

    return any(token in process_name for token in CHROMIUM_NAME_TOKENS)
