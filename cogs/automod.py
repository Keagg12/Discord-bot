"""
cogs/automod.py
===============
Automatic moderation: fires on every incoming message and applies
configurable filters before the message is seen by members.

Filters (all toggleable via guild_config):
  • Anti-spam          – rate-limited message volume
  • Anti-invite        – strips / deletes Discord invite links
  • Anti-scam          – deletes known phishing domains
  • Anti-mass mention  – punishes @mentioning many users at once
  • Anti-caps spam     – flags ALL-CAPS shouting
  • Anti-emoji spam    – too many emoji in one message
  • Bad-word filter    – configurable profanity list
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
import unicodedata
from collections import defaultdict, deque
from typing import Deque, Dict, Tuple

import discord
from discord.ext import commands

from config import Config
from utils.embeds import error_embed, warning_embed

logger = logging.getLogger("automod")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_INVITE_RE = re.compile(Config.INVITE_PATTERN, re.IGNORECASE)
_URL_RE = re.compile(r"https?://([^\s/]+)", re.IGNORECASE)


def _count_emoji(text: str) -> int:
    """Return the number of emoji-category codepoints in *text*."""
    return sum(
        1 for ch in text
        if unicodedata.category(ch) in ("So",) or "\U0001F000" <= ch <= "\U0001FFFF"
    )


def _caps_ratio(text: str) -> float:
    """Return the fraction of alphabetic chars that are uppercase."""
    alpha = [c for c in text if c.isalpha()]
    if not alpha:
        return 0.0
    return sum(1 for c in alpha if c.isupper()) / len(alpha)


# ---------------------------------------------------------------------------
# Spam tracker
# ---------------------------------------------------------------------------

class SpamTracker:
    """
    Per-guild, per-user sliding-window spam counter.
    Tracks the timestamps of recent messages and returns True when the
    rate exceeds SPAM_MESSAGE_LIMIT within SPAM_TIME_WINDOW seconds.
    """

    # guild_id → user_id → deque of UNIX timestamps
    _windows: Dict[int, Dict[int, Deque[float]]] = defaultdict(
        lambda: defaultdict(deque)
    )

    @classmethod
    def is_spamming(cls, guild_id: int, user_id: int) -> bool:
        now = time.monotonic()
        window: Deque[float] = cls._windows[guild_id][user_id]

        # Evict old entries
        cutoff = now - Config.SPAM_TIME_WINDOW
        while window and window[0] < cutoff:
            window.popleft()

        window.append(now)
        return len(window) > Config.SPAM_MESSAGE_LIMIT

    @classmethod
    def reset(cls, guild_id: int, user_id: int) -> None:
        cls._windows[guild_id][user_id].clear()


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------

class AutoMod(commands.Cog, name="AutoMod"):
    """Passive, event-driven auto-moderation."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @property
    def db(self):
        return self.bot.db

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    @commands.Cog.listener("on_message")
    async def on_message(self, message: discord.Message) -> None:
        """Run every filter in order. Deletes/warns on first match."""
        # Ignore DMs, bots, and server owners.
        if not message.guild:
            return
        if message.author.bot:
            return
        if message.author.id == message.guild.owner_id:
            return

        # Members with manage_messages bypass auto-mod.
        if message.author.guild_permissions.manage_messages:
            return

        cfg = await self.db.get_guild_config(message.guild.id)
        if not cfg["automod_enabled"]:
            return

        # Run each check; stop at first hit.
        checks = [
            (cfg["anti_spam"],         self._check_spam),
            (cfg["anti_invite"],       self._check_invite),
            (cfg["anti_scam"],         self._check_scam),
            (cfg["anti_mass_mention"], self._check_mentions),
            (cfg["anti_caps"],         self._check_caps),
            (cfg["anti_emoji_spam"],   self._check_emoji),
            (cfg["bad_word_filter"],   self._check_bad_words),
        ]
        for enabled, handler in checks:
            if enabled:
                triggered = await handler(message)
                if triggered:
                    break

    # ------------------------------------------------------------------
    # Individual filters
    # ------------------------------------------------------------------

    async def _check_spam(self, message: discord.Message) -> bool:
        if not SpamTracker.is_spamming(message.guild.id, message.author.id):
            return False
        SpamTracker.reset(message.guild.id, message.author.id)
        await self._punish(
            message,
            reason="Auto-mod: Spam detected",
            action="timeout",
            duration_minutes=10,
        )
        return True

    async def _check_invite(self, message: discord.Message) -> bool:
        if not _INVITE_RE.search(message.content):
            return False
        await self._delete_and_warn(
            message,
            "Your message was removed: **Invite links are not allowed.**",
        )
        await self._log_automod(message, "Invite link detected")
        return True

    async def _check_scam(self, message: discord.Message) -> bool:
        lower = message.content.lower()
        for domain in Config.SCAM_DOMAINS:
            if domain in lower:
                await self._delete_and_warn(
                    message,
                    "Your message was removed: **Potential scam/phishing link detected.**",
                )
                await self._punish(
                    message,
                    reason="Auto-mod: Scam/phishing link",
                    action="timeout",
                    duration_minutes=60,
                )
                return True
        return False

    async def _check_mentions(self, message: discord.Message) -> bool:
        if len(message.mentions) < Config.MAX_MENTIONS:
            return False
        await self._delete_and_warn(
            message,
            f"Your message was removed: **Mass mentions ({len(message.mentions)}) are not allowed.**",
        )
        await self._punish(
            message,
            reason=f"Auto-mod: Mass mentions ({len(message.mentions)})",
            action="timeout",
            duration_minutes=15,
        )
        return True

    async def _check_caps(self, message: discord.Message) -> bool:
        content = message.content
        if len(content) < Config.MIN_CAPS_LENGTH:
            return False
        if _caps_ratio(content) < Config.MAX_CAPS_PERCENT:
            return False
        await self._delete_and_warn(
            message,
            "Your message was removed: **Excessive caps are not allowed.**",
        )
        return True

    async def _check_emoji(self, message: discord.Message) -> bool:
        count = _count_emoji(message.content)
        if count <= Config.MAX_EMOJI_COUNT:
            return False
        await self._delete_and_warn(
            message,
            f"Your message was removed: **Too many emoji ({count}).**",
        )
        return True

    async def _check_bad_words(self, message: discord.Message) -> bool:
        lower = message.content.lower()
        for word in Config.BAD_WORDS:
            if word in lower:
                await self._delete_and_warn(
                    message,
                    "Your message was removed: **Prohibited language detected.**",
                )
                await self._log_automod(message, f"Bad word: {word}")
                return True
        return False

    # ------------------------------------------------------------------
    # Action helpers
    # ------------------------------------------------------------------

    async def _delete_and_warn(
        self, message: discord.Message, dm_text: str
    ) -> None:
        """Delete the offending message and DM the author."""
        try:
            await message.delete()
        except discord.HTTPException:
            pass

        try:
            await message.author.send(embed=warning_embed(dm_text))
        except discord.HTTPException:
            pass  # DMs closed

        # Post a transient warning in the channel
        try:
            warn_msg = await message.channel.send(
                f"⚠️ {message.author.mention} {dm_text}",
                delete_after=8,
            )
        except discord.HTTPException:
            pass

    async def _punish(
        self,
        message: discord.Message,
        reason: str,
        action: str,
        duration_minutes: int = 10,
    ) -> None:
        """Apply a timeout or other action after deleting the message."""
        member: discord.Member = message.author  # type: ignore[assignment]
        guild: discord.Guild = message.guild

        # Add a warning record
        await self.db.add_warning(guild.id, member.id, self.bot.user.id, reason)
        await self.db.log_action(guild.id, member.id, self.bot.user.id, action, reason)

        if action == "timeout":
            from datetime import timedelta
            until = discord.utils.utcnow() + timedelta(minutes=duration_minutes)
            try:
                await member.timeout(until, reason=reason)
            except discord.Forbidden:
                logger.warning(
                    "Cannot timeout %s in %s – insufficient perms.", member, guild
                )

    async def _log_automod(
        self, message: discord.Message, detail: str
    ) -> None:
        """Send an auto-mod log entry to the guild log channel."""
        cfg = await self.db.get_logging_config(message.guild.id)
        if not cfg["log_channel_id"]:
            return
        ch = message.guild.get_channel(cfg["log_channel_id"])
        if not ch:
            return
        embed = discord.Embed(
            title="🤖 Auto-Mod Action",
            colour=Config.COLOUR_WARNING,
        )
        embed.add_field(name="User", value=message.author.mention, inline=True)
        embed.add_field(name="Channel", value=message.channel.mention, inline=True)
        embed.add_field(name="Detail", value=detail, inline=False)
        embed.add_field(
            name="Message",
            value=message.content[:1024] or "*(empty)*",
            inline=False,
        )
        embed.set_footer(text=f"User ID: {message.author.id}")
        try:
            await ch.send(embed=embed)
        except discord.HTTPException:
            pass


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AutoMod(bot))
