from telegram import Bot

from services.sports_api import SportsEvent


def build_alert_message(event: SportsEvent, reasons: list[str]) -> str:
    reasons_text = "\n".join(f"- {reason}" for reason in reasons) or "- Sin detalles"

    return (
        "Alerta deportiva detectada\n\n"
        f"Deporte: {event.sport}\n"
        f"Liga: {event.league}\n"
        f"Partido: {event.home_team} vs {event.away_team}\n"
        f"Inicio: {event.starts_at}\n\n"
        f"Motivos:\n{reasons_text}"
    )


async def send_alert(bot: Bot, chat_id: int | str, message: str) -> None:
    await bot.send_message(chat_id=chat_id, text=message)
