from typing import AsyncGenerator, Optional
from datetime import datetime, timezone
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from backend.app.core.config import settings
from backend.app.db.base import Base
from backend.app.db.models import Persona, PersonaState


def to_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Ensure datetime is UTC timezone-aware for consistent comparisons."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# Create async engine
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True
)

async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db() -> None:
    """Create tables if they don't exist, safely run column migrations, and seed canonical Persona 1."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        # Safe column migrations for existing databases (SQLite & PostgreSQL)
        is_sqlite = engine.url.drivername.startswith("sqlite")
        if is_sqlite:
            # Check users table columns
            res_u = await conn.exec_driver_sql("PRAGMA table_info(users)")
            user_cols = {row[1] for row in res_u.fetchall()}
            if "city" not in user_cols:
                await conn.exec_driver_sql("ALTER TABLE users ADD COLUMN city VARCHAR(100)")

            # Check messages table columns
            res_m = await conn.exec_driver_sql("PRAGMA table_info(messages)")
            msg_cols = {row[1] for row in res_m.fetchall()}
            if "deliver_at" not in msg_cols:
                await conn.exec_driver_sql("ALTER TABLE messages ADD COLUMN deliver_at DATETIME")
            if "seen_at" not in msg_cols:
                await conn.exec_driver_sql("ALTER TABLE messages ADD COLUMN seen_at DATETIME")
            if "status" not in msg_cols:
                await conn.exec_driver_sql("ALTER TABLE messages ADD COLUMN status VARCHAR(20) DEFAULT 'active'")
            if "sequence_order" not in msg_cols:
                await conn.exec_driver_sql("ALTER TABLE messages ADD COLUMN sequence_order INTEGER DEFAULT 0")
            if "client_msg_id" not in msg_cols:
                await conn.exec_driver_sql("ALTER TABLE messages ADD COLUMN client_msg_id VARCHAR(64)")
        else:
            # PostgreSQL
            await conn.exec_driver_sql("ALTER TABLE users ADD COLUMN IF NOT EXISTS city VARCHAR(100);")
            await conn.exec_driver_sql("ALTER TABLE messages ADD COLUMN IF NOT EXISTS deliver_at TIMESTAMP WITH TIME ZONE;")
            await conn.exec_driver_sql("ALTER TABLE messages ADD COLUMN IF NOT EXISTS seen_at TIMESTAMP WITH TIME ZONE;")
            await conn.exec_driver_sql("ALTER TABLE messages ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'active';")
            await conn.exec_driver_sql("ALTER TABLE messages ADD COLUMN IF NOT EXISTS sequence_order INTEGER DEFAULT 0;")
            await conn.exec_driver_sql("ALTER TABLE messages ADD COLUMN IF NOT EXISTS client_msg_id VARCHAR(64);")

        # Backfill deliver_at, seen_at, status, sequence_order for any legacy rows
        await conn.exec_driver_sql("UPDATE messages SET deliver_at = created_at WHERE deliver_at IS NULL")
        await conn.exec_driver_sql("UPDATE messages SET seen_at = created_at WHERE seen_at IS NULL")
        await conn.exec_driver_sql("UPDATE messages SET status = 'active' WHERE status IS NULL")
        await conn.exec_driver_sql("UPDATE messages SET sequence_order = 0 WHERE sequence_order IS NULL")

    # Seed Persona 1 (Aanya)
    async with async_session_factory() as session:
        persona = await session.get(Persona, "aanya_v1")
        if not persona:
            aanya = Persona(
                id="aanya_v1",
                name="Aanya",
                fictional_bio=(
                    "24-year-old freelance UI/UX designer living in Indiranagar, Bengaluru. "
                    "Originally from Delhi, she loves specialty filter coffee, exploring indie cafes, "
                    "late-night music playlists, and evening strolls under the jacaranda trees. "
                    "She is witty, culturally grounded, perceptive, and naturally code-switches in Hinglish."
                ),
                stable_traits={
                    "age": 24,
                    "city": "Bengaluru",
                    "origin": "Delhi",
                    "profession": "UI/UX Designer",
                    "personality": ["witty", "warm", "curious", "independent", "perceptive"],
                    "interests": ["design", "indie music", "coffee", "psychology", "city walks"],
                    "loves": ["cold brew", "rainy evenings in Bangalore", "honest conversations"],
                    "dislikes": ["pretentiousness", "unsolicited advice", "stiff formal texts"]
                },
                language_style={
                    "primary_mode": "Hinglish",
                    "cadence": "playful, conversational Gen-Z/millennial texting",
                    "code_switching_markers": ["achha suno", "arre yaar", "pakka", "sahi mein", "scene kya hai"],
                    "emoji_tone": "natural, expressive, grounded",
                    "anti_patterns": ["bookish textbook Hindi", "robotic formal tone", "excessive punctuation"]
                },
                lifestyle_profile={
                    "typical_schedule": "flexible freelance hours, late mornings, creative bursts in the evening",
                    "timezone": "Asia/Kolkata"
                },
                persona_version="v8.0"
            )
            session.add(aanya)
            
            # Seed initial dynamic state
            aanya_state = PersonaState(
                persona_id="aanya_v1",
                current_activity="Sipping cold brew at an Indiranagar cafe while sketching design ideas",
                current_mood="warm_playful",
                current_plan="Finishing up a design mockup before heading out for a stroll",
                simulated_local_time=datetime.now(timezone.utc),
                state_version=1
            )
            session.add(aanya_state)
            await session.commit()
