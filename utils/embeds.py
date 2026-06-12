"""
utils/embeds.py
===============
Factory functions for the standardised embeds used throughout the bot.

Every embed follows the same visual language:
  • Colour encodes severity / type.
  • Timestamp is always set to utcnow.
  • A short icon prefix in the title signals the action category.
"""

from __future__ import annotations

from typing import Optional

import discord

from config import Config


# ---------------------------------------------------------------------------
# Simple status embeds
# ---------------------------------------------------------------------------

def success_embed(description: str, title: str = "✅ Success") -> discord.Embed:
    """Green embed for successful operations."""
    embed = discord.Embed(title=title, description=description, colour=Config.COLOUR_SUCCESS)
    embed.timestamp = discord.utils.utcnow()
    return embed


def error_embed(description: str, title: str = "❌ Error") -> discord.Embed:
    """Red embed for errors and failures."""
    embed = discord.Embed(title=title, description=description, colour=Config.COLOUR_ERROR)
    embed.timestamp = discord.utils.utcnow()
    return embed


def warning_embed(description: str, title: str = "⚠️ Warning") -> discord.Embed:
    """Amber embed for warnings and cautions."""
    embed = discord.Embed(title=title, description=description, colour=Config.COLOUR_WARNING)
    embed.timestamp = discord.utils.utcnow()
    return embed


def info_embed(description: str, title: str = "ℹ️ Info") -> discord.Embed:
    """Blue embed for neutral information."""
    embed = discord.Embed(title=title, description=description, colour=Config.COLOUR_INFO)
    embed.timestamp = discord.utils.utcnow()
    return embed


# ---------------------------------------------------------------------------
# Moderation action embed
# ---------------------------------------------------------------------------

_ACTION_ICONS: dict[str, str] = {
    "Ban": "🔨",
    "Unban": "✅",
    "Kick": "👢",
    "Timeout": "⏱️",
    "Untimeout": "✅",
    "Warning": "⚠️",
    "Purge": "🗑️",
}


def mod_action_embed(
    action: str,
    target: discord.User | discord.Member,
    moderator: discord.User | discord.Member,
    reason: str,
    colour: int = Config.COLOUR_MOD,
    extra_fields: Optional[dict[str, str]] = None,
) -> discord.Embed:
    """
    Rich embed for a moderation action.

    Parameters
    ----------
    action:
        Human-readable action name, e.g. ``"Ban"`` or ``"Warning"``.
    target:
        The user the action was applied to.
    moderator:
        The staff member who performed the action.
    reason:
        Reason string (may be ``"No reason provided"``).
    colour:
        Override the embed accent colour.
    extra_fields:
        Optional mapping of ``field_name → value`` appended after the
        standard fields, e.g. ``{"Duration": "10m", "Warning ID": "7"}``.
    """
    icon = _ACTION_ICONS.get(action, "🛡️")
    embed = discord.Embed(
        title=f"{icon} {action}",
        colour=colour,
    )
    embed.set_thumbnail(url=target.display_avatar.url)
    embed.add_field(name="Target", value=f"{target.mention} (`{target}`)", inline=True)
    embed.add_field(name="Moderator", value=f"{moderator.mention} (`{moderator}`)", inline=True)
    embed.add_field(name="Reason", value=reason, inline=False)

    if extra_fields:
        for name, value in extra_fields.items():
            embed.add_field(name=name, value=value, inline=True)

    embed.set_footer(text=f"Target ID: {target.id}")
    embed.timestamp = discord.utils.utcnow()
    return embed


# ---------------------------------------------------------------------------
# Warnings list embed
# ---------------------------------------------------------------------------

def warnings_list_embed(
    member: discord.Member,
    rows: list,  # list[aiosqlite.Row]
) -> discord.Embed:
    """
    Display a paginated-style list of warnings for a member.
    Shows up to 10 entries; truncates the list with a note if there are more.
    """
    total = len(rows)
    embed = discord.Embed(
        title=f"⚠️ Warnings for {member}",
        colour=Config.COLOUR_WARNING if total else Config.COLOUR_SUCCESS,
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="Total Warnings", value=str(total), inline=True)
    embed.add_field(name="User ID", value=str(member.id), inline=True)

    if not rows:
        embed.description = "This member has no warnings. ✅"
    else:
        display = rows[:10]
        lines: list[str] = []
        for row in display:
            lines.append(
                f"**#{row['id']}** — {row['reason']}\n"
                f"  *{row['created_at']} UTC*"
            )
        if total > 10:
            lines.append(f"… and {total - 10} more warning(s) not shown.")
        embed.description = "\n\n".join(lines)

    embed.timestamp = discord.utils.utcnow()
    return embed
