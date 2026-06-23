"""Hexadecimal bitmask flags and enums for BetBot's binary performance optimization."""

from enum import IntFlag

class OddsProviderFlags(IntFlag):
    """Odds provider bitmask flags (16-bit)."""
    NONE = 0x0000
    XBET = 0x0001
    BETOVO = 0x0002
    SOLCASINO = 0x0004
    BET365 = 0x0008
    MRPUNTER = 0x0010
    MYSTAKE = 0x0020
    BETSSON = 0x0040
    BETWARRIOR = 0x0080
    BZ = 0x0100

class StatsProviderFlags(IntFlag):
    """Statistics provider bitmask flags (16-bit)."""
    NONE = 0x0000
    SPORTRADAR = 0x0001
    SOFASCORE = 0x0002
    FLASHSCORE = 0x0004
    FOOTYSTATS = 0x0008
    SVENSKFOTBOLL = 0x0010
    PALLOLIITTO = 0x0020
    NORWAY = 0x0040
    ROMANIA = 0x0080
    SLOVAKIA = 0x0100
    ALGERIA = 0x0200

class SubscriptionFlags(IntFlag):
    """Chat notification settings bitmask toggles."""
    NONE = 0x0000
    NOTIFY_ODDS_CHANGES = 0x0001  # Bit 0: Alert on odds differences
    NOTIFY_NEW_EVENTS = 0x0002    # Bit 1: Alert when new matches are found
    ALERT_GOALS = 0x0004          # Bit 2: Alert on live goals
    ALERT_RED_CARDS = 0x0008      # Bit 3: Alert on live red cards
    ALERT_YELLOW_CARDS = 0x0010   # Bit 4: Alert on live yellow cards
    REMINDERS_ENABLED = 0x0020    # Bit 5: Reminders pre-kickoff enabled
    NOTIFY_LINEUPS = 0x0040       # Bit 6: Alert on official lineups confirmation

class LiveWatchStatusFlags(IntFlag):
    """Status flags for the live match watch loop."""
    INACTIVE = 0x0000
    WATCHING = 0x0001             # Bit 0: Actively watching live feeds
    FIRED = 0x0002                # Bit 1: Telegram alert dispatched
    CANCELLED = 0x0004            # Bit 2: Manually stopped

class SmallChangeStatusFlags(IntFlag):
    """Status flags for tracking minor odds changes."""
    NONE = 0x0000
    PENDING = 0x0010              # Bit 4: Pending review
    CONFIRMED = 0x0020            # Bit 5: Confirmed by admin/user
    IGNORED = 0x0040              # Bit 6: Dismissed/Ignored

class MatchStatusFlags(IntFlag):
    """Status flags representing the timeline and status of a match."""
    PREMATCH_INACTIVE = 0x0000
    PREMATCH_ACTIVE = 0x0001      # Bit 0: Prematch active for scraping
    LIVE = 0x0002                 # Bit 1: Match is live (in-play)
    FINISHED = 0x0004             # Bit 2: Match has finished
    POSTPONED = 0x0008            # Bit 3: Match postponed or cancelled
    REMINDER_SENT = 0x0010        # Bit 4: Pre-kickoff alert reminder sent

class MarketFlags(IntFlag):
    """Secondary market availability flags inside snapshots (reduces JSON serialization)."""
    NONE = 0x0000
    MARKET_1X2 = 0x0001           # Bit 0: 1X2 Traditional Odds
    MARKET_BTTS = 0x0002          # Bit 1: Both Teams To Score (BTTS)
    MARKET_ASIAN_HANDICAP = 0x0004 # Bit 2: Asian Handicap (AH)
    MARKET_OVER_UNDER = 0x0008    # Bit 3: Goal Line Over/Under
    MARKET_DRAW_NO_BET = 0x0010   # Bit 4: Draw No Bet (DNB)


def ids_to_hex(ids: list[int]) -> str:
    """Convert a list of 1-based integer IDs into a hexadecimal bitmask string."""
    if not ids:
        return ""
    mask = 0
    for id_ in ids:
        mask |= (1 << (id_ - 1))
    return f"{mask:x}"


def hex_to_ids(hex_str: str) -> list[int]:
    """Convert a hexadecimal bitmask string back into a list of 1-based integer IDs."""
    if not hex_str:
        return []
    try:
        mask = int(hex_str, 16)
    except ValueError:
        return []
    ids = []
    bit_len = mask.bit_length()
    for i in range(bit_len):
        if (mask & (1 << i)):
            ids.append(i + 1)
    return ids

