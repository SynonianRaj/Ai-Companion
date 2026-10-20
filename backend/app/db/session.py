from typing import AsyncGenerator
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from backend.app.core.config import settings
from backend.app.db.base import Base
from backend.app.db.models import Persona, PersonaState


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
    """Create tables if they don't exist and seed canonical Persona 1."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

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
