"""
Discord Moderation Bot - Entry Point
=====================================
Initialises the bot, loads all cogs, and starts the event loop.
"""

import asyncio
import os
import sys

import discord
from discord.ext import commands
from dotenv import load_dotenv

from config import Config
from database.database import Database
from utils.logger import setup_logger

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

load_dotenv()
logger = setup_logger("main")


class ModerationBot(commands.Bot):
    """
    Custom Bot subclass that owns the shared Database instance and handles
    cog loading / startup lifecycle.
    """

    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        intents.guilds = True
        intents.bans = True
        intents.moderation = True

        super().__init__(
            command_prefix=Config.PREFIX,
            intents=intents,
            help_command=None,          # we supply our own /help slash command
            case_insensitive=True,
        )

        self.db: Database = Database()

    # ------------------------------------------------------------------
    # Lifecycle hooks
    # ------------------------------------------------------------------

    async def setup_hook(self) -> None:
        """Called once before the bot connects – ideal for async initialisation."""
        await self.db.initialise()
        logger.info("Database initialised.")

        await self._load_cogs()

        # Sync application (slash) commands globally.
        synced = await self.tree.sync()
        logger.info("Synced %d application command(s).", len(synced))

    async def on_ready(self) -> None:
        """Fired when the bot has connected and cached all guilds."""
        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name=f"{len(self.guilds)} servers | /help",
        )
        await self.change_presence(status=discord.Status.online, activity=activity)
        logger.info(
            "Logged in as %s (ID: %s). Watching %d guild(s).",
            self.user,
            self.user.id,
            len(self.guilds),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _load_cogs(self) -> None:
        """Dynamically load every cog listed in Config.COGS."""
        for cog in Config.COGS:
            try:
                await self.load_extension(cog)
                logger.info("Loaded cog: %s", cog)
            except Exception as exc:
                logger.error("Failed to load cog %s: %s", cog, exc, exc_info=True)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main() -> None:
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        logger.critical("DISCORD_TOKEN is not set in the environment / .env file.")
        sys.exit(1)

    bot = ModerationBot()

    async with bot:
        await bot.start(token)


if __name__ == "__main__":
    asyncio.run(main())
