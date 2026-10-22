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

import random
import logging
import httpx
from datetime import datetime, timezone, timedelta
from typing import List, Tuple, Dict, Any, Optional
from zoneinfo import ZoneInfo
from sqlalchemy import select, and_, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import settings
from backend.app.db.models import RelationshipState, Conversation, Message, OpenLoop
from backend.app.db.session import async_session_factory, to_utc
from backend.app.services.clock_service import ClockService
from backend.app.services.push_service import push_service

logger = logging.getLogger(__name__)

# Realistic, spontaneous Aanya check-ins contextual to the time of day (diverse, not work-obsessed)
SPONTANEOUS_MESSAGES_BY_PERIOD = {
    "morning": [
        "Morning filter coffee in hand ☕ Jacaranda trees outside look gorgeous today. Tumhara din kaisa start hua?",
        "Subah subah Delhi ki yaad aa gayi... cold mornings and hot parathas. Bangalore mein chilly breeze hai though!",
        "Uth gaye ya abhi bhi alarm snooze chal raha hai? 😄"
    ],
    "afternoon": [
        "Taking a quick 5 min breather... playlist pe mast acoustic tracks chal rahe hain. Kya chal raha hai tumhara?",
        "Just stepped out for lunch at 12th Main Indiranagar! Weather is actually so pleasant today ✨",
        "Aaj ka workday kaisa ja raha hai? Tumhara lunch hua?"
    ],
    "evening": [
        "Metro commute wrap ho gaya! Finally heading home. Any fun plans for the evening?",
        "Indiranagar evenings under the streetlights with indie tracks on loop 🎧 How was your day?",
        "Chai break time! Just finished some chores. Tumhara scene kya hai abhi?"
    ],
    "night": [
        "Late night playlist on loop (Prateek Kuhad vibe tonight) ✨ Sone ka plan hai ya night owl mode?",
        "Just reading a bit before sleep. Tum soye nahi abhi tak?"
    ]
}

ARRIVAL_FOLLOWUP_MESSAGES = [
    "Arre, tumne bola tha office pahunch ke text karoge, kiya nahi... Kahan busy ho gaye? 😜",
    "Office pahunch gaye safely? Kaam mein phans gaye kya?",
    "Suno, pahunch ke msg karne ko bola tha... sab theek? Kaisa chal raha hai work?",
    "Hey! Office pahunch gaye? Kaam ka pressure zyaada hai kya aaj?"
]


class SchedulerService:
    """
    Spontaneous persona messaging engine implementing the 'Claim, then work' pattern.
    - Lane A: Open loop departure check-ins (bypasses 3h recency, checks quiet hours and daily cap).
    - Lane B: Generic spontaneous reachouts (checks quiet hours, daily cap, 3h recency, unreplied backoff).
    - Daily cap (max 2/day) resets automatically past IST midnight.
    - Sets spontaneous_paused = True at dispatch/claiming time when unreplied count reaches 2.
    - Dropping quiet-hour open loops (status='dropped') so stale messages are never rolled over to next morning.
    """

    @classmethod
    def _maybe_reset_daily_cap(cls, rel: RelationshipState, ist_now: datetime, now_utc: datetime) -> None:
        """Resets spontaneous_daily_count if date has advanced past midnight in IST."""
        try:
            ist_tz = ZoneInfo("Asia/Kolkata")
        except Exception:
            ist_tz = timezone.utc

        today_ist = ist_now.date()
        if rel.spontaneous_daily_reset_at is None:
            rel.spontaneous_daily_count = 0
            rel.spontaneous_daily_reset_at = now_utc
        else:
            last_reset_ist = to_utc(rel.spontaneous_daily_reset_at).astimezone(ist_tz).date()
            if today_ist > last_reset_ist:
                rel.spontaneous_daily_count = 0
                rel.spontaneous_daily_reset_at = now_utc

    @classmethod
    async def claim_pending_spontaneous_relationships(
        cls,
        session: Optional[AsyncSession] = None
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Fast atomic claim.
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

        ready_items: List[Dict[str, Any]] = []
        rescheduled_quiet_count = 0
        batch_limit = getattr(settings, "TICK_BATCH_SIZE", 5)

        async def _do_claim(s: AsyncSession):
            nonlocal rescheduled_quiet_count

            # 1. Backfill un-scheduled active relationships (only if NOT paused)
            backfill_stmt = (
                select(RelationshipState)
                .where(
                    and_(
                        RelationshipState.spontaneous_opt_in == True,
                        RelationshipState.spontaneous_paused == False,
                        RelationshipState.next_spontaneous_at.is_(None),
                        RelationshipState.lifecycle_status == "active"
                    )
                )
                .limit(batch_limit)
            )
            backfill_candidates = (await s.execute(backfill_stmt)).scalars().all()
            for rel in backfill_candidates:
                cls._maybe_reset_daily_cap(rel, ist_now, now)
                # Scatter backfill over 3.0 to 7.0 hours
                scatter_hours = random.uniform(3.0, 7.0)
                sched_time = now + timedelta(hours=scatter_hours)
                sched_ist = sched_time.astimezone(ist_tz)
                if sched_ist.hour >= 23 or sched_ist.hour < 8:
                    next_8am = sched_ist.replace(hour=8, minute=30, second=0, microsecond=0)
                    if sched_ist.hour >= 23:
                        next_8am += timedelta(days=1)
                    sched_time = next_8am.astimezone(timezone.utc)
                rel.next_spontaneous_at = sched_time

            # 2. Lane A: Process Pending Open Loops
            loop_stmt = (
                select(OpenLoop)
                .where(
                    and_(
                        OpenLoop.status == "open",
                        OpenLoop.next_review_at.is_not(None),
                        OpenLoop.next_review_at <= now
                    )
                )
                .limit(batch_limit)
            )
            pending_loops = (await s.execute(loop_stmt)).scalars().all()
            for loop in pending_loops:
                # Quiet hours: drop stale open loops instead of awkward morning rollover
                if is_quiet:
                    loop.status = "dropped"
                    rescheduled_quiet_count += 1
                    continue

                rel = await s.get(RelationshipState, loop.relationship_id)
                if not rel or rel.lifecycle_status != "active":
                    loop.status = "dropped"
                    continue

                cls._maybe_reset_daily_cap(rel, ist_now, now)

                # Daily cap check
                if rel.spontaneous_daily_count >= 2:
                    loop.status = "dropped"
                    continue

                # Open loop follow-up bypasses 3h active check
                loop.status = "resolved"
                rel.spontaneous_daily_count += 1
                rel.unreplied_spontaneous_count += 1
                rel.last_spontaneous_at = now

                # Dispatch-time pause check
                if rel.unreplied_spontaneous_count >= 2:
                    rel.spontaneous_paused = True
                    rel.next_spontaneous_at = None

                ready_items.append({
                    "relationship_id": rel.id,
                    "user_id": rel.user_id,
                    "persona_id": rel.persona_id,
                    "item_type": "open_loop",
                    "topic": loop.topic
                })

            # 3. Lane B: Generic Spontaneous Reachouts
            spont_stmt = (
                select(RelationshipState)
                .where(
                    and_(
                        RelationshipState.spontaneous_opt_in == True,
                        RelationshipState.spontaneous_paused == False,
                        RelationshipState.next_spontaneous_at.is_not(None),
                        RelationshipState.next_spontaneous_at <= now,
                        RelationshipState.lifecycle_status == "active"
                    )
                )
                .order_by(RelationshipState.next_spontaneous_at.asc())
                .limit(batch_limit)
                .with_for_update(skip_locked=True)
            )
            spont_candidates = (await s.execute(spont_stmt)).scalars().all()

            for rel in spont_candidates:
                cls._maybe_reset_daily_cap(rel, ist_now, now)

                if is_quiet:
                    # Reschedule past quiet hours to 08:30 IST + jitter
                    jitter_minutes = random.randint(5, 75)
                    next_8am = ist_now.replace(hour=8, minute=30, second=0, microsecond=0)
                    if ist_now.hour >= 23:
                        next_8am += timedelta(days=1)
                    rescheduled_time = (next_8am + timedelta(minutes=jitter_minutes)).astimezone(timezone.utc)
                    rel.next_spontaneous_at = rescheduled_time
                    rescheduled_quiet_count += 1
                    continue

                # Daily cap check
                if rel.spontaneous_daily_count >= 2:
                    # Capped for today -> push to tomorrow morning
                    next_8am = (ist_now + timedelta(days=1)).replace(hour=8, minute=30, second=0, microsecond=0)
                    rel.next_spontaneous_at = next_8am.astimezone(timezone.utc)
                    continue

                # 3-hour recency check for generic reachouts
                if rel.last_user_initiated_interaction_at:
                    delta_s = (now - to_utc(rel.last_user_initiated_interaction_at)).total_seconds()
                    if delta_s < 10800:
                        # User was active < 3 hours ago -> push forward by 3 hours
                        rel.next_spontaneous_at = now + timedelta(hours=3.0)
                        continue

                # Advance next spontaneous schedule by 3.5 to 6.0 hours
                next_hours = random.uniform(3.5, 6.0)
                rel.next_spontaneous_at = now + timedelta(hours=next_hours)
                rel.last_spontaneous_at = now
                rel.spontaneous_daily_count += 1
                rel.unreplied_spontaneous_count += 1

                # Dispatch-time pause check
                if rel.unreplied_spontaneous_count >= 2:
                    rel.spontaneous_paused = True
                    rel.next_spontaneous_at = None

                ready_items.append({
                    "relationship_id": rel.id,
                    "user_id": rel.user_id,
                    "persona_id": rel.persona_id,
                    "item_type": "spontaneous",
                    "topic": None
                })

            await s.commit()

        if session is not None:
            await _do_claim(session)
        else:
            async with async_session_factory() as s:
                await _do_claim(s)

        return ready_items, rescheduled_quiet_count

    @classmethod
    async def dispatch_claimed_messages(cls, items: List[Dict[str, Any]]) -> int:
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
            item_type = item.get("item_type", "spontaneous")
            topic = item.get("topic")

            if item_type == "open_loop":
                text_bubble = random.choice(ARRIVAL_FOLLOWUP_MESSAGES)
            else:
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
                    metadata_json={
                        "spontaneous": True,
                        "item_type": item_type,
                        "open_loop_topic": topic
                    }
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


scheduler_service = SchedulerService()
