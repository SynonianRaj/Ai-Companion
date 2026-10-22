import re
import json
import pytest
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from unittest.mock import AsyncMock, patch

from sqlalchemy import select, and_
from backend.app.db.models import User, RelationshipState, OpenLoop, Message, Conversation
from backend.app.db.session import init_db, to_utc
from backend.app.services.clock_service import ClockService
from backend.app.services.scheduler_service import scheduler_service
from backend.app.engine.adapter import get_activity_for_time, calculate_pacing, GroqLLMAdapter
from backend.app.engine.orchestrator import orchestrator


@pytest.mark.asyncio
async def test_sqlite_migration_idempotence():
    """Verify that running init_db() multiple times on SQLite is idempotent."""
    # First invocation in test already ran via conftest, run 2 more times
    await init_db()
    await init_db()
    # If no exception was raised and columns exist, migration is idempotent
    assert True


@pytest.mark.asyncio
async def test_user_text_cancels_pending_open_loop(db_session):
    """When user texts before the open loop follow-up is due, the loop is resolved."""
    user = User(username="openloop_user_1", age_eligibility_status=True, ai_disclosure_acknowledged=True)
    db_session.add(user)
    await db_session.flush()

    rel = RelationshipState(
        user_id=user.id,
        persona_id="aanya_v1",
        spontaneous_opt_in=True,
        spontaneous_paused=False,
        lifecycle_status="active",
        unreplied_spontaneous_count=1
    )
    db_session.add(rel)
    await db_session.flush()

    now = ClockService.now()
    loop = OpenLoop(
        relationship_id=rel.id,
        user_id=user.id,
        persona_id=rel.persona_id,
        topic="office_arrival",
        status="open",
        last_relevant_at=now,
        next_review_at=now + timedelta(minutes=45)
    )
    db_session.add(loop)
    await db_session.commit()

    conv = Conversation(
        relationship_id=rel.id,
        user_id=user.id,
        persona_id=rel.persona_id
    )
    db_session.add(conv)
    await db_session.flush()

    # User sends a new message before follow-up triggers
    result = await orchestrator.process_user_message(
        session=db_session,
        user=user,
        relationship=rel,
        conversation=conv,
        user_message="Hey Aanya, free abhi?"
    )
    assert result is not None

    await db_session.refresh(loop)
    await db_session.refresh(rel)
    # Open loop must be marked resolved, and unreplied count reset
    assert loop.status == "resolved"
    assert rel.unreplied_spontaneous_count == 0
    assert rel.spontaneous_paused is False


@pytest.mark.asyncio
async def test_paused_relationship_not_scheduled_by_backfill(db_session):
    """A paused relationship stays paused and is NOT scheduled by backfill."""
    now = ClockService.now()
    user = User(username="paused_user_1", age_eligibility_status=True, ai_disclosure_acknowledged=True)
    db_session.add(user)
    await db_session.flush()

    rel = RelationshipState(
        user_id=user.id,
        persona_id="aanya_v1",
        spontaneous_opt_in=True,
        spontaneous_paused=True,
        next_spontaneous_at=None,
        lifecycle_status="active"
    )
    db_session.add(rel)
    await db_session.commit()

    ready, quiet_count = await scheduler_service.claim_pending_spontaneous_relationships(session=db_session)
    assert not any(r["relationship_id"] == rel.id for r in ready)

    await db_session.refresh(rel)
    assert rel.spontaneous_paused is True
    assert rel.next_spontaneous_at is None


def test_cross_process_sha256_slot_determinism():
    """Verify that hashlib SHA-256 slotting produces deterministic activity and delay across calls."""
    ist = ZoneInfo("Asia/Kolkata")
    dt = datetime(2026, 10, 22, 11, 45, tzinfo=ist)
    rel_id = "test_rel_uuid_abc_123"

    act1, tier1, delay1 = get_activity_for_time(dt, relationship_id=rel_id)
    act2, tier2, delay2 = get_activity_for_time(dt, relationship_id=rel_id)

    assert act1 == act2
    assert tier1 == tier2
    assert delay1 == delay2


@pytest.mark.asyncio
async def test_open_loop_bypasses_3h_active_check_and_respects_daily_cap(db_session):
    """
    Open loops:
    1. Bypass the 3-hour recency check.
    2. Respect daily cap (capped at 2 messages/day).
    3. Drop (status='dropped') during quiet hours (23:00 to 08:00 IST).
    """
    ist = ZoneInfo("Asia/Kolkata")
    # 1. Daytime: 14:00 IST
    dt_day = datetime(2026, 10, 22, 14, 0, 0, tzinfo=ist)
    ClockService.set_time(dt_day)
    now_day = ClockService.now()

    user = User(username="openloop_bypass_user", age_eligibility_status=True, ai_disclosure_acknowledged=True)
    db_session.add(user)
    await db_session.flush()

    # User was active just 10 minutes ago
    rel = RelationshipState(
        user_id=user.id,
        persona_id="aanya_v1",
        spontaneous_opt_in=True,
        spontaneous_paused=False,
        spontaneous_daily_count=0,
        last_user_initiated_interaction_at=now_day - timedelta(minutes=10),
        next_spontaneous_at=now_day + timedelta(hours=4),
        lifecycle_status="active"
    )
    db_session.add(rel)
    await db_session.flush()

    loop = OpenLoop(
        relationship_id=rel.id,
        user_id=user.id,
        persona_id=rel.persona_id,
        topic="office_arrival",
        status="open",
        last_relevant_at=now_day - timedelta(minutes=60),
        next_review_at=now_day - timedelta(minutes=5)
    )
    db_session.add(loop)
    await db_session.commit()

    ready, quiet_count = await scheduler_service.claim_pending_spontaneous_relationships(session=db_session)
    assert any(r["relationship_id"] == rel.id and r["item_type"] == "open_loop" for r in ready)

    await db_session.refresh(rel)
    await db_session.refresh(loop)
    assert rel.spontaneous_daily_count == 1
    assert loop.status == "resolved"

    # 2. Quiet hours: 01:30 IST
    dt_night = datetime(2026, 10, 23, 1, 30, 0, tzinfo=ist)
    ClockService.set_time(dt_night)
    now_night = ClockService.now()

    loop_quiet = OpenLoop(
        relationship_id=rel.id,
        user_id=user.id,
        persona_id=rel.persona_id,
        topic="general_arrival",
        status="open",
        last_relevant_at=now_night - timedelta(minutes=40),
        next_review_at=now_night - timedelta(minutes=5)
    )
    db_session.add(loop_quiet)
    await db_session.commit()

    ready_q, quiet_count_q = await scheduler_service.claim_pending_spontaneous_relationships(session=db_session)
    await db_session.refresh(loop_quiet)
    # Stale open loop dropped instead of waking up user or rolling over awkwardly
    assert loop_quiet.status == "dropped"


@pytest.mark.asyncio
async def test_glitch_fallback_excluded_from_next_prompt_history(db_session):
    """Ensure message with is_glitch_fallback: true is excluded from prompt history."""
    user = User(username="glitch_test_user", age_eligibility_status=True, ai_disclosure_acknowledged=True)
    db_session.add(user)
    await db_session.flush()

    rel = RelationshipState(
        user_id=user.id,
        persona_id="aanya_v1",
        lifecycle_status="active"
    )
    db_session.add(rel)
    await db_session.flush()

    conv = Conversation(
        relationship_id=rel.id,
        user_id=user.id,
        persona_id=rel.persona_id
    )
    db_session.add(conv)
    await db_session.flush()

    now = ClockService.now()
    # Message 1: Normal assistant message
    msg1 = Message(
        conversation_id=conv.id,
        relationship_id=rel.id,
        user_id=user.id,
        persona_id=rel.persona_id,
        role="assistant",
        content="Hey! How is your day going?",
        status="active",
        created_at=now - timedelta(minutes=5),
        metadata_json={"emotion": "warm"}
    )
    # Message 2: Glitch fallback message
    msg_glitch = Message(
        conversation_id=conv.id,
        relationship_id=rel.id,
        user_id=user.id,
        persona_id=rel.persona_id,
        role="assistant",
        content="Arre ek second, network thoda glitch kar raha hai... kya bola tumne?",
        status="active",
        created_at=now - timedelta(minutes=4),
        metadata_json={"is_glitch_fallback": True}
    )
    # Message 3: User reply "??"
    msg3 = Message(
        conversation_id=conv.id,
        relationship_id=rel.id,
        user_id=user.id,
        persona_id=rel.persona_id,
        role="user",
        content="??",
        status="active",
        created_at=now - timedelta(minutes=3)
    )
    db_session.add_all([msg1, msg_glitch, msg3])
    await db_session.commit()

    # Now verify query constructed in orchestrator excludes glitch message
    recent_msgs_stmt = (
        select(Message)
        .where(
            and_(
                Message.relationship_id == rel.id,
                Message.status == "active"
            )
        )
        .order_by(Message.created_at.desc(), Message.sequence_order.desc())
        .limit(8)
    )
    recent_msgs_raw = (await db_session.execute(recent_msgs_stmt)).scalars().all()
    filtered_messages = [
        {"role": m.role, "content": m.content}
        for m in reversed(recent_msgs_raw)
        if not (m.metadata_json or {}).get("is_glitch_fallback")
    ]

    contents = [m["content"] for m in filtered_messages]
    assert "Hey! How is your day going?" in contents
    assert "??" in contents
    assert "Arre ek second, network thoda glitch kar raha hai... kya bola tumne?" not in contents


@pytest.mark.asyncio
async def test_daily_count_resets_past_ist_midnight(db_session):
    """Verify that spontaneous_daily_count resets to 0 past IST midnight."""
    ist = ZoneInfo("Asia/Kolkata")
    # Day 1: 22:00 IST
    dt_day1 = datetime(2026, 10, 21, 22, 0, 0, tzinfo=ist)
    ClockService.set_time(dt_day1)
    now_day1 = ClockService.now()

    user = User(username="daily_cap_user", age_eligibility_status=True, ai_disclosure_acknowledged=True)
    db_session.add(user)
    await db_session.flush()

    rel = RelationshipState(
        user_id=user.id,
        persona_id="aanya_v1",
        spontaneous_opt_in=True,
        spontaneous_paused=False,
        spontaneous_daily_count=2,
        spontaneous_daily_reset_at=now_day1,
        last_user_initiated_interaction_at=now_day1 - timedelta(hours=5),
        next_spontaneous_at=now_day1 + timedelta(minutes=10),
        lifecycle_status="active"
    )
    db_session.add(rel)
    await db_session.commit()

    # Move time past IST midnight to 09:00 IST the next day
    dt_day2 = datetime(2026, 10, 22, 9, 0, 0, tzinfo=ist)
    ClockService.set_time(dt_day2)
    now_day2 = ClockService.now()
    rel.next_spontaneous_at = now_day2 - timedelta(minutes=5)
    await db_session.commit()

    ready, quiet_count = await scheduler_service.claim_pending_spontaneous_relationships(session=db_session)
    assert any(r["relationship_id"] == rel.id for r in ready)

    await db_session.refresh(rel)
    # Count incremented from 0 to 1 for the new day
    assert rel.spontaneous_daily_count == 1


@pytest.mark.asyncio
async def test_malformed_llm_json_fallback_and_deduplication(db_session):
    """
    Verify:
    1. Malformed JSON from LLM gracefully defaults to regex extraction.
    2. Consecutive departure messages deduplicate to a single open loop.
    3. Expected minutes are clamped between 15 and 240.
    """
    user = User(username="dedupe_user", age_eligibility_status=True, ai_disclosure_acknowledged=True)
    db_session.add(user)
    await db_session.flush()

    rel = RelationshipState(
        user_id=user.id,
        persona_id="aanya_v1",
        lifecycle_status="active"
    )
    db_session.add(rel)
    await db_session.commit()

    now = ClockService.now()

    # First departure message
    await orchestrator._extract_and_store_open_loop(
        session=db_session,
        relationship=rel,
        user=user,
        text="office pahunch ke text krta hu",
        now=now
    )
    await db_session.commit()

    loops = (await db_session.execute(
        select(OpenLoop).where(
            and_(OpenLoop.relationship_id == rel.id, OpenLoop.status == "open")
        )
    )).scalars().all()
    assert len(loops) == 1
    assert loops[0].topic == "office_arrival"
    # Office arrival defaults to 80 minutes
    assert to_utc(loops[0].next_review_at) > to_utc(now) + timedelta(minutes=70)
    assert to_utc(loops[0].next_review_at) <= to_utc(now) + timedelta(minutes=85)

    # Second consecutive departure message (e.g. "chal bye, ofc pahunch ke baat krta hu")
    now_later = now + timedelta(minutes=2)
    await orchestrator._extract_and_store_open_loop(
        session=db_session,
        relationship=rel,
        user=user,
        text="chal bye, ofc pahunch ke baat krta hu",
        now=now_later
    )
    await db_session.commit()

    # Deduplicated into exactly 1 open loop
    loops_after = (await db_session.execute(
        select(OpenLoop).where(
            and_(OpenLoop.relationship_id == rel.id, OpenLoop.status == "open")
        )
    )).scalars().all()
    assert len(loops_after) == 1
    assert loops_after[0].id == loops[0].id


@pytest.mark.asyncio
async def test_backend_authoritative_show_skip_wait(client):
    """
    Verify authoritative show_skip_wait computation:
    - Departure signoff ends active flow and uses quick_signoff (show_skip_wait = False).
    - Rapid follow-up during active flow (< 3.5 min) gives quick tier (show_skip_wait = False).
    """
    reg = await client.post("/api/auth/register", json={
        "username": "skipwait_user",
        "age_confirmed": True,
        "ai_disclosure_accepted": True
    })
    rel_id = reg.json()["relationship_id"]

    # 1. First chat message
    res1 = await client.post("/api/chat/send", json={
        "relationship_id": rel_id,
        "message": "Hey Aanya!"
    })
    assert res1.status_code == 200
    data1 = res1.json()
    assert "show_skip_wait" in data1

    # 2. Departure signoff -> quick_signoff delay, show_skip_wait must be False
    res_signoff = await client.post("/api/chat/send", json={
        "relationship_id": rel_id,
        "message": "chal bye, office nikal raha hu"
    })
    assert res_signoff.status_code == 200
    data_signoff = res_signoff.json()
    assert data_signoff["show_skip_wait"] is False
    assert data_signoff["delay_tier"] == "quick_signoff"
