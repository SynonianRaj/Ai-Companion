import pytest
from datetime import datetime, timezone, timedelta
from backend.app.services.clock_service import ClockService
from backend.app.services.rate_limiter_service import rate_limiter_service
from backend.app.db.models import UserRateLimit


@pytest.mark.asyncio
async def test_db_rate_limiter_minute_limit(db_session):
    ClockService.reset()
    user_id = "test_rate_user_1"

    # Limit to 3 per minute for test
    for i in range(3):
        allowed, reason = await rate_limiter_service.check_and_increment(
            session=db_session,
            user_id=user_id,
            max_per_minute=3,
            max_per_day=20
        )
        assert allowed is True
        assert reason == "ok"

    # 4th request in same minute should be rejected
    allowed, reason = await rate_limiter_service.check_and_increment(
        session=db_session,
        user_id=user_id,
        max_per_minute=3,
        max_per_day=20
    )
    assert allowed is False
    assert "minute_limit_exceeded" in reason

    # Advance time by 61 seconds -> should be allowed again
    ClockService.advance_time(minutes=1.1)
    allowed, reason = await rate_limiter_service.check_and_increment(
        session=db_session,
        user_id=user_id,
        max_per_minute=3,
        max_per_day=20
    )
    assert allowed is True


@pytest.mark.asyncio
async def test_db_rate_limiter_daily_limit(db_session):
    ClockService.reset()
    user_id = "test_rate_user_2"

    # Limit to 5 per day for test
    for i in range(5):
        # advance time slightly to avoid minute limit
        ClockService.advance_time(minutes=1.5)
        allowed, reason = await rate_limiter_service.check_and_increment(
            session=db_session,
            user_id=user_id,
            max_per_minute=10,
            max_per_day=5
        )
        assert allowed is True

    # 6th request in same day -> daily limit hit
    ClockService.advance_time(minutes=1.5)
    allowed, reason = await rate_limiter_service.check_and_increment(
        session=db_session,
        user_id=user_id,
        max_per_minute=10,
        max_per_day=5
    )
    assert allowed is False
    assert "daily_limit_exceeded" in reason

    # Advance to next day -> reset daily count
    ClockService.advance_time(days=1.1)
    allowed, reason = await rate_limiter_service.check_and_increment(
        session=db_session,
        user_id=user_id,
        max_per_minute=10,
        max_per_day=5
    )
    assert allowed is True
