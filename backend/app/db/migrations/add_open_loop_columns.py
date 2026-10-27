"""
Database migration script: Add context columns to open_loops table.
Supports both SQLite (local dev) and PostgreSQL (Render production).
"""

import asyncio
import logging
from sqlalchemy import text
from backend.app.core.config import settings
from backend.app.db.session import engine

logger = logging.getLogger(__name__)


async def run_open_loops_migration():
    """
    Idempotent migration to add user_message, persona_state_at_time,
    loop_type, raised_at, and expires_at to open_loops.
    """
    db_url = str(settings.DATABASE_URL)
    is_sqlite = "sqlite" in db_url.lower()

    columns_to_add = [
        ("user_message", "TEXT"),
        ("persona_state_at_time", "VARCHAR(50)"),
        ("loop_type", "VARCHAR(50) DEFAULT 'departure'"),
        ("raised_at", "TIMESTAMP WITH TIME ZONE" if not is_sqlite else "DATETIME"),
        ("expires_at", "TIMESTAMP WITH TIME ZONE" if not is_sqlite else "DATETIME"),
    ]

    async with engine.begin() as conn:
        if is_sqlite:
            # Check existing columns in SQLite
            result = await conn.execute(text("PRAGMA table_info(open_loops)"))
            existing_cols = {row[1] for row in result.fetchall()}
            for col_name, col_type in columns_to_add:
                if col_name not in existing_cols:
                    logger.info("Adding column %s to open_loops (SQLite)...", col_name)
                    await conn.execute(text(f"ALTER TABLE open_loops ADD COLUMN {col_name} {col_type}"))
        else:
            # PostgreSQL ADD COLUMN IF NOT EXISTS
            for col_name, col_type in columns_to_add:
                logger.info("Adding column %s to open_loops (Postgres)...", col_name)
                await conn.execute(text(f"ALTER TABLE open_loops ADD COLUMN IF NOT EXISTS {col_name} {col_type}"))

    logger.info("open_loops migration completed successfully.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_open_loops_migration())
