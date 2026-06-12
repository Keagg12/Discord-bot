"""
utils/checks.py
===============
Custom ``app_commands.check`` decorators used across all cogs.

Usage
-----
    from utils.checks import is_moderator, is_admin

    @app_commands.command(...)
    @is_moderator()
    async def my_command(self, interaction): ...
"""

from __future__ import annotations

import discord
from discord import app_commands


def is_moderator():
    """
    Allow the command if the invoker has at least one of the standard
    moderation permissions: ban_members, kick_members, manage_messages,
    moderate_members, or manage_channels.
    Server administrators always pass.
    """
    def predicate(interaction: discord.Interaction) -> bool:
        member: discord.Member = interaction.user  # type: ignore[assignment]
        perms = member.guild_permissions
        return (
            perms.administrator
            or perms.ban_members
            or perms.kick_members
            or perms.manage_messages
            or perms.moderate_members
            or perms.manage_channels
        )

    return app_commands.check(predicate)


def is_admin():
    """Allow only server administrators."""
    def predicate(interaction: discord.Interaction) -> bool:
        member: discord.Member = interaction.user  # type: ignore[assignment]
        return member.guild_permissions.administrator

    return app_commands.check(predicate)


def is_owner():
    """Allow only the guild owner."""
    def predicate(interaction: discord.Interaction) -> bool:
        return interaction.user.id == interaction.guild.owner_id

    return app_commands.check(predicate)
