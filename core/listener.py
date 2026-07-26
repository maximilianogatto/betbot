"""Puerto `EventListener`: el contrato que implementa quien consume avisos.

El core publica eventos de dominio sin saber quién los recibe. Cada interfaz
(Telegram hoy; un CLI o una web mañana) implementa este puerto y se suscribe al
bus en el arranque. Así el sentido de las dependencias se mantiene: el core
define el contrato, las capas de arriba lo implementan.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class EventListener(ABC):
    """Consumidor de eventos de dominio."""

    @abstractmethod
    async def handle(self, event: Any) -> None:
        """Procesa un evento ya publicado.

        Se invoca en modo one-way: el publicador no espera resultado y una
        excepción acá no lo interrumpe (el bus la aísla y la reporta). Por eso
        cada implementación es responsable de su propio manejo de errores.
        """
