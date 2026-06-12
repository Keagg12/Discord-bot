"""
cogs/utility.py
===============
General-purpose slash commands that any member can use.

Commands
--------
  /ping        – bot latency
  /userinfo    – detailed member card
  /serverinfo  – guild overview
  /avatar      – display a member's avatar
  /botstats    – runtime statistics
  /help        – dynamic command listing
"""

from __future__ import annotations

import platform
import time
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from config import Config

_START_TIME = time.time()


class Utility(commands.Cog, name="Utility"):
    """Informational commands open to all members."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ------------------------------------------------------------------
    # /ping
    # ------------------------------------------------------------------

    @app_commands.command(name="ping", description="Check the bot's response latency.")
    async def ping(self, interaction: discord.Interaction) -> None:
        """Returns the WebSocket heartbeat latency."""
        latency_ms = round(self.bot.latency * 1000)
        colour = (
            Config.COLOUR_SUCCESS if latency_ms < 100
            else Config.COLOUR_WARNING if latency_ms < 250
            else Config.COLOUR_ERROR
        )
        embed = discord.Embed(
            title="🏓 Pong!",
            description=f"WebSocket latency: **{latency_ms} ms**",
            colour=colour,
        )
        await interaction.response.send_message(embed=embed)

    # ------------------------------------------------------------------
    # /userinfo
    # ------------------------------------------------------------------

    @app_commands.command(name="userinfo", description="View detailed information about a member.")
    @app_commands.describe(member="The member to inspect (defaults to yourself)")
    async def userinfo(
        self,
        interaction: discord.Interaction,
        member: Optional[discord.Member] = None,
    ) -> None:
        """Display a rich profile card for a guild member."""
        target: discord.Member = member or interaction.user  # type: ignore[assignment]

        roles = [r.mention for r in target.roles if r.name != "@everyone"]
        roles_str = ", ".join(roles) if roles else "None"
        if len(roles_str) > 1024:
            roles_str = roles_str[:1021] + "…"

        status_map = {
            discord.Status.online: "🟢 Online",
            discord.Status.idle: "🌙 Idle",
            discord.Status.dnd: "🔴 Do Not Disturb",
            discord.Status.offline: "⚫ Offline",
        }
        status = status_map.get(target.status, "Unknown")

        badges: list[str] = []
        flags = target.public_flags
        if flags.staff:
            badges.append("Discord Staff")
        if flags.partner:
            badges.append("Partnered Server Owner")
        if flags.hypesquad:
            badges.append("HypeSquad Events")
        if flags.bug_hunter:
            badges.append("Bug Hunter")
        if flags.verified_bot_developer:
            badges.append("Verified Bot Dev")
        if flags.early_supporter:
            badges.append("Early Supporter")
        badges_str = ", ".join(badges) if badges else "None"

        embed = discord.Embed(
            title=f"👤 {target}",
            colour=target.colour if target.colour.value else Config.COLOUR_INFO,
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="Display Name", value=target.display_name, inline=True)
        embed.add_field(name="ID", value=str(target.id), inline=True)
        embed.add_field(name="Bot", value="Yes" if target.bot else "No", inline=True)
        embed.add_field(
            name="Account Created",
            value=discord.utils.format_dt(target.created_at, "F"),
            inline=True,
        )
        embed.add_field(
            name="Joined Server",
            value=discord.utils.format_dt(target.joined_at, "F") if target.joined_at else "Unknown",
            inline=True,
        )
        embed.add_field(name="Status", value=status, inline=True)
        embed.add_field(name="Badges", value=badges_str, inline=False)
        embed.add_field(
            name=f"Roles ({len(roles)})",
            value=roles_str,
            inline=False,
        )
        embed.set_footer(text=f"Requested by {interaction.user}")
        embed.timestamp = discord.utils.utcnow()
        await interaction.response.send_message(embed=embed)

    # ------------------------------------------------------------------
    # /serverinfo
    # ------------------------------------------------------------------

    @app_commands.command(name="serverinfo", description="View information about this server.")
    async def serverinfo(self, interaction: discord.Interaction) -> None:
        """Display a summary card for the current guild."""
        guild = interaction.guild

        # Verification level string
        vl_map = {
            discord.VerificationLevel.none: "None",
            discord.VerificationLevel.low: "Low",
            discord.VerificationLevel.medium: "Medium",
            discord.VerificationLevel.high: "High",
            discord.VerificationLevel.highest: "Highest",
        }
        vl = vl_map.get(guild.verification_level, "Unknown")

        text_ch = sum(isinstance(c, discord.TextChannel) for c in guild.channels)
        voice_ch = sum(isinstance(c, discord.VoiceChannel) for c in guild.channels)

        bots = sum(1 for m in guild.members if m.bot)
        humans = guild.member_count - bots

        embed = discord.Embed(
            title=f"🏰 {guild.name}",
            colour=Config.COLOUR_INFO,
        )
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        embed.add_field(name="Owner", value=guild.owner.mention if guild.owner else "Unknown", inline=True)
        embed.add_field(name="ID", value=str(guild.id), inline=True)
        embed.add_field(
            name="Created",
            value=discord.utils.format_dt(guild.created_at, "F"),
            inline=True,
        )
        embed.add_field(name="Members", value=f"👥 {guild.member_count} total\n👤 {humans} humans\n🤖 {bots} bots", inline=True)
        embed.add_field(name="Channels", value=f"💬 {text_ch} text\n🔊 {voice_ch} voice", inline=True)
        embed.add_field(name="Roles", value=str(len(guild.roles)), inline=True)
        embed.add_field(name="Verification", value=vl, inline=True)
        embed.add_field(name="Boost Level", value=f"Level {guild.premium_tier} ({guild.premium_subscription_count} boosts)", inline=True)
        embed.add_field(name="Emoji Slots", value=f"{len(guild.emojis)}/{guild.emoji_limit}", inline=True)
        embed.set_footer(text=f"Requested by {interaction.user}")
        embed.timestamp = discord.utils.utcnow()
        await interaction.response.send_message(embed=embed)

    # ------------------------------------------------------------------
    # /avatar
    # ------------------------------------------------------------------

    @app_commands.command(name="avatar", description="Display a member's avatar in full size.")
    @app_commands.describe(member="The member whose avatar to show (defaults to yourself)")
    async def avatar(
        self,
        interaction: discord.Interaction,
        member: Optional[discord.Member] = None,
    ) -> None:
        """Show a full-size avatar image."""
        target: discord.Member = member or interaction.user  # type: ignore[assignment]

        embed = discord.Embed(
            title=f"🖼️ {target.display_name}'s Avatar",
            colour=Config.COLOUR_INFO,
        )
        embed.set_image(url=target.display_avatar.with_size(1024).url)
        embed.add_field(
            name="Links",
            value=(
                f"[PNG]({target.display_avatar.with_format('png').url}) | "
                f"[JPG]({target.display_avatar.with_format('jpg').url}) | "
                f"[WEBP]({target.display_avatar.with_format('webp').url})"
            ),
        )
        await interaction.response.send_message(embed=embed)

    # ------------------------------------------------------------------
    # /botstats
    # ------------------------------------------------------------------

    @app_commands.command(name="botstats", description="View runtime statistics for the bot.")
    async def botstats(self, interaction: discord.Interaction) -> None:
        """Display memory usage, uptime, and other runtime details."""
        import os, sys

        uptime_s = int(time.time() - _START_TIME)
        hours, remainder = divmod(uptime_s, 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime_str = f"{hours}h {minutes}m {seconds}s"

        try:
            import psutil
            proc = psutil.Process(os.getpid())
            mem_mb = proc.memory_info().rss / (1024 * 1024)
            mem_str = f"{mem_mb:.1f} MB"
        except ImportError:
            mem_str = "N/A (psutil not installed)"

        total_commands = sum(
            1 for cmd in self.bot.tree.get_commands()
        )

        embed = discord.Embed(
            title=f"🤖 {self.bot.user.name} – Stats",
            colour=Config.COLOUR_MOD,
        )
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        embed.add_field(name="Version", value=Config.BOT_VERSION, inline=True)
        embed.add_field(name="discord.py", value=discord.__version__, inline=True)
        embed.add_field(name="Python", value=platform.python_version(), inline=True)
        embed.add_field(name="Uptime", value=uptime_str, inline=True)
        embed.add_field(name="Memory", value=mem_str, inline=True)
        embed.add_field(name="Latency", value=f"{round(self.bot.latency * 1000)} ms", inline=True)
        embed.add_field(name="Guilds", value=str(len(self.bot.guilds)), inline=True)
        embed.add_field(name="Slash Commands", value=str(total_commands), inline=True)
        embed.add_field(name="OS", value=platform.system(), inline=True)
        embed.timestamp = discord.utils.utcnow()
        await interaction.response.send_message(embed=embed)

    # ------------------------------------------------------------------
    # /help
    # ------------------------------------------------------------------

    @app_commands.command(name="help", description="Browse all available bot commands.")
    @app_commands.describe(category="Filter commands by category (optional)")
    @app_commands.choices(category=[
        app_commands.Choice(name="Moderation", value="moderation"),
        app_commands.Choice(name="Auto-Mod",   value="automod"),
        app_commands.Choice(name="Logging",    value="logging"),
        app_commands.Choice(name="Utility",    value="utility"),
    ])
    async def help(
        self,
        interaction: discord.Interaction,
        category: Optional[str] = None,
    ) -> None:
        """Interactive help listing all slash commands."""
        embed = discord.Embed(
            title="📖 Bot Help",
            colour=Config.COLOUR_INFO,
            description=(
                "Use the slash command menu (`/`) to auto-complete any command.\n"
                "All commands require the relevant Discord permissions."
            ),
        )
        if self.bot.user.display_avatar:
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)

        sections = {
            "moderation": (
                "🔨 **Moderation**",
                (
                    "`/ban` `/unban` `/kick` `/timeout` `/untimeout`\n"
                    "`/warn` `/warnings` `/removewarn` `/purge`\n"
                    "`/lock` `/unlock` `/slowmode` `/nickname`"
                ),
            ),
            "automod": (
                "🤖 **Auto-Mod**",
                (
                    "Automatically enforces:\n"
                    "• Anti-spam  • Anti-invite  • Anti-scam\n"
                    "• Anti-mass-mention  • Anti-caps  • Anti-emoji-spam\n"
                    "• Bad-word filter\n"
                    "*(Configured via guild_config in the database)*"
                ),
            ),
            "logging": (
                "📋 **Logging**",
                (
                    "`/setlogchannel` — set the log output channel\n"
                    "`/logstatus` — view current logging config\n\n"
                    "Auto-logs: edits, deletes, joins, leaves,\n"
                    "bans, kicks, timeouts, role changes"
                ),
            ),
            "utility": (
                "🛠️ **Utility**",
                (
                    "`/ping` `/userinfo` `/serverinfo`\n"
                    "`/avatar` `/botstats` `/help`"
                ),
            ),
        }

        # Show all sections or just the requested one.
        targets = [category] if category and category in sections else list(sections.keys())
        for key in targets:
            title, value = sections[key]
            embed.add_field(name=title, value=value, inline=False)

        embed.set_footer(
            text=f"Bot v{Config.BOT_VERSION} | {len(self.bot.guilds)} server(s)"
        )
        embed.timestamp = discord.utils.utcnow()
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Utility(bot))
