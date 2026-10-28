"""
Presence Service:
1. Tracks active PWA sessions for users.
2. Authoritatively resolves Aanya's persona presence, subtitle, and online dot state:
   - Synchronized with IST routine and active exchanges.
   - Shows "online" when free or when in an active exchange (< 3 mins), even during work hours.
   - Shows "last seen at [time]" after exchange ends or during work breaks.
   - Shows varying bedtime when asleep (never "online").
   - Shows "last seen" when a delayed reply is pending (never "online").
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional
from zoneinfo import ZoneInfo
from backend.app.services.clock_service import ClockService
from backend.app.db.session import to_utc


class PresenceService:
    """
    In-memory presence tracking for active web PWA sessions and
    persona presence resolution.
    """
    def __init__(self):
        self._last_seen: Dict[str, datetime] = {}

    def mark_online(self, relationship_id: str, at: Optional[datetime] = None) -> None:
        """Records an active ping from the client."""
        if not relationship_id:
            return
        self._last_seen[relationship_id] = at or ClockService.now()

    def is_online(self, relationship_id: str, threshold_seconds: int = 70) -> bool:
        """
        Returns True if the user sent a ping within the last `threshold_seconds`.
        Default threshold: 70s.
        """
        if not relationship_id or relationship_id not in self._last_seen:
            return False
        last = self._last_seen[relationship_id]
        now = ClockService.now()
        # Ensure UTC comparison
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        return (now - last).total_seconds() <= threshold_seconds

    def clear(self) -> None:
        """Clears all presence data (useful for test resets)."""
        self._last_seen.clear()

    @classmethod
    def format_ist_time(cls, dt: Optional[datetime]) -> str:
        """Formats datetime to 12-hour IST time string, e.g. '2:14 PM'."""
        if dt is None:
            return "recently"
        try:
            ist_tz = ZoneInfo("Asia/Kolkata")
        except Exception:
            ist_tz = timezone.utc

        utc_dt = to_utc(dt)
        ist_dt = utc_dt.astimezone(ist_tz)
        hour = ist_dt.hour % 12 or 12
        minute = f"{ist_dt.minute:02d}"
        am_pm = "AM" if ist_dt.hour < 12 else "PM"
        return f"{hour}:{minute} {am_pm}"

    @classmethod
    def get_varying_bedtime_str(cls, current_ist_dt: datetime) -> str:
        """
        Computes a varying bedtime for Aanya for that night (not hardcoded 11:30 PM).
        Varies between 11:15 PM and 12:25 AM based on date seed.
        """
        day_num = current_ist_dt.day
        month_num = current_ist_dt.month
        # Deterministic variation per date
        minute_offsets = [12, 18, 24, 32, 38, 45, 52, 58, 5, 15]
        min_choice = minute_offsets[(day_num + month_num) % len(minute_offsets)]
        hour_choice = 11 if min_choice >= 30 else 12
        am_pm = "PM" if hour_choice == 11 else "AM"
        return f"{hour_choice}:{min_choice:02d} {am_pm}"

    @classmethod
    def resolve_persona_presence(
        cls,
        current_time: Optional[datetime] = None,
        routine_state: str = "free",
        last_seen_at: Optional[datetime] = None,
        last_interaction_at: Optional[datetime] = None,
        pending_delivery: bool = False,
        next_deliver_at: Optional[datetime] = None,
        location_override: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Resolves authoritative persona presence status.
        Returns:
        {
          "is_online": bool,
          "status_text": "online" | "last seen 2:14 PM" | "last seen yesterday at 11:42 PM",
          "state": "online" | "busy" | "sleeping" | "delayed_reply" | "away",
          "city_label": "Indiranagar, Bengaluru" | "Rohini, Delhi"
        }
        """
        now = to_utc(current_time or ClockService.now())

        try:
            ist_tz = ZoneInfo("Asia/Kolkata")
        except Exception:
            ist_tz = timezone.utc
        ist_dt = now.astimezone(ist_tz)

        city_label = location_override or "Indiranagar, Bengaluru"

        # 1. Delayed reply pending (deliver_at > now): Never show online
        if pending_delivery and next_deliver_at and to_utc(next_deliver_at) > now:
            ts_str = cls.format_ist_time(last_seen_at or (now - timedelta(minutes=5)))
            return {
                "is_online": False,
                "status_text": f"last seen {ts_str}",
                "state": "delayed_reply",
                "city_label": city_label
            }

        # 2. Sleeping state (00:00 - 08:00 IST): Never show online; show variable bedtime
        if routine_state == "sleeping":
            bedtime_str = cls.get_varying_bedtime_str(ist_dt)
            return {
                "is_online": False,
                "status_text": f"last seen yesterday at {bedtime_str}",
                "state": "sleeping",
                "city_label": city_label
            }

        # 3. Active Exchange Check (< 180 seconds since last user or assistant interaction)
        time_since_interaction = (now - to_utc(last_interaction_at)).total_seconds() if last_interaction_at else 999999.0
        time_since_seen = (now - to_utc(last_seen_at)).total_seconds() if last_seen_at else 999999.0
        is_active_exchange = min(time_since_interaction, time_since_seen) <= 180.0

        if is_active_exchange:
            # Active conversation ongoing: She is looking at her phone!
            return {
                "is_online": True,
                "status_text": "online",
                "state": "online",
                "city_label": city_label
            }

        # 4. Working hours (after active exchange ends): She stepped away or is on Figma
        if routine_state == "working":
            ts_str = cls.format_ist_time(last_seen_at or last_interaction_at or now)
            return {
                "is_online": False,
                "status_text": f"last seen {ts_str}",
                "state": "busy",
                "city_label": city_label
            }

        # 5. Free hours but not currently in active exchange (< 3m)
        if routine_state == "free":
            # If she saw/sent something within last 10 minutes, show last seen [time]
            ts_str = cls.format_ist_time(last_seen_at or last_interaction_at or now)
            return {
                "is_online": False,
                "status_text": f"last seen {ts_str}",
                "state": "away",
                "city_label": city_label
            }

        # 6. Winding down hours
        ts_str = cls.format_ist_time(last_seen_at or last_interaction_at or now)
        return {
            "is_online": False,
            "status_text": f"last seen {ts_str}",
            "state": "winding_down",
            "city_label": city_label
        }


presence_service = PresenceService()
