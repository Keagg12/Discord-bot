"""
config.py – Central configuration for the moderation bot.
All tuneable values live here so they are easy to change in one place.
"""

from __future__ import annotations

import os
from typing import Final


class Config:
    """Static configuration bag – no instances needed."""

    # ------------------------------------------------------------------
    # Core
    # ------------------------------------------------------------------

    PREFIX: Final[str] = "!"          # Legacy prefix (slash commands are primary)
    BOT_VERSION: Final[str] = "1.0.0"

    # ------------------------------------------------------------------
    # Database
    # ------------------------------------------------------------------

    DB_PATH: Final[str] = os.path.join(
        os.path.dirname(__file__), "data", "moderation.db"
    )

    # ------------------------------------------------------------------
    # Cogs to load
    # ------------------------------------------------------------------

    COGS: Final[list[str]] = [
        "cogs.moderation",
        "cogs.automod",
        "cogs.logging",
        "cogs.utility",
        "cogs.events",
    ]

    # ------------------------------------------------------------------
    # Colours (hex integers for discord.Colour)
    # ------------------------------------------------------------------

    COLOUR_SUCCESS: Final[int] = 0x2ECC71   # green
    COLOUR_ERROR: Final[int] = 0xE74C3C     # red
    COLOUR_WARNING: Final[int] = 0xF39C12   # amber
    COLOUR_INFO: Final[int] = 0x3498DB      # blue
    COLOUR_MOD: Final[int] = 0x9B59B6       # purple  (moderation actions)
    COLOUR_LOG: Final[int] = 0x95A5A6       # grey    (server log events)

    # ------------------------------------------------------------------
    # Auto-mod thresholds
    # ------------------------------------------------------------------

    SPAM_MESSAGE_LIMIT: Final[int] = 5        # messages per …
    SPAM_TIME_WINDOW: Final[int] = 5          # … seconds

    MAX_MENTIONS: Final[int] = 5              # unique user mentions per message
    MAX_CAPS_PERCENT: Final[float] = 0.70     # 70 % uppercase → caps-spam
    MIN_CAPS_LENGTH: Final[int] = 10          # only check strings this long+
    MAX_EMOJI_COUNT: Final[int] = 10          # emoji per message

    # ------------------------------------------------------------------
    # Auto-mod: bad-word list  (extend as needed)
    # ------------------------------------------------------------------

    BAD_WORDS: Final[list[str]] = [
        "badword1",
        "badword2",
        "slur1",
        "slur2",
    ]

    # ------------------------------------------------------------------
    # Known scam / phishing domains
    # ------------------------------------------------------------------

    SCAM_DOMAINS: Final[list[str]] = [
        "discord-nitro.gift",
        "discordnitro.com",
        "free-nitro.ru",
        "steamcommunity.ru",
        "steamwaliet.com",
        "csgo-skins.com",
    ]

    # ------------------------------------------------------------------
    # Discord invite regex pattern (used in anti-invite rule)
    # ------------------------------------------------------------------

    INVITE_PATTERN: Final[str] = (
        r"(discord\.gg|discord\.com/invite|discordapp\.com/invite)"
        r"[/\\]+"
        r"([a-zA-Z0-9\-]+)"
    )

    # ------------------------------------------------------------------
    # Logging channel name (created per-guild if absent)
    # ------------------------------------------------------------------

    DEFAULT_LOG_CHANNEL: Final[str] = "mod-logs"

    # ------------------------------------------------------------------
    # Purge limits
    # ------------------------------------------------------------------

    MAX_PURGE: Final[int] = 500

    # ------------------------------------------------------------------
    # Slowmode limits (seconds)
    # ------------------------------------------------------------------

    MAX_SLOWMODE: Final[int] = 21600   # 6 hours (Discord maximum)
