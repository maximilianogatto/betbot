from telegram import Bot

from alerts.telegram_alerts import build_alert_message, send_alert
from monitors.rules import evaluate_event
from services.sports_api import SportsAPIClient


async def run_monitoring_cycle(
    provider: SportsAPIClient,
    bot: Bot,
    chat_id: int | str,
) -> None:
    """
    Ejecuta un ciclo simple de monitoreo:
    trae eventos, evalúa reglas y envía alertas si corresponde.
    """

    events = await provider.fetch_events()

    for event in events:
        reasons = evaluate_event(event)

        if not reasons:
            continue

        message = build_alert_message(event, reasons)
        await send_alert(bot=bot, chat_id=chat_id, message=message)
