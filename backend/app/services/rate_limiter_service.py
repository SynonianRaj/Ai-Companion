from datetime import datetime, timezone
from typing import Tuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import UserRateLimit
from backend.app.core.config import settings
from backend.app.services.clock_service import ClockService


class RateLimiterService:
    """
    Database-backed rate limiter for LLM requests.
    Persists counters in PostgreSQL / SQLite so Render dyno restarts
    and spin-downs never reset user quotas.
    """

    @classmethod
    async def check_and_increment(
        cls,
        session: AsyncSession,
        user_id: str,
        max_per_minute: int = 6,
        max_per_day: int = 40
    ) -> Tuple[bool, str]:
        """
        Atomically checks and increments user's minute and daily usage counters.
        Returns:
            (allowed: bool, reason: str)
        """
        now = ClockService.now()
        current_minute = int(now.timestamp()) // 60
        current_day = now.strftime("%Y-%m-%d")

        stmt = select(UserRateLimit).where(UserRateLimit.user_id == user_id)
        record = (await session.execute(stmt)).scalar_one_or_none()

        if not record:
            record = UserRateLimit(
                user_id=user_id,
                window_minute=current_minute,
                minute_count=1,
                day_date=current_day,
                day_count=1,
                updated_at=now
            )
            session.add(record)
            await session.commit()
            return True, "ok"

        # Check minute window
        if record.window_minute != current_minute:
            record.window_minute = current_minute
            record.minute_count = 1
        else:
            record.minute_count += 1

        # Check day window
        if record.day_date != current_day:
            record.day_date = current_day
            record.day_count = 1
        else:
            record.day_count += 1

        record.updated_at = now
        await session.commit()

        if record.minute_count > max_per_minute:
            return False, f"minute_limit_exceeded ({record.minute_count}/{max_per_minute})"

        if record.day_count > max_per_day:
            return False, f"daily_limit_exceeded ({record.day_count}/{max_per_day})"

        return True, "ok"


rate_limiter_service = RateLimiterService()
