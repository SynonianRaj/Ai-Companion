from datetime import datetime, timezone, timedelta
from typing import Optional


class ClockService:
    """
    Controllable test clock.
    Allows deterministic time advancement during testing and QA verification
    without waiting 15 real days.
    """

    _offset: timedelta = timedelta(0)
    _frozen_time: Optional[datetime] = None

    @classmethod
    def now(cls) -> datetime:
        if cls._frozen_time is not None:
            return cls._frozen_time + cls._offset
        return datetime.now(timezone.utc) + cls._offset

    @classmethod
    def advance_time(cls, days: float = 0, hours: float = 0, minutes: float = 0, seconds: float = 0) -> datetime:
        """Advances the virtual test clock."""
        cls._offset += timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)
        return cls.now()

    @classmethod
    def set_time(cls, dt: datetime) -> None:
        """Sets a fixed base time in UTC."""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        cls._frozen_time = dt
        cls._offset = timedelta(0)

    @classmethod
    def reset(cls) -> None:
        """Resets the clock back to system time."""
        cls._offset = timedelta(0)
        cls._frozen_time = None
