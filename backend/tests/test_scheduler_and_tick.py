import pytest
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from httpx import AsyncClient, ASGITransport

from backend.app.main import app
from backend.app.core.config import settings
from backend.app.services.clock_service import ClockService
from backend.app.services.scheduler_service import scheduler_service
from backend.app.db.models import User, RelationshipState, Conversation, Message, PushSubscription
from backend.app.db.session import to_utc
from backend.app.db.session import to_utc


@pytest.mark.asyncio
async def test_scheduler_claim_during_daytime(db_session):
    ClockService.reset()
    # 2:00 PM IST is 08:30 UTC
    dt = datetime(2026, 10, 22, 8, 30, 0, tzinfo=timezone.utc)
    ClockService.set_time(dt)
    now = ClockService.now()

    user = User(username="scheduler_user_1", age_eligibility_status=True, ai_disclosure_acknowledged=True)
    db_session.add(user)
    await db_session.flush()

    rel = RelationshipState(
        user_id=user.id,
        persona_id="aanya_v1",
        spontaneous_opt_in=True,
        next_spontaneous_at=now - timedelta(minutes=10),
        lifecycle_status="active"
    )
    db_session.add(rel)
    await db_session.commit()

    ready, quiet_count = await scheduler_service.claim_pending_spontaneous_relationships(session=db_session)
    assert quiet_count == 0
    assert len(ready) >= 1
    assert any(r["relationship_id"] == rel.id for r in ready)

    await db_session.refresh(rel)
    # Rescheduled 3 to 6 hours into future
    rel_next = to_utc(rel.next_spontaneous_at)
    assert rel_next > now + timedelta(hours=2.5)


@pytest.mark.asyncio
async def test_scheduler_reschedule_during_quiet_hours(db_session):
    ClockService.reset()
    # 1:00 AM IST is 19:30 UTC previous day
    dt = datetime(2026, 10, 21, 19, 30, 0, tzinfo=timezone.utc)
    ClockService.set_time(dt)
    now = ClockService.now()

    user = User(username="scheduler_user_2", age_eligibility_status=True, ai_disclosure_acknowledged=True)
    db_session.add(user)
    await db_session.flush()

    rel = RelationshipState(
        user_id=user.id,
        persona_id="aanya_v1",
        spontaneous_opt_in=True,
        next_spontaneous_at=now - timedelta(minutes=5),
        lifecycle_status="active"
    )
    db_session.add(rel)
    await db_session.commit()

    ready, quiet_count = await scheduler_service.claim_pending_spontaneous_relationships(session=db_session)
    assert quiet_count >= 1
    # Does NOT enqueue for immediate message delivery during quiet hours
    assert not any(r["relationship_id"] == rel.id for r in ready)

    await db_session.refresh(rel)
    # Next spontaneous should be today at 08:00 IST + 5-90 min jitter
    ist_tz = ZoneInfo("Asia/Kolkata")
    rel_next = to_utc(rel.next_spontaneous_at)
    ist_next = rel_next.astimezone(ist_tz)
    assert ist_next.hour == 8 or ist_next.hour == 9
    assert ist_next.day == 22


@pytest.mark.asyncio
async def test_universal_tick_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Missing secret -> 401
        res = await client.get("/api/internal/tick")
        assert res.status_code == 401

        # 2. Invalid secret -> 401
        res = await client.get("/api/internal/tick?secret=wrong")
        assert res.status_code == 401

        # 3. GET with ?secret= (UptimeRobot format) -> 200
        res_get = await client.get(f"/api/internal/tick?secret={settings.CRON_SECRET}")
        assert res_get.status_code == 200
        data_get = res_get.json()
        assert data_get["status"] == "ok"
        assert "claimed_count" in data_get
        assert "rescheduled_quiet_hours" in data_get

        # 4. POST with X-Cron-Secret header (cron-job.org format) -> 200
        res_post = await client.post(
            "/api/internal/tick",
            headers={"X-Cron-Secret": settings.CRON_SECRET}
        )
        assert res_post.status_code == 200
        data_post = res_post.json()
        assert data_post["status"] == "ok"

        # Allow background task to settle
        import asyncio
        await asyncio.sleep(0.1)
