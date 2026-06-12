"""
cogs/moderation.py
==================
Slash-command cog for all manual moderation actions:
  /ban  /unban  /kick  /timeout  /untimeout
  /warn  /warnings  /removewarn  /purge
  /lock  /unlock  /slowmode  /nickname
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from config import Config
from utils.checks import is_moderator, is_admin
from utils.embeds import (
    success_embed,
    error_embed,
    warning_embed,
    mod_action_embed,
    warnings_list_embed,
)
from utils.permissions import require_hierarchy

logger = logging.getLogger("moderation")


class Moderation(commands.Cog, name="Moderation"):
    """All manual moderation commands."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @property
    def db(self):
        return self.bot.db

    async def _get_log_channel(
        self, guild: discord.Guild
    ) -> Optional[discord.TextChannel]:
        """Return the configured logging channel or None."""
        cfg = await self.db.get_logging_config(guild.id)
        if cfg["log_channel_id"]:
            return guild.get_channel(cfg["log_channel_id"])
        return None

    async def _send_log(
        self, guild: discord.Guild, embed: discord.Embed
    ) -> None:
        """Send an embed to the guild's log channel if configured."""
        ch = await self._get_log_channel(guild)
        if ch:
            try:
                await ch.send(embed=embed)
            except discord.Forbidden:
                logger.warning("Cannot send to log channel %s", ch.id)

    # ------------------------------------------------------------------
    # /ban
    # ------------------------------------------------------------------

    @app_commands.command(name="ban", description="Ban a member from the server.")
    @app_commands.describe(
        member="The member to ban",
        reason="Reason for the ban",
        delete_days="Days of message history to delete (0-7)",
    )
    @app_commands.default_permissions(ban_members=True)
    @is_moderator()
    async def ban(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: Optional[str] = "No reason provided",
        delete_days: app_commands.Range[int, 0, 7] = 0,
    ) -> None:
        """Ban a server member."""
        await interaction.response.defer(ephemeral=False)

        if not await require_hierarchy(interaction, member):
            return

        try:
            await member.send(
                embed=error_embed(
                    f"You have been **banned** from **{interaction.guild.name}**.\n"
                    f"**Reason:** {reason}"
                )
            )
        except discord.HTTPException:
            pass  # DMs may be closed

        await member.ban(
            reason=f"{interaction.user} | {reason}",
            delete_message_days=delete_days,
        )
        await self.db.log_action(
            interaction.guild.id, member.id,
            interaction.user.id, "ban", reason
        )

        embed = mod_action_embed(
            action="Ban",
            target=member,
            moderator=interaction.user,
            reason=reason,
            colour=Config.COLOUR_ERROR,
        )
        await interaction.followup.send(embed=embed)
        await self._send_log(interaction.guild, embed)

    # ------------------------------------------------------------------
    # /unban
    # ------------------------------------------------------------------

    @app_commands.command(name="unban", description="Unban a user by ID or username#discriminator.")
    @app_commands.describe(
        user_id="The Discord user ID to unban",
        reason="Reason for the unban",
    )
    @app_commands.default_permissions(ban_members=True)
    @is_moderator()
    async def unban(
        self,
        interaction: discord.Interaction,
        user_id: str,
        reason: Optional[str] = "No reason provided",
    ) -> None:
        """Unban a previously banned user."""
        await interaction.response.defer()

        try:
            uid = int(user_id)
        except ValueError:
            await interaction.followup.send(
                embed=error_embed("Please provide a valid numeric user ID."),
                ephemeral=True,
            )
            return

        user = discord.Object(id=uid)
        try:
            await interaction.guild.unban(user, reason=f"{interaction.user} | {reason}")
        except discord.NotFound:
            await interaction.followup.send(
                embed=error_embed("That user is not banned or the ID is invalid."),
                ephemeral=True,
            )
            return

        fetched = await self.bot.fetch_user(uid)
        await self.db.log_action(
            interaction.guild.id, uid, interaction.user.id, "unban", reason
        )
        embed = mod_action_embed(
            action="Unban",
            target=fetched,
            moderator=interaction.user,
            reason=reason,
            colour=Config.COLOUR_SUCCESS,
        )
        await interaction.followup.send(embed=embed)
        await self._send_log(interaction.guild, embed)

    # ------------------------------------------------------------------
    # /kick
    # ------------------------------------------------------------------

    @app_commands.command(name="kick", description="Kick a member from the server.")
    @app_commands.describe(
        member="The member to kick",
        reason="Reason for the kick",
    )
    @app_commands.default_permissions(kick_members=True)
    @is_moderator()
    async def kick(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: Optional[str] = "No reason provided",
    ) -> None:
        """Kick a server member."""
        await interaction.response.defer()

        if not await require_hierarchy(interaction, member):
            return

        try:
            await member.send(
                embed=warning_embed(
                    f"You have been **kicked** from **{interaction.guild.name}**.\n"
                    f"**Reason:** {reason}"
                )
            )
        except discord.HTTPException:
            pass

        await member.kick(reason=f"{interaction.user} | {reason}")
        await self.db.log_action(
            interaction.guild.id, member.id,
            interaction.user.id, "kick", reason
        )

        embed = mod_action_embed(
            action="Kick",
            target=member,
            moderator=interaction.user,
            reason=reason,
            colour=Config.COLOUR_WARNING,
        )
        await interaction.followup.send(embed=embed)
        await self._send_log(interaction.guild, embed)

    # ------------------------------------------------------------------
    # /timeout
    # ------------------------------------------------------------------

    @app_commands.command(
        name="timeout",
        description="Timeout (mute) a member for a specified duration.",
    )
    @app_commands.describe(
        member="The member to timeout",
        duration="Duration in minutes (1–40320)",
        reason="Reason for the timeout",
    )
    @app_commands.default_permissions(moderate_members=True)
    @is_moderator()
    async def timeout(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        duration: app_commands.Range[int, 1, 40320],
        reason: Optional[str] = "No reason provided",
    ) -> None:
        """Apply a Discord timeout to a member."""
        await interaction.response.defer()

        if not await require_hierarchy(interaction, member):
            return

        until = discord.utils.utcnow() + timedelta(minutes=duration)
        await member.timeout(until, reason=f"{interaction.user} | {reason}")
        await self.db.log_action(
            interaction.guild.id, member.id,
            interaction.user.id, "timeout", reason,
            duration=f"{duration}m",
        )

        readable = _fmt_duration(duration)
        embed = mod_action_embed(
            action="Timeout",
            target=member,
            moderator=interaction.user,
            reason=reason,
            colour=Config.COLOUR_WARNING,
            extra_fields={"Duration": readable},
        )
        await interaction.followup.send(embed=embed)
        await self._send_log(interaction.guild, embed)

    # ------------------------------------------------------------------
    # /untimeout
    # ------------------------------------------------------------------

    @app_commands.command(name="untimeout", description="Remove a timeout from a member.")
    @app_commands.describe(
        member="The member to untimeout",
        reason="Reason for removing the timeout",
    )
    @app_commands.default_permissions(moderate_members=True)
    @is_moderator()
    async def untimeout(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: Optional[str] = "No reason provided",
    ) -> None:
        """Remove an active timeout from a member."""
        await interaction.response.defer()

        if member.timed_out_until is None:
            await interaction.followup.send(
                embed=error_embed(f"{member.mention} is not currently timed out."),
                ephemeral=True,
            )
            return

        await member.timeout(None, reason=f"{interaction.user} | {reason}")
        await self.db.log_action(
            interaction.guild.id, member.id,
            interaction.user.id, "untimeout", reason
        )

        embed = mod_action_embed(
            action="Untimeout",
            target=member,
            moderator=interaction.user,
            reason=reason,
            colour=Config.COLOUR_SUCCESS,
        )
        await interaction.followup.send(embed=embed)
        await self._send_log(interaction.guild, embed)

    # ------------------------------------------------------------------
    # /warn
    # ------------------------------------------------------------------

    @app_commands.command(name="warn", description="Issue a formal warning to a member.")
    @app_commands.describe(
        member="The member to warn",
        reason="Reason for the warning",
    )
    @app_commands.default_permissions(manage_messages=True)
    @is_moderator()
    async def warn(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str,
    ) -> None:
        """Issue a warning and optionally escalate if the threshold is met."""
        await interaction.response.defer()

        if not await require_hierarchy(interaction, member):
            return

        warn_id = await self.db.add_warning(
            interaction.guild.id, member.id,
            interaction.user.id, reason
        )
        await self.db.log_action(
            interaction.guild.id, member.id,
            interaction.user.id, "warn", reason
        )

        total = await self.db.count_warnings(interaction.guild.id, member.id)

        try:
            await member.send(
                embed=warning_embed(
                    f"You have received a warning in **{interaction.guild.name}**.\n"
                    f"**Reason:** {reason}\n"
                    f"**Total warnings:** {total}"
                )
            )
        except discord.HTTPException:
            pass

        embed = mod_action_embed(
            action="Warning",
            target=member,
            moderator=interaction.user,
            reason=reason,
            colour=Config.COLOUR_WARNING,
            extra_fields={"Warning ID": str(warn_id), "Total Warnings": str(total)},
        )
        await interaction.followup.send(embed=embed)
        await self._send_log(interaction.guild, embed)

        # Escalation
        cfg = await self.db.get_guild_config(interaction.guild.id)
        threshold = cfg["warn_threshold"]
        action = cfg["warn_action"]
        if total >= threshold:
            await self._escalate_warn(
                interaction, member, total, action, reason
            )

    async def _escalate_warn(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        total: int,
        action: str,
        reason: str,
    ) -> None:
        """Perform configured escalation action when warning threshold is hit."""
        esc_reason = f"Automatic action: reached {total} warnings."
        try:
            if action == "timeout":
                until = discord.utils.utcnow() + timedelta(hours=24)
                await member.timeout(until, reason=esc_reason)
            elif action == "kick":
                await member.kick(reason=esc_reason)
            elif action == "ban":
                await member.ban(reason=esc_reason)
        except discord.Forbidden:
            logger.warning("Could not escalate warn action %s on %s", action, member)

    # ------------------------------------------------------------------
    # /warnings
    # ------------------------------------------------------------------

    @app_commands.command(name="warnings", description="List all warnings for a member.")
    @app_commands.describe(member="The member to look up")
    @app_commands.default_permissions(manage_messages=True)
    @is_moderator()
    async def warnings(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
    ) -> None:
        """Display a paginated list of a member's warnings."""
        await interaction.response.defer()
        rows = await self.db.get_warnings(interaction.guild.id, member.id)
        embed = warnings_list_embed(member, rows)
        await interaction.followup.send(embed=embed)

    # ------------------------------------------------------------------
    # /removewarn
    # ------------------------------------------------------------------

    @app_commands.command(name="removewarn", description="Remove a specific warning by ID.")
    @app_commands.describe(
        warning_id="The ID of the warning to remove",
    )
    @app_commands.default_permissions(manage_messages=True)
    @is_moderator()
    async def removewarn(
        self,
        interaction: discord.Interaction,
        warning_id: int,
    ) -> None:
        """Delete a specific warning record."""
        await interaction.response.defer()
        deleted = await self.db.remove_warning(warning_id, interaction.guild.id)
        if deleted:
            await interaction.followup.send(
                embed=success_embed(f"Warning **#{warning_id}** has been removed.")
            )
        else:
            await interaction.followup.send(
                embed=error_embed(
                    f"No warning with ID **#{warning_id}** found in this server."
                ),
                ephemeral=True,
            )

    # ------------------------------------------------------------------
    # /purge
    # ------------------------------------------------------------------

    @app_commands.command(name="purge", description="Bulk-delete messages in this channel.")
    @app_commands.describe(
        amount="Number of messages to delete (1–500)",
        member="Only delete messages from this member (optional)",
    )
    @app_commands.default_permissions(manage_messages=True)
    @is_moderator()
    async def purge(
        self,
        interaction: discord.Interaction,
        amount: app_commands.Range[int, 1, 500],
        member: Optional[discord.Member] = None,
    ) -> None:
        """Bulk-delete recent messages, optionally filtered by author."""
        await interaction.response.defer(ephemeral=True)

        check = (lambda m: m.author == member) if member else None
        deleted = await interaction.channel.purge(limit=amount, check=check)

        who = f" from {member.mention}" if member else ""
        await interaction.followup.send(
            embed=success_embed(
                f"Deleted **{len(deleted)}** message(s){who}."
            ),
            ephemeral=True,
        )
        await self.db.log_action(
            interaction.guild.id,
            member.id if member else interaction.user.id,
            interaction.user.id,
            "purge",
            f"Deleted {len(deleted)} messages{who}",
        )

    # ------------------------------------------------------------------
    # /lock
    # ------------------------------------------------------------------

    @app_commands.command(name="lock", description="Lock the current channel (deny @everyone from sending).")
    @app_commands.describe(reason="Reason for locking the channel")
    @app_commands.default_permissions(manage_channels=True)
    @is_moderator()
    async def lock(
        self,
        interaction: discord.Interaction,
        reason: Optional[str] = "No reason provided",
    ) -> None:
        """Deny the @everyone role from sending messages in this channel."""
        await interaction.response.defer()
        everyone = interaction.guild.default_role
        overwrite = interaction.channel.overwrites_for(everyone)
        overwrite.send_messages = False
        await interaction.channel.set_permissions(
            everyone, overwrite=overwrite,
            reason=f"{interaction.user} | {reason}"
        )
        await interaction.followup.send(
            embed=success_embed(f"🔒 Channel locked. **Reason:** {reason}")
        )

    # ------------------------------------------------------------------
    # /unlock
    # ------------------------------------------------------------------

    @app_commands.command(name="unlock", description="Unlock the current channel.")
    @app_commands.describe(reason="Reason for unlocking the channel")
    @app_commands.default_permissions(manage_channels=True)
    @is_moderator()
    async def unlock(
        self,
        interaction: discord.Interaction,
        reason: Optional[str] = "No reason provided",
    ) -> None:
        """Restore @everyone's ability to send messages."""
        await interaction.response.defer()
        everyone = interaction.guild.default_role
        overwrite = interaction.channel.overwrites_for(everyone)
        overwrite.send_messages = None   # reset to inherited
        await interaction.channel.set_permissions(
            everyone, overwrite=overwrite,
            reason=f"{interaction.user} | {reason}"
        )
        await interaction.followup.send(
            embed=success_embed(f"🔓 Channel unlocked. **Reason:** {reason}")
        )

    # ------------------------------------------------------------------
    # /slowmode
    # ------------------------------------------------------------------

    @app_commands.command(name="slowmode", description="Set the slowmode delay for this channel.")
    @app_commands.describe(
        seconds="Delay in seconds (0 to disable, max 21600)",
    )
    @app_commands.default_permissions(manage_channels=True)
    @is_moderator()
    async def slowmode(
        self,
        interaction: discord.Interaction,
        seconds: app_commands.Range[int, 0, 21600],
    ) -> None:
        """Update the channel slowmode delay."""
        await interaction.response.defer()
        await interaction.channel.edit(slowmode_delay=seconds)
        msg = (
            f"Slowmode set to **{seconds}s** in {interaction.channel.mention}."
            if seconds > 0
            else f"Slowmode disabled in {interaction.channel.mention}."
        )
        await interaction.followup.send(embed=success_embed(msg))

    # ------------------------------------------------------------------
    # /nickname
    # ------------------------------------------------------------------

    @app_commands.command(name="nickname", description="Change or reset a member's server nickname.")
    @app_commands.describe(
        member="The member whose nickname to change",
        nickname="New nickname (leave blank to reset)",
    )
    @app_commands.default_permissions(manage_nicknames=True)
    @is_moderator()
    async def nickname(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        nickname: Optional[str] = None,
    ) -> None:
        """Set or clear a member's nickname."""
        await interaction.response.defer()

        if not await require_hierarchy(interaction, member):
            return

        old_nick = member.display_name
        try:
            await member.edit(nick=nickname)
        except discord.Forbidden:
            await interaction.followup.send(
                embed=error_embed("I don't have permission to change that member's nickname."),
                ephemeral=True,
            )
            return

        if nickname:
            msg = f"Changed **{old_nick}**'s nickname to **{nickname}**."
        else:
            msg = f"Reset **{old_nick}**'s nickname."

        await interaction.followup.send(embed=success_embed(msg))


# ---------------------------------------------------------------------------
# Utility: format minutes into a human-readable string
# ---------------------------------------------------------------------------

def _fmt_duration(minutes: int) -> str:
    if minutes < 60:
        return f"{minutes} minute(s)"
    hours, mins = divmod(minutes, 60)
    if hours < 24:
        return f"{hours}h {mins}m" if mins else f"{hours} hour(s)"
    days, hrs = divmod(hours, 24)
    return f"{days}d {hrs}h" if hrs else f"{days} day(s)"


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

async def setup(bot: commands.Bot) -> None:
    """Called by bot.load_extension."""
    await bot.add_cog(Moderation(bot))
