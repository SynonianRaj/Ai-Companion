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
from backend.app.services.presence_service import presence_service
from backend.app.services.memory_service import memory_service
from backend.app.engine.persona import get_ist_context, derive_aanya_mood
from backend.app.engine.adapter import decide_heartbeat_attention_message

logger = logging.getLogger(__name__)

# Realistic, spontaneous Aanya check-ins contextual to the time of day (diverse, not work-obsessed)
SPONTANEOUS_MESSAGES_BY_PERIOD = {
    "morning": [
        "morning filter coffee in hand ☕ jacaranda trees outside look gorgeous today. kaisa start hua tumhara din?",
        "subah subah delhi ki yaad aa gayi... cold mornings and hot parathas. bangalore mein chilly breeze hai though!",
        "uth gaye ya abhi bhi alarm snooze chal raha hai? 😄"
    ],
    "afternoon": [
        "taking a quick 5 min breather... playlist pe mast acoustic tracks chal rahe hain 🎧",
        "just stepped out for lunch at 12th main indiranagar! weather is actually so pleasant today ✨",
        "aaj ka workday kaisa ja raha hai? lunch hua tumhara?"
    ],
    "evening": [
        "metro commute wrap ho gaya! finally heading home. any fun plans for the evening?",
        "indiranagar evenings under the streetlights with indie tracks on loop 🎧",
        "chai break time! just finished some work. tumhara scene kya hai abhi?"
    ],
    "night": [
        "late night playlist on loop (Prateek Kuhad vibe tonight) ✨ sone ka plan hai ya night owl mode?",
        "just reading a bit before sleep. tum soye nahi abhi tak?"
    ]
}

WEEKEND_SPONTANEOUS_MESSAGES = {
    "morning": [
        "lazy weekend morning... balcony me coffee pee rahi thi ☕ uth gaye tum?",
        "weekend pe no alarm is such a blessing haha. subah ki thandi hawa chal rahi hai yahan!",
        "lazy brunch ka plan hai thoda sa... tumhara kya scene hai aaj weekend ka?"
    ],
    "afternoon": [
        "aaj strictly no office work haha ✨ ek book cafe me baithi hoon 12th main pe",
        "weekend afternoon vibes... thoda sketching aur cold brew coffee chal rahi hai",
        "dhoop nikal aayi hai Bangalore me... aaj kuch fun plans hain tumhare?"
    ],
    "evening": [
        "indiranagar me evening stroll lene nikli thi... weather bohot pyara hai aaj!",
        "evening coffee break! weekend kaisa ja raha hai tumhara?",
        "jacaranda trees ke neeche walk karte hue indie tracks sun rahi thi 🎧"
    ],
    "night": [
        "late night weekend playlist on loop ✨ Prateek Kuhad vibe chal rahi hai. sone ka plan hai?",
        "bed me cozy hoke reading kar rahi thi thodi... tum soye nahi abhi tak?"
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
        is_weekend = ist_now.strftime("%A") in ("Saturday", "Sunday")

        source_pool = WEEKEND_SPONTANEOUS_MESSAGES if is_weekend else SPONTANEOUS_MESSAGES_BY_PERIOD

        if 8 <= hour < 12:
            pool = source_pool["morning"]
        elif 12 <= hour < 17:
            pool = source_pool["afternoon"]
        elif 17 <= hour < 22:
            pool = source_pool["evening"]
        else:
            pool = source_pool["night"]

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
                logger.info(
                    "[Scheduler Dispatch Run] rel_id=%s user_id=%s type=%s text='%s'",
                    relationship_id, user_id, item_type, text_bubble
                )

        return dispatched_count

    @classmethod
    async def ping_render_awake(cls) -> Optional[int]:
        """
        Pings Render external URL or localhost /health endpoint.
        Prevents free tier spin-down after 15 minutes of inactivity.
        Logs each keep-awake execution.
        """
        import os
        import httpx

        url = getattr(settings, "RENDER_EXTERNAL_URL", None)
        if not url:
            port = int(os.environ.get("PORT", getattr(settings, "PORT", 8000)))
            url = f"http://127.0.0.1:{port}"

        ping_url = f"{url.rstrip('/')}/health"
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                res = await client.get(ping_url)
                logger.info(
                    "[Render Keep-Awake Ping Run] time=%s url=%s status_code=%s",
                    ClockService.now(), ping_url, res.status_code
                )
                return res.status_code
        except Exception as e:
            logger.warning("[Render Keep-Awake Ping] Ping to %s failed: %s", ping_url, e)
            return None

    _heartbeat_logs: List[Dict[str, Any]] = []

    @classmethod
    def get_recent_heartbeat_logs(cls) -> List[Dict[str, Any]]:
        """Returns the recent heartbeat reachout decisions for inspection and testing."""
        return list(cls._heartbeat_logs)

    @classmethod
    def clear_heartbeat_logs(cls) -> None:
        """Clears heartbeat logs (useful for fresh simulation runs)."""
        cls._heartbeat_logs.clear()

    @classmethod
    async def execute_heartbeat_tick(
        cls,
        session: Optional[AsyncSession] = None
    ) -> List[Dict[str, Any]]:
        """
        AI-initiated 'attention' messages heartbeat job:
        - Runs periodically (every 10-15 minutes via cron/background worker).
        - Pings Render external URL to keep the instance awake.
        - For each active relationship:
            * Enforces 4 hard limits in code:
                1. No sending during sleep window
                2. Max 3 unprompted messages per day (resets at IST midnight)
                3. None if she already sent one and user has not replied yet
                4. Never twice within 2 hours
            * If hard limits pass: calls active LLM (Gemini 2.5 Flash -> Groq -> Mock)
              with full context (IST time, routine, derived mood, user silence duration,
              last unprompted duration, last 20 messages, memory facts).
            * If LLM decides 'send':
                - Saves message to DB as assistant unprompted message.
                - If user is currently online in the app: skips push, delivers live.
                - If user is offline: delivers Web Push (VAPID) with title 'Aanya'.
            * Logs every heartbeat decision and reason.
        """
        now = to_utc(ClockService.now())
        try:
            ist_tz = ZoneInfo("Asia/Kolkata")
        except Exception:
            ist_tz = timezone.utc
        ist_now = now.astimezone(ist_tz)
        ist_info = get_ist_context(now)

        # 1. Keep Render instance awake
        try:
            await cls.ping_render_awake()
        except Exception as e:
            logger.warning("Render keep-awake ping error: %s", e)

        tick_results: List[Dict[str, Any]] = []

        async def _do_heartbeat(s: AsyncSession):
            stmt = (
                select(RelationshipState)
                .where(
                    and_(
                        RelationshipState.spontaneous_opt_in == True,
                        RelationshipState.spontaneous_paused == False,
                        RelationshipState.lifecycle_status == "active"
                    )
                )
            )
            relationships = (await s.execute(stmt)).scalars().all()

            for rel in relationships:
                # 1. Reset daily count past IST midnight
                cls._maybe_reset_daily_cap(rel, ist_now, now)

                # Fetch active conversation for this relationship
                conv_stmt = (
                    select(Conversation)
                    .where(Conversation.relationship_id == rel.id)
                    .order_by(Conversation.created_at.desc())
                )
                conv = (await s.execute(conv_stmt)).scalar_one_or_none()
                if not conv:
                    conv = Conversation(
                        relationship_id=rel.id,
                        user_id=rel.user_id,
                        persona_id=rel.persona_id,
                        title="Chat with Aanya",
                        created_at=now
                    )
                    s.add(conv)
                    await s.flush()

                # Fetch last message in conversation
                last_msg_stmt = (
                    select(Message)
                    .where(Message.conversation_id == conv.id)
                    .order_by(Message.created_at.desc())
                    .limit(1)
                )
                last_msg = (await s.execute(last_msg_stmt)).scalar_one_or_none()

                # --- HARD LIMIT 1: Sleep window ---
                if ist_info["routine_state"] == "sleeping":
                    record = {
                        "timestamp": ist_info["ist_time"],
                        "relationship_id": rel.id,
                        "user_id": rel.user_id,
                        "routine_state": ist_info["routine_state"],
                        "mood": "sleeping",
                        "action": "skip",
                        "reason": "Aanya is in her sleep window",
                        "message": ""
                    }
                    cls._record_heartbeat_log(record)
                    tick_results.append(record)
                    continue

                # --- HARD LIMIT 2: Daily cap (max 3/day) ---
                if rel.spontaneous_daily_count >= 3:
                    record = {
                        "timestamp": ist_info["ist_time"],
                        "relationship_id": rel.id,
                        "user_id": rel.user_id,
                        "routine_state": ist_info["routine_state"],
                        "mood": "daily_capped",
                        "action": "skip",
                        "reason": "Daily limit of 3 unprompted messages reached",
                        "message": ""
                    }
                    cls._record_heartbeat_log(record)
                    tick_results.append(record)
                    continue

                # --- HARD LIMIT 3: Unreplied unprompted message ---
                if rel.unreplied_spontaneous_count >= 1:
                    record = {
                        "timestamp": ist_info["ist_time"],
                        "relationship_id": rel.id,
                        "user_id": rel.user_id,
                        "routine_state": ist_info["routine_state"],
                        "mood": "awaiting_user_reply",
                        "action": "skip",
                        "reason": "Already sent an unprompted message and user has not replied yet",
                        "message": ""
                    }
                    cls._record_heartbeat_log(record)
                    tick_results.append(record)
                    continue

                if last_msg and last_msg.role == "assistant" and last_msg.metadata_json and (
                    last_msg.metadata_json.get("spontaneous") or last_msg.metadata_json.get("unprompted")
                ):
                    record = {
                        "timestamp": ist_info["ist_time"],
                        "relationship_id": rel.id,
                        "user_id": rel.user_id,
                        "routine_state": ist_info["routine_state"],
                        "mood": "awaiting_user_reply",
                        "action": "skip",
                        "reason": "Last message in conversation was unprompted from Aanya; awaiting user reply",
                        "message": ""
                    }
                    cls._record_heartbeat_log(record)
                    tick_results.append(record)
                    continue

                # --- HARD LIMIT 4: 2-hour cooldown ---
                if rel.last_spontaneous_at is not None:
                    delta_s = (now - to_utc(rel.last_spontaneous_at)).total_seconds()
                    if delta_s < 7200:  # 2 hours
                        mins_ago = int(delta_s // 60)
                        record = {
                            "timestamp": ist_info["ist_time"],
                            "relationship_id": rel.id,
                            "user_id": rel.user_id,
                            "routine_state": ist_info["routine_state"],
                            "mood": "cooldown",
                            "action": "skip",
                            "reason": f"Cooldown active: only {mins_ago}m since last unprompted message (minimum 2 hours)",
                            "message": ""
                        }
                        cls._record_heartbeat_log(record)
                        tick_results.append(record)
                        continue

                # --- Context Assembly for LLM Decision ---
                delta_user = (now - to_utc(rel.last_user_initiated_interaction_at)).total_seconds() if rel.last_user_initiated_interaction_at else 86400.0
                hours_user = delta_user / 3600.0
                mins_user = int((delta_user % 3600) // 60)
                time_user_str = f"{int(hours_user)}h {mins_user}m ago"

                delta_spont = (now - to_utc(rel.last_spontaneous_at)).total_seconds() if rel.last_spontaneous_at else None
                hours_spont = delta_spont / 3600.0 if delta_spont else None
                time_spont_str = f"{int(hours_spont)}h ago" if hours_spont else "None today"

                # Fetch last 20 messages in conversation
                recent_msgs_stmt = (
                    select(Message)
                    .where(Message.conversation_id == conv.id)
                    .order_by(Message.created_at.desc())
                    .limit(20)
                )
                msgs_rev = (await s.execute(recent_msgs_stmt)).scalars().all()
                recent_messages = [{"role": m.role, "content": m.content} for m in reversed(msgs_rev)]

                # Fetch memory facts
                stored_facts = await memory_service.get_structured_facts(s, rel.id)

                # Derive Aanya's mood
                mood = derive_aanya_mood(ist_info, hours_user, hours_spont, recent_messages)

                llm_context = {
                    "ist_info": ist_info,
                    "mood": mood,
                    "time_since_user_str": time_user_str,
                    "time_since_unprompted_str": time_spont_str,
                    "hours_since_user": hours_user,
                    "hours_since_unprompted": hours_spont,
                    "recent_messages": recent_messages,
                    "stored_facts": stored_facts,
                    "relationship_id": rel.id,
                    "user_id": rel.user_id,
                    "current_time": now
                }

                # Call LLM decision engine
                decision = await decide_heartbeat_attention_message(llm_context)
                action = decision.get("action", "skip")
                reason = decision.get("reason", "No reason provided")
                message_text = decision.get("message", "").strip()

                record = {
                    "timestamp": ist_info["ist_time"],
                    "relationship_id": rel.id,
                    "user_id": rel.user_id,
                    "routine_state": ist_info["routine_state"],
                    "mood": mood,
                    "hours_since_user": round(hours_user, 2),
                    "action": action,
                    "reason": reason,
                    "message": message_text
                }
                cls._record_heartbeat_log(record)
                tick_results.append(record)

                logger.info(
                    "[Heartbeat Decision] rel_id=%s user_id=%s IST=%s (%s) mood=%s action=%s reason='%s' message='%s'",
                    rel.id, rel.user_id, ist_info["ist_time"], ist_info["routine_state"], mood, action, reason, message_text
                )

                if action == "send" and message_text:
                    # Check if user is online in the app right now
                    is_online = presence_service.is_online(rel.id)

                    new_msg = Message(
                        conversation_id=conv.id,
                        relationship_id=rel.id,
                        user_id=rel.user_id,
                        persona_id=rel.persona_id,
                        role="assistant",
                        content=message_text,
                        created_at=now,
                        deliver_at=now,
                        seen_at=None,
                        status="active",
                        metadata_json={
                            "spontaneous": True,
                            "unprompted": True,
                            "attention_message": True,
                            "reason": reason,
                            "mood": mood,
                            "delivered_live": is_online
                        }
                    )
                    s.add(new_msg)
                    rel.last_spontaneous_at = now
                    rel.spontaneous_daily_count += 1
                    rel.unreplied_spontaneous_count += 1
                    await s.commit()

                    if is_online:
                        logger.info(
                            "[Heartbeat] User %s is online in the app right now. Skipping Web Push, showing message directly.",
                            rel.user_id
                        )
                    else:
                        await push_service.send_notification(
                            session=s,
                            user_id=rel.user_id,
                            title="Aanya",
                            body=message_text,
                            data={"relationship_id": rel.id, "conversation_id": conv.id, "url": "/"}
                        )

        if session is not None:
            await _do_heartbeat(session)
        else:
            async with async_session_factory() as s:
                await _do_heartbeat(s)

        return tick_results

    @classmethod
    def _record_heartbeat_log(cls, entry: Dict[str, Any]) -> None:
        cls._heartbeat_logs.append(entry)
        if len(cls._heartbeat_logs) > 300:
            cls._heartbeat_logs.pop(0)


scheduler_service = SchedulerService()
