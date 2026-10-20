import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from backend.app.services.clock_service import ClockService
from backend.app.services.lifecycle_service import lifecycle_service
from backend.app.services.memory_service import memory_service
from backend.app.db.models import (
    User, RelationshipState, Conversation, Message, SubscriptionEntitlement,
    Persona, Memory
)


@pytest.mark.asyncio
async def test_clock_service_time_travel():
    ClockService.reset()
    start_time = ClockService.now()
    ClockService.advance_time(days=5, hours=2)
    advanced_time = ClockService.now()
    diff = advanced_time - start_time
    assert diff.days == 5
    assert diff.seconds >= 7200

    ClockService.reset()
    reset_time = ClockService.now()
    assert abs((reset_time - datetime.now(timezone.utc)).total_seconds()) < 2


@pytest.mark.asyncio
async def test_entitled_user_never_expires(db_session):
    now = ClockService.now()
    user = User(username="pilot_tester", age_eligibility_status=True, ai_disclosure_acknowledged=True)
    db_session.add(user)
    await db_session.flush()

    # Active beta entitlement
    ent = SubscriptionEntitlement(user_id=user.id, plan_type="beta_pilot", status="active", started_at=now)
    db_session.add(ent)

    rel = RelationshipState(user_id=user.id, persona_id="aanya_v1", last_user_initiated_interaction_at=now)
    db_session.add(rel)
    await db_session.commit()

    await lifecycle_service.record_user_interaction(db_session, rel)
    assert rel.expires_at is None

    # Advance 20 days: should NOT expire or delete
    ClockService.advance_time(days=20)
    checks = await lifecycle_service.process_lifecycle_checks(db_session)
    assert len(checks["expired_and_deleted"]) == 0
    assert rel.lifecycle_status == "active"


@pytest.mark.asyncio
async def test_unsubscribed_user_inactivity_expiry_and_deletion(db_session):
    now = ClockService.now()
    user = User(username="unsubscribed_user", age_eligibility_status=True, ai_disclosure_acknowledged=True)
    db_session.add(user)
    await db_session.flush()

    # Relationship WITHOUT active subscription
    rel = RelationshipState(user_id=user.id, persona_id="aanya_v1", last_user_initiated_interaction_at=now)
    db_session.add(rel)
    await db_session.commit()

    # User interacts: sets expires_at to +15 days
    await lifecycle_service.record_user_interaction(db_session, rel)
    assert rel.expires_at is not None
    assert (rel.expires_at - now).days == 15

    # Store some memories for this user
    await memory_service.store_memory(
        session=db_session,
        relationship_id=rel.id,
        user_id=user.id,
        persona_id="aanya_v1",
        memory_type="episodic",
        content="User loves indie rock concerts",
        importance=0.8
    )
    await db_session.commit()

    # Advance to Day 12 -> Verify Neutral Reminder
    ClockService.advance_time(days=12.5)
    checks_day12 = await lifecycle_service.process_lifecycle_checks(db_session)
    assert len(checks_day12["reminders_sent"]) == 1
    reminder = checks_day12["reminders_sent"][0]
    assert reminder["relationship_id"] == rel.id
    assert "Notice from AI Companion" in reminder["notice_text"]

    # Advance past Day 15 -> Verify Pilot Dormant Transition
    ClockService.advance_time(days=3)
    checks_day15 = await lifecycle_service.process_lifecycle_checks(db_session)
    assert rel.id in checks_day15["dormant_transitions"]
    assert rel.lifecycle_status == "dormant"

    # Process next cycle: confirmed expired -> Execute permanent deletion
    checks_delete = await lifecycle_service.process_lifecycle_checks(db_session)
    assert len(checks_delete["expired_and_deleted"]) == 1
    assert rel.lifecycle_status == "deleted"

    # Verify user memories deleted
    remaining_mems = await memory_service.get_all_memories(db_session, rel.id)
    assert len(remaining_mems) == 0

    # Verify canonical Persona 1 ("Aanya") remains completely intact
    persona = await db_session.get(Persona, "aanya_v1")
    assert persona is not None
    assert persona.name == "Aanya"
