"""Utilidades de formato compartidas entre capas.

Viven en `core/` (la capa de abajo) para que tanto los services como los renderers
de `interfaces/` usen la MISMA implementación sin romper el sentido de las
dependencias. Durante PR2-E4 esto quedó duplicado y las dos copias divergieron: la
de los renderers perdió el padding y el manejo de horas (una duración de 2h salía
como "120m 0.0s"), rompiendo el formato de los logs del monitor.
"""
from __future__ import annotations


def format_duration(seconds: float) -> str:
    """Formatea una duración en una representación compacta para el usuario.

    >>> format_duration(45)
    '45s'
    >>> format_duration(68)
    '1m 08s'
    >>> format_duration(3725)
    '1h 02m 05s'
    """
    if seconds is None:
        return "n/d"

    whole_seconds = max(0, int(seconds))
    hours, remainder = divmod(whole_seconds, 3600)
    minutes, secs = divmod(remainder, 60)

    if hours:
        return f"{hours}h {minutes:02d}m {secs:02d}s"
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"
