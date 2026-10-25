from datetime import datetime, timezone
from typing import Dict, Optional
from backend.app.services.clock_service import ClockService


class PresenceService:
    """
    In-memory presence tracking for active web PWA sessions.
    Allows checking if a user is currently looking at the app,
    so AI-initiated attention messages can be delivered live with
    a typing delay instead of firing a background Web Push.
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
        Default threshold: 70s (supports 25-30s ping intervals with room for network jitter).
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


presence_service = PresenceService()
