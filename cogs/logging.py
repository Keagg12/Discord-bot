"""
cogs/logging.py
===============
Event-driven logging cog.  Listens to Discord gateway events and
forwards structured embeds to the guild's configured log channel.

Logged events
-------------
  • Message edits
  • Message deletes
  • Member joins
  • Member leaves
  • Bans
  • Unbans
  • Role updates (roles added / removed from a member)
  • Timeouts (applied / removed via audit log)

Slash commands
--------------
  /setlogchannel  – configure the log channel
  /logstatus      – show current logging configuration
"""

from __future__ import annotations

import logging
from typing import Optional, Sequence

import discord
from discord import app_commands
from discord.ext import commands

from config import Config
from utils.checks import is_admin
from utils.embeds import success_embed, error_embed

logger = logging.getLogger("logging_cog")


class Logging(commands.Cog, name="Logging"):
    """Structured event logging to a dedicated channel."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @property
    def db(self):
        return self.bot.db

    async def _log_channel(
        self, guild: discord.Guild
    ) -> Optional[discord.TextChannel]:
        """Return the configured log channel for *guild*, or None."""
        cfg = await self.db.get_logging_config(guild.id)
        if cfg["log_channel_id"]:
            ch = guild.get_channel(cfg["log_channel_id"])
            if isinstance(ch, discord.TextChannel):
                return ch
        return None

    async def _send(
        self, guild: discord.Guild, embed: discord.Embed
    ) -> None:
        """Send *embed* to the guild log channel, silently ignoring errors."""
        ch = await self._log_channel(guild)
        if ch is None:
            return
        try:
            await ch.send(embed=embed)
        except discord.HTTPException as exc:
            logger.warning("Failed to send log embed to %s: %s", ch, exc)

    @staticmethod
    def _base_embed(title: str, colour: int) -> discord.Embed:
        embed = discord.Embed(title=title, colour=colour)
        embed.timestamp = discord.utils.utcnow()
        return embed

    # ------------------------------------------------------------------
    # /setlogchannel
    # ------------------------------------------------------------------

    @app_commands.command(
        name="setlogchannel",
        description="Set the channel where moderation logs are posted.",
    )
    @app_commands.describe(channel="The text channel to use for logs")
    @app_commands.default_permissions(administrator=True)
    @is_admin()
    async def setlogchannel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
    ) -> None:
        """Configure the guild's log channel."""
        await interaction.response.defer(ephemeral=True)
        await self.db.set_log_channel(interaction.guild.id, channel.id)
        await interaction.followup.send(
            embed=success_embed(
                f"Log channel set to {channel.mention}.\n"
                "All moderation events will be posted there."
            ),
            ephemeral=True,
        )

    # ------------------------------------------------------------------
    # /logstatus
    # ------------------------------------------------------------------

    @app_commands.command(
        name="logstatus",
        description="View the current logging configuration.",
    )
    @app_commands.default_permissions(manage_guild=True)
    @is_admin()
    async def logstatus(self, interaction: discord.Interaction) -> None:
        """Display an overview of which events are being logged."""
        await interaction.response.defer(ephemeral=True)
        cfg = await self.db.get_logging_config(interaction.guild.id)

        ch = interaction.guild.get_channel(cfg["log_channel_id"]) if cfg["log_channel_id"] else None
        ch_str = ch.mention if ch else "*(not set)*"

        def _tick(val: int) -> str:
            return "✅" if val else "❌"

        embed = discord.Embed(
            title="📋 Logging Configuration",
            colour=Config.COLOUR_INFO,
        )
        embed.add_field(name="Log Channel", value=ch_str, inline=False)
        embed.add_field(
            name="Events",
            value=(
                f"{_tick(cfg['log_message_edit'])} Message Edits\n"
                f"{_tick(cfg['log_message_delete'])} Message Deletes\n"
                f"{_tick(cfg['log_member_join'])} Member Joins\n"
                f"{_tick(cfg['log_member_leave'])} Member Leaves\n"
                f"{_tick(cfg['log_bans'])} Bans / Unbans\n"
                f"{_tick(cfg['log_kicks'])} Kicks\n"
                f"{_tick(cfg['log_timeouts'])} Timeouts\n"
                f"{_tick(cfg['log_warnings'])} Warnings\n"
                f"{_tick(cfg['log_role_updates'])} Role Updates"
            ),
            inline=False,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ------------------------------------------------------------------
    # Message edit
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_message_edit(
        self, before: discord.Message, after: discord.Message
    ) -> None:
        if not after.guild or after.author.bot:
            return
        if before.content == after.content:
            return  # e.g. embed unfurl, not a real edit

        cfg = await self.db.get_logging_config(after.guild.id)
        if not cfg["log_message_edit"]:
            return

        embed = self._base_embed("✏️ Message Edited", Config.COLOUR_INFO)
        embed.set_author(
            name=str(after.author),
            icon_url=after.author.display_avatar.url,
        )
        embed.add_field(name="Author", value=after.author.mention, inline=True)
        embed.add_field(name="Channel", value=after.channel.mention, inline=True)
        embed.add_field(
            name="Before",
            value=before.content[:1024] or "*(empty)*",
            inline=False,
        )
        embed.add_field(
            name="After",
            value=after.content[:1024] or "*(empty)*",
            inline=False,
        )
        embed.add_field(
            name="Jump",
            value=f"[Go to message]({after.jump_url})",
            inline=False,
        )
        embed.set_footer(text=f"User ID: {after.author.id}")
        await self._send(after.guild, embed)

    # ------------------------------------------------------------------
    # Message delete
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        if not message.guild or message.author.bot:
            return

        cfg = await self.db.get_logging_config(message.guild.id)
        if not cfg["log_message_delete"]:
            return

        embed = self._base_embed("🗑️ Message Deleted", Config.COLOUR_ERROR)
        embed.set_author(
            name=str(message.author),
            icon_url=message.author.display_avatar.url,
        )
        embed.add_field(name="Author", value=message.author.mention, inline=True)
        embed.add_field(name="Channel", value=message.channel.mention, inline=True)
        embed.add_field(
            name="Content",
            value=message.content[:1024] or "*(empty or attachment only)*",
            inline=False,
        )
        if message.attachments:
            names = ", ".join(a.filename for a in message.attachments)
            embed.add_field(name="Attachments", value=names, inline=False)
        embed.set_footer(text=f"User ID: {message.author.id}")
        await self._send(message.guild, embed)

    # ------------------------------------------------------------------
    # Member join
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        cfg = await self.db.get_logging_config(member.guild.id)
        if not cfg["log_member_join"]:
            return

        embed = self._base_embed("📥 Member Joined", Config.COLOUR_SUCCESS)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Member", value=member.mention, inline=True)
        embed.add_field(name="Account Created", value=discord.utils.format_dt(member.created_at, "R"), inline=True)
        embed.add_field(name="Member Count", value=str(member.guild.member_count), inline=True)
        embed.set_footer(text=f"User ID: {member.id}")
        await self._send(member.guild, embed)

    # ------------------------------------------------------------------
    # Member leave / kick
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        cfg = await self.db.get_logging_config(member.guild.id)
        if not cfg["log_member_leave"]:
            return

        # Check audit log to detect kicks
        action_label = "📤 Member Left"
        colour = Config.COLOUR_LOG

        try:
            async for entry in member.guild.audit_logs(
                limit=5, action=discord.AuditLogAction.kick
            ):
                if entry.target.id == member.id:
                    action_label = "👢 Member Kicked"
                    colour = Config.COLOUR_WARNING
                    break
        except discord.Forbidden:
            pass

        embed = self._base_embed(action_label, colour)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Member", value=f"{member} ({member.mention})", inline=True)
        embed.add_field(
            name="Joined",
            value=discord.utils.format_dt(member.joined_at, "R") if member.joined_at else "Unknown",
            inline=True,
        )
        roles = [r.mention for r in member.roles if r.name != "@everyone"]
        embed.add_field(
            name="Roles",
            value=", ".join(roles) if roles else "None",
            inline=False,
        )
        embed.set_footer(text=f"User ID: {member.id}")
        await self._send(member.guild, embed)

    # ------------------------------------------------------------------
    # Ban
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User) -> None:
        cfg = await self.db.get_logging_config(guild.id)
        if not cfg["log_bans"]:
            return

        reason = "Unknown"
        moderator = None
        try:
            async for entry in guild.audit_logs(
                limit=5, action=discord.AuditLogAction.ban
            ):
                if entry.target.id == user.id:
                    reason = entry.reason or "No reason provided"
                    moderator = entry.user
                    break
        except discord.Forbidden:
            pass

        embed = self._base_embed("🔨 Member Banned", Config.COLOUR_ERROR)
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name="User", value=f"{user} ({user.mention})", inline=True)
        if moderator:
            embed.add_field(name="Moderator", value=moderator.mention, inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.set_footer(text=f"User ID: {user.id}")
        await self._send(guild, embed)

    # ------------------------------------------------------------------
    # Unban
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User) -> None:
        cfg = await self.db.get_logging_config(guild.id)
        if not cfg["log_bans"]:
            return

        embed = self._base_embed("✅ Member Unbanned", Config.COLOUR_SUCCESS)
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name="User", value=f"{user} ({user.mention})", inline=True)
        embed.set_footer(text=f"User ID: {user.id}")
        await self._send(guild, embed)

    # ------------------------------------------------------------------
    # Role updates
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_member_update(
        self, before: discord.Member, after: discord.Member
    ) -> None:
        cfg = await self.db.get_logging_config(after.guild.id)

        # --- timeout changes ---
        if cfg["log_timeouts"]:
            if before.timed_out_until != after.timed_out_until:
                if after.timed_out_until:
                    embed = self._base_embed("⏱️ Member Timed Out", Config.COLOUR_WARNING)
                    embed.add_field(name="Member", value=after.mention, inline=True)
                    embed.add_field(
                        name="Until",
                        value=discord.utils.format_dt(after.timed_out_until, "F"),
                        inline=True,
                    )
                else:
                    embed = self._base_embed("⏱️ Timeout Removed", Config.COLOUR_SUCCESS)
                    embed.add_field(name="Member", value=after.mention, inline=True)
                embed.set_footer(text=f"User ID: {after.id}")
                await self._send(after.guild, embed)

        # --- role changes ---
        if not cfg["log_role_updates"]:
            return

        added = set(after.roles) - set(before.roles)
        removed = set(before.roles) - set(after.roles)
        if not added and not removed:
            return

        embed = self._base_embed("🎭 Role Update", Config.COLOUR_INFO)
        embed.set_author(
            name=str(after),
            icon_url=after.display_avatar.url,
        )
        embed.add_field(name="Member", value=after.mention, inline=False)
        if added:
            embed.add_field(
                name="Roles Added",
                value=", ".join(r.mention for r in added),
                inline=False,
            )
        if removed:
            embed.add_field(
                name="Roles Removed",
                value=", ".join(r.mention for r in removed),
                inline=False,
            )
        embed.set_footer(text=f"User ID: {after.id}")
        await self._send(after.guild, embed)


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Logging(bot))
