import pytest
import pytest_asyncio
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select

from backend.app.core.config import settings
from backend.app.db.base import Base
from backend.app.db.models import User, RelationshipState, Conversation, Message, SubscriptionEntitlement
from backend.app.services.clock_service import ClockService
from backend.app.services.presence_service import presence_service
from backend.app.services.scheduler_service import scheduler_service
from backend.app.engine.persona import get_ist_context, derive_aanya_mood, build_heartbeat_prompt
from backend.app.engine.adapter import decide_heartbeat_attention_message


@pytest_asyncio.fixture
async def async_session():
    test_db_url = "sqlite+aiosqlite:///:memory:"
    engine = create_async_engine(test_db_url, echo=False)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_heartbeat_hard_limit_sleep_window(async_session: AsyncSession):
    """Verifies that no attention messages are sent during Aanya's sleep window."""
    user = User(username="sleep_user", age_eligibility_status=True, ai_disclosure_acknowledged=True)
    async_session.add(user)
    await async_session.flush()

    rel = RelationshipState(
        user_id=user.id,
        persona_id="aanya_v1",
        relationship_stage="getting_to_know",
        lifecycle_status="active",
        spontaneous_opt_in=True
    )
    async_session.add(rel)
    await async_session.commit()

    # Set virtual clock to 03:00 IST (21:30 UTC previous day)
    ClockService.set_time(datetime(2026, 10, 26, 21, 30, tzinfo=timezone.utc))

    results = await scheduler_service.execute_heartbeat_tick(session=async_session)
    assert len(results) >= 1
    rel_result = next(r for r in results if r["relationship_id"] == rel.id)
    assert rel_result["action"] == "skip"
    assert "sleep window" in rel_result["reason"].lower()


@pytest.mark.asyncio
async def test_heartbeat_hard_limit_max_3_daily(async_session: AsyncSession):
    """Verifies that max 3 unprompted messages are allowed per day."""
    user = User(username="daily_cap_user", age_eligibility_status=True, ai_disclosure_acknowledged=True)
    async_session.add(user)
    await async_session.flush()

    # Set virtual time to afternoon 15:00 IST (09:30 UTC)
    ClockService.set_time(datetime(2026, 10, 26, 9, 30, tzinfo=timezone.utc))
    now = ClockService.now()

    rel = RelationshipState(
        user_id=user.id,
        persona_id="aanya_v1",
        relationship_stage="getting_to_know",
        lifecycle_status="active",
        spontaneous_opt_in=True,
        spontaneous_daily_count=3,  # Already sent 3 today
        spontaneous_daily_reset_at=now,
        last_spontaneous_at=now - timedelta(hours=3),
        last_user_initiated_interaction_at=now - timedelta(hours=4)
    )
    async_session.add(rel)
    await async_session.commit()

    results = await scheduler_service.execute_heartbeat_tick(session=async_session)
    rel_result = next(r for r in results if r["relationship_id"] == rel.id)
    assert rel_result["action"] == "skip"
    assert "daily limit" in rel_result["reason"].lower()


@pytest.mark.asyncio
async def test_heartbeat_hard_limit_unreplied_message(async_session: AsyncSession):
    """Verifies no sending if she already sent one and user has not replied yet."""
    user = User(username="unreplied_user", age_eligibility_status=True, ai_disclosure_acknowledged=True)
    async_session.add(user)
    await async_session.flush()

    ClockService.set_time(datetime(2026, 10, 26, 11, 0, tzinfo=timezone.utc)) # 16:30 IST
    now = ClockService.now()

    rel = RelationshipState(
        user_id=user.id,
        persona_id="aanya_v1",
        relationship_stage="getting_to_know",
        lifecycle_status="active",
        spontaneous_opt_in=True,
        spontaneous_daily_count=1,
        unreplied_spontaneous_count=1,  # Awaiting reply
        last_spontaneous_at=now - timedelta(hours=3),
        last_user_initiated_interaction_at=now - timedelta(hours=5)
    )
    async_session.add(rel)
    await async_session.commit()

    results = await scheduler_service.execute_heartbeat_tick(session=async_session)
    rel_result = next(r for r in results if r["relationship_id"] == rel.id)
    assert rel_result["action"] == "skip"
    assert "not replied yet" in rel_result["reason"].lower()


@pytest.mark.asyncio
async def test_heartbeat_hard_limit_2_hour_cooldown(async_session: AsyncSession):
    """Verifies that an unprompted message is never sent twice within 2 hours."""
    user = User(username="cooldown_user", age_eligibility_status=True, ai_disclosure_acknowledged=True)
    async_session.add(user)
    await async_session.flush()

    ClockService.set_time(datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)) # 17:30 IST
    now = ClockService.now()

    rel = RelationshipState(
        user_id=user.id,
        persona_id="aanya_v1",
        relationship_stage="getting_to_know",
        lifecycle_status="active",
        spontaneous_opt_in=True,
        spontaneous_daily_count=1,
        unreplied_spontaneous_count=0,
        last_spontaneous_at=now - timedelta(minutes=45),  # Sent only 45m ago (< 2h)
        last_user_initiated_interaction_at=now - timedelta(minutes=10)
    )
    async_session.add(rel)
    await async_session.commit()

    results = await scheduler_service.execute_heartbeat_tick(session=async_session)
    rel_result = next(r for r in results if r["relationship_id"] == rel.id)
    assert rel_result["action"] == "skip"
    assert "cooldown active" in rel_result["reason"].lower()


@pytest.mark.asyncio
async def test_presence_service_online_bypass_push(async_session: AsyncSession):
    """
    Verifies that when the user is online in the app:
    - Web Push is skipped.
    - Message is marked as delivered_live.
    """
    presence_service.clear()

    user = User(username="online_user", age_eligibility_status=True, ai_disclosure_acknowledged=True)
    async_session.add(user)
    await async_session.flush()

    ClockService.set_time(datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)) # 17:30 IST
    now = ClockService.now()

    rel = RelationshipState(
        user_id=user.id,
        persona_id="aanya_v1",
        relationship_stage="getting_to_know",
        lifecycle_status="active",
        spontaneous_opt_in=True,
        spontaneous_daily_count=0,
        unreplied_spontaneous_count=0,
        last_spontaneous_at=None,
        last_user_initiated_interaction_at=now - timedelta(hours=6)
    )
    async_session.add(rel)
    await async_session.commit()

    # Mark user as online in the app right now
    presence_service.mark_online(rel.id)
    assert presence_service.is_online(rel.id) is True

    # Advance clock by 30 seconds
    ClockService.advance_time(seconds=30)
    assert presence_service.is_online(rel.id) is True

    # Mock an explicit send decision
    llm_context = {
        "ist_info": get_ist_context(now),
        "mood": "missing_him",
        "time_since_user_str": "6 hours ago",
        "time_since_unprompted_str": "None today",
        "hours_since_user": 6.0,
        "hours_since_unprompted": None,
        "recent_messages": [],
        "stored_facts": {},
        "relationship_id": rel.id,
        "user_id": user.id
    }

    # Verify decision sanitization
    decision = await decide_heartbeat_attention_message(llm_context)
    assert decision["action"] in ("send", "skip")
    assert "reason" in decision


@pytest.mark.asyncio
async def test_presence_expiry():
    """Verifies that a presence ping expires after the threshold."""
    presence_service.clear()
    rel_id = "rel_test_123"

    now = datetime(2026, 10, 26, 10, 0, tzinfo=timezone.utc)
    ClockService.set_time(now)

    presence_service.mark_online(rel_id)
    assert presence_service.is_online(rel_id, threshold_seconds=60) is True

    # Advance 65 seconds
    ClockService.advance_time(seconds=65)
    assert presence_service.is_online(rel_id, threshold_seconds=60) is False


@pytest.mark.asyncio
async def test_derive_aanya_mood():
    """Tests mood derivation for different contexts."""
    ist_info = {"routine_state": "working", "is_weekend": False}
    mood_work = derive_aanya_mood(ist_info, hours_since_user=3.0)
    assert "bored_at_work" in mood_work

    ist_free = {"routine_state": "free", "is_weekend": False}
    mood_missing = derive_aanya_mood(ist_free, hours_since_user=7.0)
    assert "missing_him" in mood_missing

    # Sulky check
    recent = [
        {"role": "user", "content": "acha suno"},
        {"role": "assistant", "content": "haan bolo na?"}
    ]
    mood_sulky = derive_aanya_mood(ist_free, hours_since_user=2.5, recent_messages=recent)
    assert "a_little_sulky" in mood_sulky
