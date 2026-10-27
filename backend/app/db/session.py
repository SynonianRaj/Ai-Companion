from typing import AsyncGenerator, Optional
from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
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


def prepare_async_db_url_and_args(raw_url: str):
    """Normalizes database URLs and configures connect_args for async SQLAlchemy / asyncpg / Neon."""
    connect_args = {}
    url = raw_url
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://") and not url.startswith("postgresql+"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    
    if "asyncpg" in url:
        connect_args["statement_cache_size"] = 0
        connect_args["prepared_statement_cache_size"] = 0
        parsed = urlparse(url)
        query_params = parse_qs(parsed.query)
        if "sslmode" in query_params:
            sslmode_val = query_params.pop("sslmode")[0]
            if sslmode_val in ("require", "verify-ca", "verify-full", "prefer"):
                connect_args["ssl"] = sslmode_val
            new_query = urlencode(query_params, doseq=True)
            url = urlunparse(parsed._replace(query=new_query))
            
    return url, connect_args


# Create async engine with Neon / PgBouncer statement cache bypass for asyncpg
db_url, db_connect_args = prepare_async_db_url_and_args(settings.DATABASE_URL)
engine_args = {
    "echo": False,
    "future": True,
}
if db_connect_args:
    engine_args["connect_args"] = db_connect_args

engine = create_async_engine(
    db_url,
    **engine_args
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

            # Check relationship_state table columns
            res_r = await conn.exec_driver_sql("PRAGMA table_info(relationship_state)")
            rel_cols = {row[1] for row in res_r.fetchall()}
            if "next_spontaneous_at" not in rel_cols:
                await conn.exec_driver_sql("ALTER TABLE relationship_state ADD COLUMN next_spontaneous_at DATETIME")
            if "last_spontaneous_at" not in rel_cols:
                await conn.exec_driver_sql("ALTER TABLE relationship_state ADD COLUMN last_spontaneous_at DATETIME")
            if "spontaneous_opt_in" not in rel_cols:
                await conn.exec_driver_sql("ALTER TABLE relationship_state ADD COLUMN spontaneous_opt_in BOOLEAN DEFAULT 1")
            if "spontaneous_paused" not in rel_cols:
                await conn.exec_driver_sql("ALTER TABLE relationship_state ADD COLUMN spontaneous_paused BOOLEAN DEFAULT 0")
            if "spontaneous_daily_count" not in rel_cols:
                await conn.exec_driver_sql("ALTER TABLE relationship_state ADD COLUMN spontaneous_daily_count INTEGER DEFAULT 0")
            if "spontaneous_daily_reset_at" not in rel_cols:
                await conn.exec_driver_sql("ALTER TABLE relationship_state ADD COLUMN spontaneous_daily_reset_at DATETIME")
            if "unreplied_spontaneous_count" not in rel_cols:
                await conn.exec_driver_sql("ALTER TABLE relationship_state ADD COLUMN unreplied_spontaneous_count INTEGER DEFAULT 0")

            # Check open_loops table columns
            res_ol = await conn.exec_driver_sql("PRAGMA table_info(open_loops)")
            ol_cols = {row[1] for row in res_ol.fetchall()}
            if "user_message" not in ol_cols:
                await conn.exec_driver_sql("ALTER TABLE open_loops ADD COLUMN user_message TEXT")
            if "persona_state_at_time" not in ol_cols:
                await conn.exec_driver_sql("ALTER TABLE open_loops ADD COLUMN persona_state_at_time VARCHAR(50)")
            if "loop_type" not in ol_cols:
                await conn.exec_driver_sql("ALTER TABLE open_loops ADD COLUMN loop_type VARCHAR(50) DEFAULT 'departure'")
            if "raised_at" not in ol_cols:
                await conn.exec_driver_sql("ALTER TABLE open_loops ADD COLUMN raised_at DATETIME")
            if "expires_at" not in ol_cols:
                await conn.exec_driver_sql("ALTER TABLE open_loops ADD COLUMN expires_at DATETIME")
        else:
            # PostgreSQL
            await conn.exec_driver_sql("ALTER TABLE users ADD COLUMN IF NOT EXISTS city VARCHAR(100);")
            await conn.exec_driver_sql("ALTER TABLE messages ADD COLUMN IF NOT EXISTS deliver_at TIMESTAMP WITH TIME ZONE;")
            await conn.exec_driver_sql("ALTER TABLE messages ADD COLUMN IF NOT EXISTS seen_at TIMESTAMP WITH TIME ZONE;")
            await conn.exec_driver_sql("ALTER TABLE messages ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'active';")
            await conn.exec_driver_sql("ALTER TABLE messages ADD COLUMN IF NOT EXISTS sequence_order INTEGER DEFAULT 0;")
            await conn.exec_driver_sql("ALTER TABLE messages ADD COLUMN IF NOT EXISTS client_msg_id VARCHAR(64);")
            await conn.exec_driver_sql("ALTER TABLE relationship_state ADD COLUMN IF NOT EXISTS next_spontaneous_at TIMESTAMP WITH TIME ZONE;")
            await conn.exec_driver_sql("ALTER TABLE relationship_state ADD COLUMN IF NOT EXISTS last_spontaneous_at TIMESTAMP WITH TIME ZONE;")
            await conn.exec_driver_sql("ALTER TABLE relationship_state ADD COLUMN IF NOT EXISTS spontaneous_opt_in BOOLEAN DEFAULT TRUE;")
            await conn.exec_driver_sql("ALTER TABLE relationship_state ADD COLUMN IF NOT EXISTS spontaneous_paused BOOLEAN DEFAULT FALSE;")
            await conn.exec_driver_sql("ALTER TABLE relationship_state ADD COLUMN IF NOT EXISTS spontaneous_daily_count INTEGER DEFAULT 0;")
            await conn.exec_driver_sql("ALTER TABLE relationship_state ADD COLUMN IF NOT EXISTS spontaneous_daily_reset_at TIMESTAMP WITH TIME ZONE;")
            await conn.exec_driver_sql("ALTER TABLE relationship_state ADD COLUMN IF NOT EXISTS unreplied_spontaneous_count INTEGER DEFAULT 0;")
            await conn.exec_driver_sql("ALTER TABLE open_loops ADD COLUMN IF NOT EXISTS user_message TEXT;")
            await conn.exec_driver_sql("ALTER TABLE open_loops ADD COLUMN IF NOT EXISTS persona_state_at_time VARCHAR(50);")
            await conn.exec_driver_sql("ALTER TABLE open_loops ADD COLUMN IF NOT EXISTS loop_type VARCHAR(50) DEFAULT 'departure';")
            await conn.exec_driver_sql("ALTER TABLE open_loops ADD COLUMN IF NOT EXISTS raised_at TIMESTAMP WITH TIME ZONE;")
            await conn.exec_driver_sql("ALTER TABLE open_loops ADD COLUMN IF NOT EXISTS expires_at TIMESTAMP WITH TIME ZONE;")

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
