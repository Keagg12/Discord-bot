"""
database/database.py
====================
Async SQLite wrapper built on aiosqlite.

Tables
------
warnings          – per-user warning records
moderation_actions – audit log of every mod action
guild_config      – per-guild bot settings
logging_config    – per-guild logging channel settings
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

import aiosqlite

from config import Config

logger = logging.getLogger("database")


class Database:
    """
    Singleton-style async database manager.
    Call ``await db.initialise()`` once before using any other method.
    """

    def __init__(self) -> None:
        self._path: str = Config.DB_PATH
        self._conn: Optional[aiosqlite.Connection] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialise(self) -> None:
        """Open the connection and create tables if they don't exist."""
        self._conn = await aiosqlite.connect(self._path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL;")
        await self._conn.execute("PRAGMA foreign_keys=ON;")
        await self._create_tables()
        await self._conn.commit()
        logger.info("Database connected: %s", self._path)

    async def close(self) -> None:
        """Gracefully close the database connection."""
        if self._conn:
            await self._conn.close()
            logger.info("Database connection closed.")

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    async def _create_tables(self) -> None:
        """Create all required tables (idempotent)."""
        statements = [
            # ---- warnings ------------------------------------------------
            """
            CREATE TABLE IF NOT EXISTS warnings (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id    INTEGER NOT NULL,
                user_id     INTEGER NOT NULL,
                moderator_id INTEGER NOT NULL,
                reason      TEXT    NOT NULL,
                created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
            );
            """,
            # ---- moderation_actions --------------------------------------
            """
            CREATE TABLE IF NOT EXISTS moderation_actions (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id     INTEGER NOT NULL,
                user_id      INTEGER NOT NULL,
                moderator_id INTEGER NOT NULL,
                action       TEXT    NOT NULL,
                reason       TEXT,
                duration     TEXT,
                created_at   TEXT    NOT NULL DEFAULT (datetime('now'))
            );
            """,
            # ---- guild_config --------------------------------------------
            """
            CREATE TABLE IF NOT EXISTS guild_config (
                guild_id            INTEGER PRIMARY KEY,
                automod_enabled     INTEGER NOT NULL DEFAULT 1,
                anti_spam           INTEGER NOT NULL DEFAULT 1,
                anti_invite         INTEGER NOT NULL DEFAULT 1,
                anti_scam           INTEGER NOT NULL DEFAULT 1,
                anti_mass_mention   INTEGER NOT NULL DEFAULT 1,
                anti_caps           INTEGER NOT NULL DEFAULT 1,
                anti_emoji_spam     INTEGER NOT NULL DEFAULT 1,
                bad_word_filter     INTEGER NOT NULL DEFAULT 1,
                warn_threshold      INTEGER NOT NULL DEFAULT 3,
                warn_action         TEXT    NOT NULL DEFAULT 'timeout',
                updated_at          TEXT    NOT NULL DEFAULT (datetime('now'))
            );
            """,
            # ---- logging_config -----------------------------------------
            """
            CREATE TABLE IF NOT EXISTS logging_config (
                guild_id           INTEGER PRIMARY KEY,
                log_channel_id     INTEGER,
                log_message_edit   INTEGER NOT NULL DEFAULT 1,
                log_message_delete INTEGER NOT NULL DEFAULT 1,
                log_member_join    INTEGER NOT NULL DEFAULT 1,
                log_member_leave   INTEGER NOT NULL DEFAULT 1,
                log_bans           INTEGER NOT NULL DEFAULT 1,
                log_kicks          INTEGER NOT NULL DEFAULT 1,
                log_timeouts       INTEGER NOT NULL DEFAULT 1,
                log_warnings       INTEGER NOT NULL DEFAULT 1,
                log_role_updates   INTEGER NOT NULL DEFAULT 1,
                updated_at         TEXT    NOT NULL DEFAULT (datetime('now'))
            );
            """,
        ]
        for stmt in statements:
            await self._conn.execute(stmt)

    # ------------------------------------------------------------------
    # Warnings
    # ------------------------------------------------------------------

    async def add_warning(
        self,
        guild_id: int,
        user_id: int,
        moderator_id: int,
        reason: str,
    ) -> int:
        """Insert a warning and return the new warning ID."""
        async with self._conn.execute(
            """
            INSERT INTO warnings (guild_id, user_id, moderator_id, reason)
            VALUES (?, ?, ?, ?)
            """,
            (guild_id, user_id, moderator_id, reason),
        ) as cursor:
            await self._conn.commit()
            return cursor.lastrowid  # type: ignore[return-value]

    async def get_warnings(
        self, guild_id: int, user_id: int
    ) -> list[aiosqlite.Row]:
        """Return all warnings for a user in a guild (newest first)."""
        async with self._conn.execute(
            """
            SELECT * FROM warnings
            WHERE guild_id = ? AND user_id = ?
            ORDER BY created_at DESC
            """,
            (guild_id, user_id),
        ) as cursor:
            return await cursor.fetchall()

    async def remove_warning(self, warning_id: int, guild_id: int) -> bool:
        """
        Delete a specific warning by ID (must belong to the given guild).
        Returns True if a row was deleted.
        """
        async with self._conn.execute(
            "DELETE FROM warnings WHERE id = ? AND guild_id = ?",
            (warning_id, guild_id),
        ) as cursor:
            await self._conn.commit()
            return cursor.rowcount > 0

    async def clear_warnings(self, guild_id: int, user_id: int) -> int:
        """Delete ALL warnings for a user. Returns the number deleted."""
        async with self._conn.execute(
            "DELETE FROM warnings WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        ) as cursor:
            await self._conn.commit()
            return cursor.rowcount

    async def count_warnings(self, guild_id: int, user_id: int) -> int:
        """Return the total warning count for a user in a guild."""
        async with self._conn.execute(
            "SELECT COUNT(*) FROM warnings WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

    # ------------------------------------------------------------------
    # Moderation action log
    # ------------------------------------------------------------------

    async def log_action(
        self,
        guild_id: int,
        user_id: int,
        moderator_id: int,
        action: str,
        reason: Optional[str] = None,
        duration: Optional[str] = None,
    ) -> None:
        """Persist a moderation action to the audit log table."""
        await self._conn.execute(
            """
            INSERT INTO moderation_actions
                (guild_id, user_id, moderator_id, action, reason, duration)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (guild_id, user_id, moderator_id, action, reason, duration),
        )
        await self._conn.commit()

    async def get_action_history(
        self, guild_id: int, user_id: int, limit: int = 10
    ) -> list[aiosqlite.Row]:
        """Return recent moderation actions for a user."""
        async with self._conn.execute(
            """
            SELECT * FROM moderation_actions
            WHERE guild_id = ? AND user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (guild_id, user_id, limit),
        ) as cursor:
            return await cursor.fetchall()

    # ------------------------------------------------------------------
    # Guild configuration
    # ------------------------------------------------------------------

    async def get_guild_config(self, guild_id: int) -> aiosqlite.Row:
        """
        Fetch guild config, inserting defaults if the guild is new.
        Always returns a Row.
        """
        async with self._conn.execute(
            "SELECT * FROM guild_config WHERE guild_id = ?", (guild_id,)
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            await self._conn.execute(
                "INSERT OR IGNORE INTO guild_config (guild_id) VALUES (?)",
                (guild_id,),
            )
            await self._conn.commit()
            async with self._conn.execute(
                "SELECT * FROM guild_config WHERE guild_id = ?", (guild_id,)
            ) as cursor:
                row = await cursor.fetchone()
        return row  # type: ignore[return-value]

    async def update_guild_config(
        self, guild_id: int, **kwargs: Any
    ) -> None:
        """Update one or more columns in guild_config for the given guild."""
        if not kwargs:
            return
        kwargs["updated_at"] = datetime.utcnow().isoformat()
        cols = ", ".join(f"{k} = ?" for k in kwargs)
        vals = list(kwargs.values()) + [guild_id]
        await self._conn.execute(
            f"UPDATE guild_config SET {cols} WHERE guild_id = ?", vals
        )
        await self._conn.commit()

    # ------------------------------------------------------------------
    # Logging configuration
    # ------------------------------------------------------------------

    async def get_logging_config(self, guild_id: int) -> aiosqlite.Row:
        """Return logging config for a guild, creating defaults if absent."""
        async with self._conn.execute(
            "SELECT * FROM logging_config WHERE guild_id = ?", (guild_id,)
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            await self._conn.execute(
                "INSERT OR IGNORE INTO logging_config (guild_id) VALUES (?)",
                (guild_id,),
            )
            await self._conn.commit()
            async with self._conn.execute(
                "SELECT * FROM logging_config WHERE guild_id = ?", (guild_id,)
            ) as cursor:
                row = await cursor.fetchone()
        return row  # type: ignore[return-value]

    async def set_log_channel(self, guild_id: int, channel_id: int) -> None:
        """Set the logging channel for a guild."""
        # Ensure the row exists first.
        await self.get_logging_config(guild_id)
        await self._conn.execute(
            """
            UPDATE logging_config
            SET log_channel_id = ?, updated_at = datetime('now')
            WHERE guild_id = ?
            """,
            (channel_id, guild_id),
        )
        await self._conn.commit()

    async def update_logging_config(
        self, guild_id: int, **kwargs: Any
    ) -> None:
        """Toggle individual logging event flags."""
        if not kwargs:
            return
        kwargs["updated_at"] = datetime.utcnow().isoformat()
        cols = ", ".join(f"{k} = ?" for k in kwargs)
        vals = list(kwargs.values()) + [guild_id]
        await self._conn.execute(
            f"UPDATE logging_config SET {cols} WHERE guild_id = ?", vals
        )
        await self._conn.commit()
