"""
utils/permissions.py
====================
Role-hierarchy helpers used by moderation commands to prevent
moderators from actioning users who outrank them.

Functions
---------
require_hierarchy(interaction, target)
    Sends an error and returns False if the moderator's top role is
    not above the target's top role (or if the target is the guild owner).
    Returns True when the action should proceed.

can_moderate(moderator, target)
    Pure predicate — no Discord side-effects.
"""

from __future__ import annotations

import discord

from utils.embeds import error_embed


async def require_hierarchy(
    interaction: discord.Interaction,
    target: discord.Member,
) -> bool:
    """
    Guard a moderation action against the Discord role hierarchy.

    Returns
    -------
    bool
        ``True``  → hierarchy check passed; proceed with the action.
        ``False`` → hierarchy check failed; an error reply has been sent.
    """
    guild: discord.Guild = interaction.guild
    moderator: discord.Member = interaction.user  # type: ignore[assignment]

    # Cannot action the guild owner.
    if target.id == guild.owner_id:
        await _respond(
            interaction,
            error_embed("You cannot perform moderation actions on the server owner."),
        )
        return False

    # Cannot action yourself.
    if target.id == moderator.id:
        await _respond(
            interaction,
            error_embed("You cannot perform moderation actions on yourself."),
        )
        return False

    # Cannot action the bot itself.
    if target.id == guild.me.id:
        await _respond(
            interaction,
            error_embed("I cannot perform moderation actions on myself."),
        )
        return False

    # The bot's own top role must be above the target.
    if guild.me.top_role <= target.top_role:
        await _respond(
            interaction,
            error_embed(
                f"My highest role is not above {target.mention}'s highest role.\n"
                "Please move my role higher in the server settings."
            ),
        )
        return False

    # The moderator's top role must be above the target's top role.
    # Admins bypass this because their effective permission level is always highest.
    if not moderator.guild_permissions.administrator:
        if moderator.top_role <= target.top_role:
            await _respond(
                interaction,
                error_embed(
                    f"Your highest role is not above {target.mention}'s highest role.\n"
                    "You cannot moderate someone at or above your role level."
                ),
            )
            return False

    return True


def can_moderate(moderator: discord.Member, target: discord.Member) -> bool:
    """
    Lightweight, synchronous hierarchy check with no Discord side-effects.

    Parameters
    ----------
    moderator:
        The staff member attempting the action.
    target:
        The member being actioned.

    Returns
    -------
    bool
        True if the moderator outranks the target and the bot can act.
    """
    guild = moderator.guild

    if target.id == guild.owner_id:
        return False
    if target.id == moderator.id:
        return False
    if guild.me.top_role <= target.top_role:
        return False
    if not moderator.guild_permissions.administrator:
        if moderator.top_role <= target.top_role:
            return False
    return True


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

async def _respond(
    interaction: discord.Interaction, embed: discord.Embed
) -> None:
    """Send an ephemeral embed, handling whether we've already responded."""
    try:
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)
    except discord.HTTPException:
        pass
