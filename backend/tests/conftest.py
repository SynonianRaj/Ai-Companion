import os
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

# Use a test SQLite database
TEST_DB_URL = "sqlite+aiosqlite:///./test_companion.db"
os.environ["DATABASE_URL"] = TEST_DB_URL

from backend.app.core.config import settings
settings.DATABASE_URL = TEST_DB_URL
settings.LLM_PROVIDER = "mock"

from backend.app.db.base import Base
import backend.app.db.models
import backend.app.db.session as session_module
from backend.app.db.session import get_db, init_db
from backend.app.services.clock_service import ClockService
from backend.app.main import app

test_engine = create_async_engine(
    TEST_DB_URL,
    echo=False,
    poolclass=NullPool,
    connect_args={"timeout": 30.0}
)
test_session_factory = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False
)
session_module.engine = test_engine
session_module.async_session_factory = test_session_factory


async def override_get_db():
    async with test_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()


app.dependency_overrides[get_db] = override_get_db


@pytest_asyncio.fixture(autouse=True)
async def setup_test_db():
    ClockService.reset()
    await init_db()
    async with test_engine.begin() as conn:
        await conn.exec_driver_sql("PRAGMA journal_mode = WAL")
        await conn.run_sync(Base.metadata.create_all)
        await conn.exec_driver_sql("PRAGMA foreign_keys = OFF")
        for table in reversed(Base.metadata.sorted_tables):
            await conn.exec_driver_sql(f"DELETE FROM {table.name}")
        await conn.exec_driver_sql("PRAGMA foreign_keys = ON")

    # Initialize seed data
    from backend.app.db.models import Persona, PersonaState
    from datetime import datetime, timezone

    async with test_session_factory() as session:
        aanya = Persona(
            id="aanya_v1",
            name="Aanya",
            fictional_bio="24-year-old freelance UI/UX designer living in Indiranagar, Bengaluru.",
            stable_traits={"city": "Bengaluru", "age": 24},
            language_style={"primary_mode": "Hinglish"},
            lifestyle_profile={"timezone": "Asia/Kolkata"},
            persona_version="v8.0"
        )
        session.add(aanya)
        aanya_state = PersonaState(
            persona_id="aanya_v1",
            current_activity="Sipping coffee at an Indiranagar cafe",
            current_mood="warm_playful",
            current_plan="Sketching wireframes",
            simulated_local_time=datetime.now(timezone.utc),
            state_version=1
        )
        session.add(aanya_state)
        await session.commit()

    yield

    ClockService.reset()


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def db_session():
    async with test_session_factory() as session:
        yield session
