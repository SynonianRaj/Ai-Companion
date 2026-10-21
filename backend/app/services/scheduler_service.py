import random
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Tuple, Dict, Any, Optional
from zoneinfo import ZoneInfo
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import settings
from backend.app.db.models import RelationshipState, Conversation, Message
from backend.app.db.session import async_session_factory, to_utc
from backend.app.services.clock_service import ClockService
from backend.app.services.push_service import push_service

logger = logging.getLogger(__name__)

# Realistic, spontaneous Aanya check-ins contextual to the time of day
SPONTANEOUS_MESSAGES_BY_PERIOD = {
    "morning": [
        "Morning filter coffee in hand ☕ Jacaranda trees outside look gorgeous today. Tumhara din kaisa start hua?",
        "Subah subah Delhi ki yaad aa gayi... cold mornings and hot parathas. Bangalore mein chilly breeze hai though!",
        "Uth gaye ya abhi bhi alarm snooze chal raha hai? 😄"
    ],
    "afternoon": [
        "Figma sprint chal raha hai... designers block hit ho raha tha so taking a 5 min break. Kya chal raha hai tumhara?",
        "Just stepped out for lunch at 12th Main Indiranagar! Weather is actually so pleasant today ✨",
        "Aaj ka workday kaisa ja raha hai? Tumhara lunch hua?"
    ],
    "evening": [
        "Metro commute wrap ho gaya! Finally winding down. Any fun plans for the evening?",
        "Indiranagar evenings under the streetlights with indie tracks on loop 🎧 How was your day?",
        "Chai break time! Just finished a client design critique. Tumhara scene kya hai abhi?"
    ],
    "night": [
        "Late night playlist on loop (Prateek Kuhad vibe tonight) ✨ Sone ka plan hai ya night owl mode?",
        "Just sketching some UI layouts before sleep. Tum soye nahi abhi tak?"
    ]
}


class SchedulerService:
    """
    Spontaneous persona messaging engine implementing the 'Claim, then work' pattern.
    - Transaction 1 (<5ms): SELECT ... FOR UPDATE SKIP LOCKED, reschedule next_spontaneous_at, commit.
    - Quiet Hours (23:00 to 08:00 IST): Reschedules to 08:00 IST + 5-90 min jitter to avoid synchronized bursts.
    - Execution (outside lock): Generates text and dispatches high-urgency Web Push.
    """

    @classmethod
    async def claim_pending_spontaneous_relationships(
        cls,
        session: Optional[AsyncSession] = None
    ) -> Tuple[List[Dict[str, str]], int]:
        """
        Fast atomic claim (<5ms transaction).
        Returns:
            (ready_relationships: list of dicts, rescheduled_quiet_count: int)
        """
        now = to_utc(ClockService.now())
        try:
            ist_tz = ZoneInfo("Asia/Kolkata")
        except Exception:
            ist_tz = timezone.utc

        ist_now = now.astimezone(ist_tz)
        is_quiet = ist_now.hour >= 23 or ist_now.hour < 8

        ready_items: List[Dict[str, str]] = []
        rescheduled_quiet_count = 0
        batch_limit = getattr(settings, "TICK_BATCH_SIZE", 5)

        async def _do_claim(s: AsyncSession):
            nonlocal rescheduled_quiet_count
            stmt = (
                select(RelationshipState)
                .where(
                    and_(
                        RelationshipState.spontaneous_opt_in == True,
                        RelationshipState.next_spontaneous_at.is_not(None),
                        RelationshipState.next_spontaneous_at <= now,
                        RelationshipState.lifecycle_status == "active"
                    )
                )
                .order_by(RelationshipState.next_spontaneous_at.asc())
                .limit(batch_limit)
                .with_for_update(skip_locked=True)
            )
            candidates = (await s.execute(stmt)).scalars().all()

            for rel in candidates:
                if is_quiet:
                    # Reschedule to next 08:00 IST + random jitter (5 to 90 minutes)
                    jitter_minutes = random.randint(5, 90)
                    next_8am = ist_now.replace(hour=8, minute=0, second=0, microsecond=0)
                    if ist_now.hour >= 23:
                        next_8am += timedelta(days=1)
                    rescheduled_time = (next_8am + timedelta(minutes=jitter_minutes)).astimezone(timezone.utc)
                    rel.next_spontaneous_at = rescheduled_time
                    rescheduled_quiet_count += 1
                else:
                    # Daytime/evening: advance next spontaneous trigger by 3.0 to 6.0 hours
                    next_hours = random.uniform(3.0, 6.0)
                    rel.next_spontaneous_at = now + timedelta(hours=next_hours)
                    rel.last_spontaneous_at = now
                    ready_items.append({
                        "relationship_id": rel.id,
                        "user_id": rel.user_id,
                        "persona_id": rel.persona_id
                    })

            await s.commit()

        if session is not None:
            await _do_claim(session)
        else:
            async with async_session_factory() as s:
                await _do_claim(s)

        return ready_items, rescheduled_quiet_count

    @classmethod
    async def dispatch_claimed_messages(cls, items: List[Dict[str, str]]) -> int:
        """
        Executes outside the database transaction lock.
        Generates spontaneous text and delivers message + push.
        """
        if not items:
            return 0

        now = to_utc(ClockService.now())
        try:
            ist_tz = ZoneInfo("Asia/Kolkata")
        except Exception:
            ist_tz = timezone.utc
        ist_now = now.astimezone(ist_tz)
        hour = ist_now.hour

        if 8 <= hour < 12:
            pool = SPONTANEOUS_MESSAGES_BY_PERIOD["morning"]
        elif 12 <= hour < 17:
            pool = SPONTANEOUS_MESSAGES_BY_PERIOD["afternoon"]
        elif 17 <= hour < 22:
            pool = SPONTANEOUS_MESSAGES_BY_PERIOD["evening"]
        else:
            pool = SPONTANEOUS_MESSAGES_BY_PERIOD["night"]

        dispatched_count = 0

        for item in items:
            relationship_id = item["relationship_id"]
            user_id = item["user_id"]
            persona_id = item["persona_id"]

            text_bubble = random.choice(pool)

            async with async_session_factory() as session:
                # Find active conversation
                conv_stmt = (
                    select(Conversation)
                    .where(Conversation.relationship_id == relationship_id)
                    .order_by(Conversation.created_at.desc())
                )
                conv = (await session.execute(conv_stmt)).scalar_one_or_none()

                if not conv:
                    conv = Conversation(
                        relationship_id=relationship_id,
                        user_id=user_id,
                        persona_id=persona_id,
                        title="Chat with Aanya",
                        created_at=now
                    )
                    session.add(conv)
                    await session.flush()

                # Add spontaneous assistant message (deliver_at=now, seen_at=None)
                msg = Message(
                    conversation_id=conv.id,
                    relationship_id=relationship_id,
                    user_id=user_id,
                    persona_id=persona_id,
                    role="assistant",
                    content=text_bubble,
                    created_at=now,
                    deliver_at=now,
                    seen_at=None,
                    status="active",
                    metadata_json={"spontaneous": True}
                )
                session.add(msg)
                await session.commit()

                # Dispatch high-urgency Web Push to user's phone
                await push_service.send_notification(
                    session=session,
                    user_id=user_id,
                    title="Aanya",
                    body=text_bubble,
                    data={"relationship_id": relationship_id, "conversation_id": conv.id}
                )
                dispatched_count += 1

        return dispatched_count


scheduler_service = SchedulerService()
