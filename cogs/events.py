"""
cogs/events.py
==============
Global event handlers that don't belong in a more specific cog.

  • Global app-command error handler
      – permission errors
      – cooldown errors
      – generic / unhandled errors
  • on_guild_join   – create default DB rows, greet server owner
  • on_guild_remove – clean up
"""

from __future__ import annotations

import logging
import traceback

import discord
from discord import app_commands
from discord.ext import commands

from config import Config
from utils.embeds import error_embed, success_embed

logger = logging.getLogger("events")


class Events(commands.Cog, name="Events"):
    """Global gateway event listeners and error handling."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # Attach the global app-command error handler.
        bot.tree.on_error = self._on_app_command_error  # type: ignore[method-assign]

    @property
    def db(self):
        return self.bot.db

    # ------------------------------------------------------------------
    # Global app-command error handler
    # ------------------------------------------------------------------

    async def _on_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        """
        Centralised handler for all slash-command errors.
        Sends an ephemeral user-facing message and logs internally.
        """
        # Unwrap the generic CommandInvokeError wrapper
        original = getattr(error, "original", error)

        # --- Missing bot permissions ---
        if isinstance(original, discord.Forbidden):
            embed = error_embed(
                "I don't have the required permissions to do that.\n"
                "Please check my role's permissions and try again."
            )

        # --- Missing user permissions ---
        elif isinstance(original, app_commands.MissingPermissions):
            perms = ", ".join(
                p.replace("_", " ").title()
                for p in original.missing_permissions
            )
            embed = error_embed(
                f"You are missing the following permission(s) to run this command:\n"
                f"`{perms}`"
            )

        # --- Bot missing permissions ---
        elif isinstance(original, app_commands.BotMissingPermissions):
            perms = ", ".join(
                p.replace("_", " ").title()
                for p in original.missing_permissions
            )
            embed = error_embed(
                f"I am missing the following permission(s):\n`{perms}`"
            )

        # --- Cooldown ---
        elif isinstance(original, app_commands.CommandOnCooldown):
            embed = error_embed(
                f"This command is on cooldown.\n"
                f"Please try again in **{original.retry_after:.1f}s**."
            )

        # --- Command not found (shouldn't happen with slash, but guard anyway) ---
        elif isinstance(original, app_commands.CommandNotFound):
            embed = error_embed("That command doesn't exist.")

        # --- Check failure (custom checks via is_moderator, is_admin) ---
        elif isinstance(original, app_commands.CheckFailure):
            embed = error_embed(
                "You don't have permission to use this command."
            )

        # --- Database / unexpected errors ---
        else:
            logger.error(
                "Unhandled error in /%s: %s",
                interaction.command.name if interaction.command else "unknown",
                "".join(traceback.format_exception(type(original), original, original.__traceback__)),
            )
            embed = error_embed(
                "An unexpected error occurred while processing that command.\n"
                "The issue has been logged. Please try again later."
            )

        # Respond or follow-up depending on whether we already ack'd.
        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except discord.HTTPException:
            pass  # If even the error response fails, give up gracefully.

    # ------------------------------------------------------------------
    # Guild join
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild) -> None:
        """
        When the bot joins a new guild:
          1. Initialise default database rows.
          2. Attempt to DM the owner with a quick-start guide.
        """
        logger.info("Joined guild: %s (ID: %s)", guild.name, guild.id)

        # Seed guild config and logging config rows.
        await self.db.get_guild_config(guild.id)
        await self.db.get_logging_config(guild.id)

        # Try to DM the server owner.
        if guild.owner:
            embed = discord.Embed(
                title=f"👋 Thanks for adding me to **{guild.name}**!",
                colour=Config.COLOUR_SUCCESS,
                description=(
                    "Here's how to get started:\n\n"
                    "1. Use `/setlogchannel #channel` to configure a log channel.\n"
                    "2. Use `/logstatus` to verify logging is set up.\n"
                    "3. Grant me a role with `Ban Members`, `Kick Members`, "
                    "`Moderate Members`, and `Manage Messages`.\n"
                    "4. Type `/help` to see all available commands.\n\n"
                    "All auto-mod features are **enabled by default**."
                ),
            )
            embed.set_footer(text=f"Bot v{Config.BOT_VERSION}")
            try:
                await guild.owner.send(embed=embed)
            except discord.HTTPException:
                pass  # Owner DMs may be closed.

    # ------------------------------------------------------------------
    # Guild remove
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild) -> None:
        """Log when the bot is removed from a guild."""
        logger.info("Removed from guild: %s (ID: %s)", guild.name, guild.id)
        # We keep the database rows for audit purposes.
        # They can be cleared manually if needed.

    # ------------------------------------------------------------------
    # Command error (prefix commands – fallback)
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_command_error(
        self, ctx: commands.Context, error: commands.CommandError
    ) -> None:
        """Handle any legacy prefix-command errors."""
        if isinstance(error, commands.CommandNotFound):
            return  # Silently ignore unknown prefix commands.
        if isinstance(error, commands.MissingPermissions):
            await ctx.send(
                embed=error_embed("You don't have permission to run that command."),
                delete_after=10,
            )
        else:
            logger.error("Prefix command error: %s", error, exc_info=True)


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Events(bot))
