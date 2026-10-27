import asyncio
import re
import json
import uuid
import random
import logging
import httpx
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List
from sqlalchemy import select, and_, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from backend.app.core.config import settings
from backend.app.db.models import (
    User, RelationshipState, Conversation, Message, SafetyEvent, OpenLoop
)
from backend.app.db.session import async_session_factory, to_utc
from backend.app.safety.crisis_detector import crisis_detector
from backend.app.safety.content_gate import content_gate
from backend.app.services.clock_service import ClockService
from backend.app.services.lifecycle_service import lifecycle_service
from backend.app.services.memory_service import memory_service
from backend.app.services.continuity_service import continuity_service
from backend.app.services.presence_service import presence_service
from backend.app.services.push_service import push_service
from backend.app.engine.adapter import (
    LLMAdapterFactory, mock_adapter, LLMResponse, calculate_pacing, get_activity_for_time, _parse_llm_text_to_chunks
)
from backend.app.engine.persona import (
    validate_and_sanitize_response,
    fix_male_grammar,
    get_ist_context
)

logger = logging.getLogger(__name__)


class Orchestrator:
    """
    Coordinates the full message handling pipeline:
    Auth -> Concurrency Lock -> Crisis Pre-Check -> Inactivity Clock Reset ->
    Memory Retrieval -> Model/Template Adapter -> Content Guardrails ->
    Server Timestamps -> Lazy Side Effects -> Persistence.
    """

    _locks: Dict[str, asyncio.Lock] = {}

    @classmethod
    def get_lock(cls, relationship_id: str) -> asyncio.Lock:
        """
        In-memory per-relationship lock for single-worker deployment.
        Note: For future multi-worker scaling, replace with Redis or Postgres advisory lock.
        """
        if relationship_id not in cls._locks:
            cls._locks[relationship_id] = asyncio.Lock()
        return cls._locks[relationship_id]

    @classmethod
    async def _schedule_in_process_delivery(cls, message_id: str, relationship_id: str, deliver_at: datetime) -> None:
        """
        In-process precision delivery worker: sleeps until deliver_at, then delivers.
        If user is offline, triggers Web Push.
        """
        now = to_utc(ClockService.now())
        wait_seconds = max(0.0, (deliver_at - now).total_seconds())
        await asyncio.sleep(wait_seconds)
        try:
            async with async_session_factory() as session:
                msg = await session.get(Message, message_id)
                if msg and msg.status == "active":
                    if not presence_service.is_online(relationship_id):
                        rel = await session.get(RelationshipState, relationship_id)
                        if rel:
                            await push_service.send_push_notification(
                                session=session,
                                user_id=rel.user_id,
                                relationship_id=rel.id,
                                title="Aanya",
                                body=msg.content[:100]
                            )
        except Exception as e:
            logger.warning("In-process delivery worker exception: %s", e)

    @classmethod
    async def commit_delivered_side_effects(cls, session: AsyncSession, relationship_id: str) -> None:
        """
        Lazy trigger: Commits memory extraction, open loops, and stage transitions
        ONLY when an assistant chunk's deliver_at has arrived.
        Cancelled chunks or pending future chunks are never committed.
        """
        now = to_utc(ClockService.now())
        stmt = (
            select(Message)
            .where(
                and_(
                    Message.relationship_id == relationship_id,
                    Message.role == "assistant",
                    Message.status == "active",
                    Message.deliver_at <= now
                )
            )
            .order_by(Message.deliver_at.asc(), Message.sequence_order.asc())
        )
        delivered_messages = (await session.execute(stmt)).scalars().all()

        modified = False
        for msg in delivered_messages:
            meta = dict(msg.metadata_json or {})
            pending_memories = meta.pop("pending_memories", None)
            pending_open_loops = meta.pop("pending_open_loops", None)
            stage_transition = meta.pop("stage_transition", None)

            if pending_memories or pending_open_loops or stage_transition:
                # Commit memories
                if pending_memories:
                    for mem_data in pending_memories:
                        await memory_service.store_memory(
                            session=session,
                            relationship_id=relationship_id,
                            user_id=msg.user_id,
                            persona_id=msg.persona_id,
                            memory_type=mem_data.get("type", "episodic"),
                            content=mem_data.get("content", ""),
                            source_message_ids=[msg.id],
                            importance=mem_data.get("importance", 0.7)
                        )
                # Commit open loops
                if pending_open_loops:
                    for loop_topic in pending_open_loops:
                        await memory_service.track_open_loop(
                            session=session,
                            relationship_id=relationship_id,
                            user_id=msg.user_id,
                            persona_id=msg.persona_id,
                            topic=loop_topic
                        )
                # Apply stage transition
                if stage_transition:
                    rel = await session.get(RelationshipState, relationship_id)
                    if rel and rel.relationship_stage != stage_transition:
                        rel.relationship_stage = stage_transition
                        rel.updated_at = now

                msg.metadata_json = meta
                flag_modified(msg, "metadata_json")
                modified = True

        if modified:
            await session.commit()

    @classmethod
    async def skip_wait(cls, session: AsyncSession, relationship_id: str) -> List[Dict[str, Any]]:
        """
        Fast-forwards pending deliveries to NOW.
        Staggers assistant chunks by 50ms to maintain stable sequential ordering without collisions.
        """
        async with cls.get_lock(relationship_id):
            now = to_utc(ClockService.now())

            # Mark user messages as seen
            user_stmt = (
                select(Message)
                .where(
                    and_(
                        Message.relationship_id == relationship_id,
                        Message.role == "user",
                        Message.status == "active"
                    )
                )
            )
            user_msgs = (await session.execute(user_stmt)).scalars().all()
            for um in user_msgs:
                if not um.seen_at or to_utc(um.seen_at) > now:
                    um.seen_at = now

            # Stagger pending assistant chunks by 50ms
            asst_stmt = (
                select(Message)
                .where(
                    and_(
                        Message.relationship_id == relationship_id,
                        Message.role == "assistant",
                        Message.status == "active",
                        Message.deliver_at > now
                    )
                )
                .order_by(Message.sequence_order.asc(), Message.deliver_at.asc())
            )
            pending_asst = (await session.execute(asst_stmt)).scalars().all()
            total_pending = len(pending_asst)
            for idx, am in enumerate(pending_asst):
                # Stagger into the immediate past so deliver_at <= now is guaranteed, while maintaining strictly ascending order
                am.deliver_at = now - timedelta(milliseconds=(total_pending - idx) * 10)
                am.seen_at = now
                am.sequence_order = idx

            await session.commit()

            # Commit now-delivered side-effects
            await cls.commit_delivered_side_effects(session, relationship_id)

            return [
                {
                    "id": m.id,
                    "content": m.content,
                    "deliver_at": m.deliver_at,
                    "sequence_order": m.sequence_order
                }
                for m in pending_asst
            ]

    @classmethod
    async def process_user_message(
        cls,
        session: AsyncSession,
        user: User,
        relationship: RelationshipState,
        conversation: Conversation,
        user_message: Optional[str] = None,
        user_messages: Optional[List[str]] = None,
        pacing_mode: str = "realistic",
        client_msg_id: Optional[str] = None
    ) -> Dict[str, Any]:
        async with cls.get_lock(relationship.id):
            # Process lazy side effects first
            await cls.commit_delivered_side_effects(session, relationship.id)

            now = to_utc(ClockService.now())

            # Prepare message chunks
            raw_chunks: List[str] = []
            if user_messages:
                raw_chunks = [c.strip() for c in user_messages if c and c.strip()]
            elif user_message and user_message.strip():
                raw_chunks = [user_message.strip()]

            if not raw_chunks:
                raw_chunks = [""]

            combined_text = " ".join(raw_chunks).strip()

            # Idempotency check
            if client_msg_id:
                stmt_idemp = select(Message).where(
                    and_(
                        Message.relationship_id == relationship.id,
                        Message.client_msg_id == client_msg_id
                    )
                )
                existing = (await session.execute(stmt_idemp)).scalar_one_or_none()
                if existing:
                    return {
                        "role": "assistant",
                        "content": existing.content,
                        "chunks": [existing.content],
                        "chunk_details": [],
                        "crisis_handoff": None,
                        "relationship_stage": relationship.relationship_stage,
                        "lifecycle_status": relationship.lifecycle_status,
                        "emotion": "warm",
                        "persona_activity": "Online",
                        "delay_tier": "quick",
                        "read_delay_seconds": 0.0,
                        "seen_at": now
                    }

            # Step 1: Plain-Code Crisis Detection on Chunks AND Concatenated Burst
            is_crisis = False
            crisis_meta = None
            for chunk in raw_chunks:
                is_c, c_meta = crisis_detector.check_message(chunk)
                if is_c:
                    is_crisis = True
                    crisis_meta = c_meta
                    break

            if not is_crisis:
                is_crisis, crisis_meta = crisis_detector.check_message(combined_text)

            # Step 1b: Tier 2 Ambiguous Distress Detection (gentle soft check-in)
            is_ambiguous_distress = False
            if not is_crisis:
                for chunk in raw_chunks:
                    if crisis_detector.check_ambiguous_distress(chunk):
                        is_ambiguous_distress = True
                        break
                if not is_ambiguous_distress:
                    is_ambiguous_distress = crisis_detector.check_ambiguous_distress(combined_text)

            if is_crisis:
                # STRICT COMPLIANCE: Log only metadata, NEVER user message text
                safety_event = SafetyEvent(
                    user_id=user.id,
                    event_type="crisis_signal",
                    severity=crisis_meta.get("severity", "critical") if crisis_meta else "critical",
                    handoff_shown=True,
                    metadata_json=crisis_meta or {"type": "crisis_detected"}
                )
                session.add(safety_event)

                crisis_payload = crisis_detector.get_crisis_handoff_response()

                # Persist user messages with deliver_at=now, seen_at=now
                for idx, chunk in enumerate(raw_chunks):
                    session.add(Message(
                        conversation_id=conversation.id,
                        relationship_id=relationship.id,
                        user_id=user.id,
                        persona_id=relationship.persona_id,
                        role="user",
                        content=chunk,
                        created_at=now,
                        deliver_at=now,
                        seen_at=now,
                        status="active",
                        sequence_order=idx,
                        client_msg_id=client_msg_id if idx == 0 else None
                    ))

                # Store assistant crisis response with 0ms delay (deliver_at=now, seen_at=now)
                asst_msg = Message(
                    conversation_id=conversation.id,
                    relationship_id=relationship.id,
                    user_id=user.id,
                    persona_id=relationship.persona_id,
                    role="assistant",
                    content=crisis_payload["persona_text"],
                    created_at=now,
                    deliver_at=now,
                    seen_at=now,
                    status="active",
                    sequence_order=len(raw_chunks),
                    metadata_json={"crisis_handoff": True}
                )
                session.add(asst_msg)
                await session.commit()

                return {
                    "role": "assistant",
                    "content": crisis_payload["persona_text"],
                    "chunks": [crisis_payload["persona_text"]],
                    "chunk_details": [{
                        "content": crisis_payload["persona_text"],
                        "deliver_at": now,
                        "typing_duration_seconds": 0.0,
                        "sequence_order": 0
                    }],
                    "crisis_handoff": crisis_payload,
                    "relationship_stage": relationship.relationship_stage,
                    "lifecycle_status": relationship.lifecycle_status,
                    "emotion": "honest",
                    "persona_activity": "Immediate Support",
                    "delay_tier": "quick",
                    "read_delay_seconds": 0.0,
                    "seen_at": now
                }

            # Step 2: Content Boundary Screen on All Chunks
            for chunk in raw_chunks:
                allowed, boundary_reason = content_gate.screen_content_boundaries(chunk)
                if not allowed:
                    return {
                        "role": "assistant",
                        "content": boundary_reason,
                        "chunks": [boundary_reason],
                        "chunk_details": [{
                            "content": boundary_reason,
                            "deliver_at": now,
                            "typing_duration_seconds": 0.0,
                            "sequence_order": 0
                        }],
                        "crisis_handoff": None,
                        "relationship_stage": relationship.relationship_stage,
                        "lifecycle_status": relationship.lifecycle_status,
                        "emotion": "warm",
                        "persona_activity": "Online",
                        "delay_tier": "quick",
                        "read_delay_seconds": 0.0,
                        "seen_at": now
                    }

            # Step 3: Reset Inactivity Clock (User-authored message)
            await lifecycle_service.record_user_interaction(session, relationship)

            # Inspect active open loops for left-hanging context
            active_loops = await memory_service.get_open_loops(session, relationship.id)
            passed_open_loops = []
            if active_loops:
                # Check if user message explicitly addressed the prior sleep/drop-off
                user_msg_addressed = bool(re.search(
                    r"\b(kal raat|so gayi thi|so gaya tha|neend aa gayi|chalo so jao|so jao|goodnight|gn|no problem|koi baat nahi|koi na)\b",
                    combined_text, re.IGNORECASE
                ))
                if user_msg_addressed:
                    for ol in active_loops:
                        await memory_service.resolve_open_loop(session, ol.id)
                else:
                    # Pass open loop with 70-80% likelihood per approved plan
                    if random.random() < getattr(settings, "OPEN_LOOP_FOLLOWUP_PROBABILITY", 0.75):
                        top_loop = active_loops[0]
                        delta_ol = (now - to_utc(top_loop.last_relevant_at)).total_seconds() if top_loop.last_relevant_at else 0
                        time_desc = f"{int(delta_ol // 3600)}h ago" if delta_ol >= 3600 else f"{int(delta_ol // 60)}m ago"
                        passed_open_loops.append({
                            "id": top_loop.id,
                            "user_message": top_loop.user_message or top_loop.topic,
                            "persona_state": top_loop.persona_state_at_time or "sleeping",
                            "time_str": time_desc
                        })

            # Reset unreplied counter and unpause spontaneous reachouts
            relationship.unreplied_spontaneous_count = 0
            relationship.spontaneous_paused = False

            # Active flow & precise sign-off detection
            last_msg_stmt = (
                select(Message)
                .where(Message.relationship_id == relationship.id)
                .order_by(Message.created_at.desc())
                .limit(1)
            )
            last_msg = (await session.execute(last_msg_stmt)).scalar_one_or_none()
            last_msg_delta = (now - to_utc(last_msg.created_at)).total_seconds() if last_msg and last_msg.created_at else 999999.0

            SIGNOFF_PATTERN = re.compile(
                r"\b(chal bye|chalo bye|bye bye|bye yaar|bye tc|take care|see ya|cya|baad me milte|baad me baat karte|nikal rha hu|nikal raha hu|nikal gaya|nikal rhi hu)\b",
                re.IGNORECASE
            )
            is_signoff = bool(SIGNOFF_PATTERN.search(combined_text))
            in_active_flow = (last_msg_delta < 210) and not is_signoff
            delay_tier_override = "quick_signoff" if is_signoff else ("quick" if in_active_flow else None)

            # Step 4: Soft-Cancel pending assistant chunks & merge unreplied user messages
            pending_stmt = (
                select(Message)
                .where(
                    and_(
                        Message.relationship_id == relationship.id,
                        Message.role == "assistant",
                        Message.status == "active",
                        Message.deliver_at > now
                    )
                )
                .order_by(Message.deliver_at.asc())
            )
            pending_asst_msgs = (await session.execute(pending_stmt)).scalars().all()
            if pending_asst_msgs:
                for p_msg in pending_asst_msgs:
                    p_msg.status = "cancelled"

                # Find unreplied user messages that arrived while reply was pending
                prev_unreplied_stmt = (
                    select(Message)
                    .where(
                        and_(
                            Message.relationship_id == relationship.id,
                            Message.role == "user",
                            Message.status == "active",
                            Message.created_at >= (pending_asst_msgs[0].created_at - timedelta(minutes=15))
                        )
                    )
                    .order_by(Message.created_at.asc(), Message.sequence_order.asc())
                )
                prev_user_msgs = (await session.execute(prev_unreplied_stmt)).scalars().all()
                prev_texts = [m.content for m in prev_user_msgs if m.content and m.content not in raw_chunks]
                if prev_texts:
                    combined_text = " ".join(prev_texts + raw_chunks).strip()

            # Step 5: City detection / One-shot awaiting_city_reply lifecycle
            fam_context = dict(relationship.familiarity_context or {})
            awaiting_city_reply = fam_context.get("awaiting_city_reply", False)
            if awaiting_city_reply:
                # Strictly clear flag on this turn so it never runs again
                fam_context["awaiting_city_reply"] = False
                relationship.familiarity_context = fam_context
                flag_modified(relationship, "familiarity_context")

            # Check for sincere AI queries
            is_ai_query = content_gate.is_ai_sincerity_query(combined_text) or any(
                content_gate.is_ai_sincerity_query(c) for c in raw_chunks
            )

            # Step 5b: Extract and Store Facts from User Message
            extracted_user_facts = memory_service.extract_user_facts(combined_text)
            for fact in extracted_user_facts:
                if fact["type"] == "user_name":
                    user.username = fact["content"].replace("User's name is ", "").strip()
                elif fact["type"] == "user_city":
                    user.city = fact["content"].replace("User lives in ", "").strip()
                await memory_service.store_memory(
                    session=session,
                    relationship_id=relationship.id,
                    user_id=user.id,
                    persona_id=relationship.persona_id,
                    memory_type=fact["type"],
                    content=fact["content"],
                    importance=fact.get("importance", 0.8)
                )

            # Retrieve structured facts for consistent context injection
            structured_facts = await memory_service.get_structured_facts(session, relationship.id)

            # Retrieve scoped memories
            scoped_memories = await memory_service.retrieve_relevant_memories(
                session=session,
                relationship_id=relationship.id,
                query=combined_text,
                limit=3
            )

            # Step 6: Assemble Context & Generate Model Chunks
            # Retrieve recent active conversation history for multi-turn dialogue context
            recent_msgs_stmt = (
                select(Message)
                .where(
                    and_(
                        Message.relationship_id == relationship.id,
                        Message.status == "active"
                    )
                )
                .order_by(Message.created_at.desc(), Message.sequence_order.desc())
                .limit(8)
            )
            recent_msgs_raw = (await session.execute(recent_msgs_stmt)).scalars().all()
            # Filter out glitch fallback messages so prompt history is never polluted
            recent_messages = [
                {"role": m.role, "content": m.content}
                for m in reversed(recent_msgs_raw)
                if not (m.metadata_json or {}).get("is_glitch_fallback")
            ]

            # Database-backed rate limiting check for remote LLM
            from backend.app.services.rate_limiter_service import rate_limiter_service
            is_allowed, rl_reason = await rate_limiter_service.check_and_increment(
                session=session,
                user_id=user.id,
                max_per_minute=getattr(settings, "RATE_LIMIT_PER_MINUTE", 6),
                max_per_day=getattr(settings, "RATE_LIMIT_PER_DAY", 40)
            )

            # Fetch today's continuity notes up to current time (Section C)
            daily_notes = await continuity_service.get_daily_notes_for_time(session, relationship.persona_id, now)

            # Query last 15 assistant messages for "things you already said"
            past_asst_stmt = (
                select(Message)
                .where(
                    and_(
                        Message.relationship_id == relationship.id,
                        Message.role == "assistant",
                        Message.status == "active"
                    )
                )
                .order_by(Message.created_at.desc(), Message.sequence_order.desc())
                .limit(15)
            )
            past_asst_rows = (await session.execute(past_asst_stmt)).scalars().all()
            things_already_said = [m.content for m in reversed(past_asst_rows) if m.content and m.content.strip()]

            # Availability state & propensity hints
            ist_ctx = get_ist_context(now)
            routine_state = ist_ctx.get("routine_state", "free")
            propensity_dict = getattr(settings, "PROPENSITY_HINTS", {}).get(routine_state, {})
            propensity_hint_str = ", ".join(f"{k}: {v}%" for k, v in propensity_dict.items())

            context = {
                "user_message": combined_text,
                "relationship_id": relationship.id,
                "delay_tier_override": delay_tier_override,
                "relationship_stage": relationship.relationship_stage,
                "lifecycle_status": relationship.lifecycle_status,
                "emotional_range": {"enabled": False, "intensity": "suppressed"} if is_ambiguous_distress else (
                    relationship.emotional_range_setting or {"enabled": True, "intensity": "realistic"}
                ),
                "is_ambiguous_distress": is_ambiguous_distress,
                "memories": scoped_memories,
                "stored_facts": structured_facts,
                "daily_notes": daily_notes,
                "things_already_said": things_already_said,
                "open_loops": passed_open_loops,
                "propensity_hint": propensity_hint_str,
                "recent_messages": recent_messages,
                "is_ai_query": is_ai_query,
                "user_name": user.username,
                "user_city": user.city,
                "awaiting_city_reply": awaiting_city_reply,
                "current_time": now,
                "pacing_mode": pacing_mode
            }

            if not is_allowed:
                # DB rate limit exceeded -> serve from offline mock engine
                active_adapter = mock_adapter
            else:
                active_adapter = LLMAdapterFactory.get_adapter()

            response: LLMResponse = await active_adapter.generate_response(context)
            if "network thoda glitch" in response.reply_text.lower():
                response = await mock_adapter.generate_response(context)

            # Post-check validation and fact contradiction check
            recent_asst_msgs = [m.get("content", "") for m in recent_messages if m.get("role") in ("assistant", "model")]
            sanitized_chunks = []
            seen_chunk_norms = set()
            for c in response.chunks:
                _, san, _ = validate_and_sanitize_response(str(c), recent_asst_msgs, combined_text, structured_facts)
                san = fix_male_grammar(san).strip()
                norm = re.sub(r"[^\w\s]", "", san.lower()).strip()
                if san and norm not in seen_chunk_norms:
                    seen_chunk_norms.add(norm)
                    sanitized_chunks.append(san)
            response.chunks = sanitized_chunks
            response.reply_text = " ".join(sanitized_chunks)

            # Extract and store persona facts from assistant response
            if response.reply_text:
                extracted_persona_facts = memory_service.extract_persona_facts(response.reply_text)
                for p_fact in extracted_persona_facts:
                    await memory_service.store_memory(
                        session=session,
                        relationship_id=relationship.id,
                        user_id=user.id,
                        persona_id=relationship.persona_id,
                        memory_type=p_fact["type"],
                        content=p_fact["content"],
                        importance=p_fact.get("importance", 0.6)
                    )

            # If opening turn and user has no city, set awaiting_city_reply for next turn
            if relationship.relationship_stage == "encounter" and not user.city:
                fam_context["awaiting_city_reply"] = True
                relationship.familiarity_context = fam_context
                flag_modified(relationship, "familiarity_context")

            # Step 7: Calculate Authoritative Server Timestamps & Availability Timing
            action = getattr(response, "availability_action", "reply_now")
            model_delay = getattr(response, "delay_seconds", 0.0)

            # 1. Base Seen Delay (when she opens the chat on mobile)
            if routine_state == "free":
                seen_delay_sec = random.uniform(settings.SEEN_DELAY_FREE_MIN, settings.SEEN_DELAY_FREE_MAX)
            elif routine_state == "working":
                seen_delay_sec = random.uniform(settings.SEEN_DELAY_BUSY_MIN, settings.SEEN_DELAY_BUSY_MAX)
            elif routine_state == "sleeping":
                seen_delay_sec = random.uniform(settings.SEEN_DELAY_SLEEPING_MIN, settings.REPLY_DELAY_SLEEPING_MAX)
            else:
                seen_delay_sec = random.uniform(settings.SEEN_DELAY_FREE_MIN, settings.SEEN_DELAY_FREE_MAX)

            # 2. Base Reply Delay
            if action == "ignore_until_free":
                delay_sec = 0.0
            elif action == "reply_later":
                if model_delay > 0:
                    delay_sec = model_delay
                else:
                    if routine_state == "working":
                        delay_sec = random.uniform(settings.REPLY_DELAY_BUSY_MIN, settings.REPLY_DELAY_BUSY_MAX)
                    elif routine_state == "sleeping":
                        delay_sec = random.uniform(settings.REPLY_DELAY_SLEEPING_MIN, settings.REPLY_DELAY_SLEEPING_MAX)
                    else:
                        delay_sec = random.uniform(settings.REPLY_DELAY_MODERATE_MIN, settings.REPLY_DELAY_MODERATE_MAX)
            else:  # reply_now
                # 5-10% chance of long gap even when free
                if routine_state == "free" and random.random() < getattr(settings, "FREE_LONG_GAP_CHANCE", 0.08):
                    delay_sec = random.uniform(settings.FREE_LONG_GAP_MIN, settings.FREE_LONG_GAP_MAX)
                elif in_active_flow:
                    delay_sec = random.uniform(1.2, 2.5)
                else:
                    delay_sec = random.uniform(settings.REPLY_DELAY_QUICK_MIN, settings.REPLY_DELAY_QUICK_MAX)

            if pacing_mode == "turbo":
                delay_sec = 0.0
                seen_delay_sec = 0.0

            # CRITICAL INVARIANT: seen_at <= deliver_at ALWAYS (If she replies, she must have seen it first)
            has_reply = bool(action != "ignore_until_free" and response.chunks)
            if has_reply:
                if seen_delay_sec > delay_sec:
                    seen_delay_sec = max(0.0 if pacing_mode == "turbo" else 0.5, delay_sec - (0.0 if pacing_mode == "turbo" else 0.5))

            seen_at = now + timedelta(seconds=seen_delay_sec)

            # Step 8: Persist User Messages (seen_at reflects when she actually opens chat)
            user_msg_records = []
            for idx, chunk in enumerate(raw_chunks):
                u_rec = Message(
                    conversation_id=conversation.id,
                    relationship_id=relationship.id,
                    user_id=user.id,
                    persona_id=relationship.persona_id,
                    role="user",
                    content=chunk,
                    created_at=now,
                    deliver_at=now,
                    seen_at=seen_at,
                    status="active",
                    sequence_order=idx,
                    client_msg_id=client_msg_id if idx == 0 else None
                )
                session.add(u_rec)
                user_msg_records.append(u_rec)
            await session.flush()

            # Step 9: Persist Assistant Chunks with Sequential deliver_at & generation idempotency
            chunk_details = []
            cumulative_typing_offset = 0.0
            generation_id = str(uuid.uuid4())

            if has_reply:
                for idx, chunk_text in enumerate(response.chunks):
                    typing_dur = 0.0 if pacing_mode == "turbo" else max(0.8, min(2.5, round(len(chunk_text) * 0.028, 2)))
                    cumulative_typing_offset += typing_dur
                    chunk_deliver_at = now + timedelta(seconds=delay_sec + cumulative_typing_offset)

                    meta_json = {
                        "provider": getattr(response, "provider", "gemini"),
                        "model": getattr(response, "model", "default"),
                        "availability_action": action,
                        "delay_seconds": delay_sec,
                        "typing_duration": typing_dur,
                        "generation_id": generation_id
                    }

                    asst_rec = Message(
                        conversation_id=conversation.id,
                        relationship_id=relationship.id,
                        user_id=user.id,
                        persona_id=relationship.persona_id,
                        role="assistant",
                        content=chunk_text,
                        created_at=now,
                        deliver_at=chunk_deliver_at,
                        seen_at=seen_at,
                        status="active",
                        sequence_order=idx,
                        metadata_json=meta_json
                    )
                    session.add(asst_rec)
                    chunk_details.append({
                        "content": chunk_text,
                        "deliver_at": chunk_deliver_at,
                        "typing_duration_seconds": typing_dur,
                        "sequence_order": idx
                    })

                    # Schedule in-process precision delivery worker
                    asyncio.create_task(cls._schedule_in_process_delivery(asst_rec.id, relationship.id, chunk_deliver_at))

                # If an open loop was passed and Aanya replied, resolve it so it never repeats
                if passed_open_loops:
                    for ol_item in passed_open_loops:
                        await memory_service.resolve_open_loop(session, ol_item["id"])

            logger.info(
                "[LLM] Message turn completed: provider=%s model=%s action=%s delay=%.1fs seen_in=%.1fs chunks=%d",
                getattr(response, "provider", "gemini"),
                getattr(response, "model", "default"),
                action,
                delay_sec,
                seen_delay_sec,
                len(chunk_details)
            )

            # Step 10: Persist Extracted Memories from User Message
            memories_to_store = list(response.extracted_memories)
            msg_lower = combined_text.lower()
            if "interview" in msg_lower or "job" in msg_lower:
                if not any("interview" in m.get("content", "").lower() for m in memories_to_store):
                    memories_to_store.append({
                        "type": "episodic",
                        "content": f"User mentioned work/interview event: '{combined_text}'",
                        "importance": 0.9
                    })

            user_msg_ids = [u.id for u in user_msg_records]
            for mem_data in memories_to_store:
                await memory_service.store_memory(
                    session=session,
                    relationship_id=relationship.id,
                    user_id=user.id,
                    persona_id=relationship.persona_id,
                    memory_type=mem_data.get("type", "episodic"),
                    content=mem_data.get("content", ""),
                    source_message_ids=user_msg_ids,
                    importance=mem_data.get("importance", 0.7)
                )

            for loop_topic in response.extracted_open_loops:
                await memory_service.track_open_loop(
                    session=session,
                    relationship_id=relationship.id,
                    user_id=user.id,
                    persona_id=relationship.persona_id,
                    topic=loop_topic
                )

            # Synchronous open-loop extraction & deduplication in same transaction
            OPEN_LOOP_GATE = re.compile(
                r"\b(pahunch|pahuch|pohoch|reach|call back|msg karta|text karta|baat karta|baat krta|aadhe ghante|ghante me)\b",
                re.IGNORECASE
            )
            if OPEN_LOOP_GATE.search(combined_text):
                await cls._extract_and_store_open_loop(
                    session=session,
                    relationship=relationship,
                    user=user,
                    text=combined_text,
                    now=now
                )

            # State-driven open loop tracking (Per approved Round 3 Realism Plan modification 5)
            # Create open loop if: user message while asleep, ignored, delayed > 3h, or LLM flagged open_loop
            is_state_open_loop = (
                routine_state == "sleeping"
                or action == "ignore_until_free"
                or delay_sec >= 10800
                or bool(getattr(response, "open_loop", False))
            )
            if is_state_open_loop:
                loop_topic = "sleep_dropoff" if routine_state == "sleeping" else ("left_on_read" if action == "ignore_until_free" else "delayed_followup")
                loop_type = "sleep_dropoff" if routine_state == "sleeping" else "delayed_reply"

                existing_loop_stmt = (
                    select(OpenLoop)
                    .where(
                        and_(
                            OpenLoop.relationship_id == relationship.id,
                            OpenLoop.status == "open",
                            OpenLoop.loop_type == loop_type
                        )
                    )
                    .order_by(OpenLoop.last_relevant_at.desc())
                    .limit(1)
                )
                existing_loop = (await session.execute(existing_loop_stmt)).scalar_one_or_none()
                if existing_loop:
                    existing_loop.user_message = combined_text[:500]
                    existing_loop.persona_state_at_time = routine_state
                    existing_loop.last_relevant_at = now
                    existing_loop.expires_at = now + timedelta(hours=getattr(settings, "OPEN_LOOP_EXPIRY_HOURS", 36))
                else:
                    await memory_service.track_open_loop(
                        session=session,
                        relationship_id=relationship.id,
                        user_id=user.id,
                        persona_id=relationship.persona_id,
                        topic=loop_topic,
                        user_message=combined_text[:500],
                        persona_state_at_time=routine_state,
                        loop_type=loop_type,
                        expires_at=now + timedelta(hours=getattr(settings, "OPEN_LOOP_EXPIRY_HOURS", 36))
                    )

            if response.stage_transition and response.stage_transition != relationship.relationship_stage:
                relationship.relationship_stage = response.stage_transition
                relationship.updated_at = now

            await session.commit()

            total_estimated_wait = delay_sec + cumulative_typing_offset
            show_skip_wait = (
                not in_active_flow
                and delay_tier_override != "quick_signoff"
                and (action == "reply_later" or getattr(response, "delay_tier", "") == "busy" or delay_sec >= 15.0)
                and total_estimated_wait >= 5.0
            )

            content_str = response.reply_text if getattr(response, "reply_text", None) else (" ".join(response.chunks) if response.chunks else "")

            return {
                "role": "assistant",
                "content": content_str,
                "chunks": response.chunks,
                "chunk_details": chunk_details,
                "crisis_handoff": None,
                "relationship_stage": response.stage_transition or relationship.relationship_stage,
                "lifecycle_status": relationship.lifecycle_status,
                "emotion": getattr(response, "emotion_displayed", "neutral"),
                "persona_activity": getattr(response, "persona_activity", "relaxing"),
                "delay_tier": getattr(response, "delay_tier", "quick"),
                "read_delay_seconds": delay_sec,
                "delay_seconds": delay_sec,
                "seen_at": seen_at,
                "show_skip_wait": show_skip_wait
            }

    @classmethod
    async def _extract_and_store_open_loop(
        cls,
        session: AsyncSession,
        relationship: RelationshipState,
        user: User,
        text: str,
        now: datetime
    ) -> None:
        """
        Extracts departure/commute promises (clamped to 15-240 min)
        and dedupes in-place into open_loops table.
        """
        expected_minutes = 80
        topic = "arrival_checkin"
        has_promise = False

        # 1. Deterministic Regex Fallback
        text_lower = text.lower()
        if any(w in text_lower for w in ["office", "ofc"]):
            has_promise = True
            topic = "office_arrival"
            expected_minutes = 80
        elif any(w in text_lower for w in ["ghar", "home"]):
            has_promise = True
            topic = "home_arrival"
            expected_minutes = 60
        elif "aadhe ghante" in text_lower:
            has_promise = True
            topic = "short_errand"
            expected_minutes = 35
        elif any(w in text_lower for w in ["pahunch", "pahuch", "pohoch", "reach"]):
            has_promise = True
            topic = "general_arrival"
            expected_minutes = 75

        # 2. Try compact LLM extraction if Groq API is configured
        if getattr(settings, "GROQ_API_KEY", None):
            try:
                prompt_messages = [
                    {
                        "role": "system",
                        "content": (
                            "Extract user departure commitment or promise. "
                            "Output pure JSON only: {\"has_promise\": bool, \"topic\": str, \"expected_minutes\": int}. "
                            "No other words."
                        )
                    },
                    {"role": "user", "content": text}
                ]
                headers = {
                    "Authorization": f"Bearer {settings.GROQ_API_KEY}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": getattr(settings, "GROQ_MODEL", "qwen/qwen3.8-27b") or "qwen/qwen3.8-27b",
                    "messages": prompt_messages,
                    "max_tokens": 80,
                    "temperature": 0.1
                }
                async with httpx.AsyncClient(timeout=4.0) as client:
                    resp = await client.post("https://api.groq.com/openai/v1/chat/completions", json=payload, headers=headers)
                    if resp.status_code == 200:
                        raw_c = resp.json()["choices"][0]["message"].get("content", "")
                        clean_json = raw_c.strip()
                        if "{" in clean_json and "}" in clean_json:
                            clean_json = clean_json[clean_json.find("{"):clean_json.rfind("}")+1]
                            parsed = json.loads(clean_json)
                            if parsed.get("has_promise"):
                                has_promise = True
                                topic = parsed.get("topic") or topic
                                val_min = parsed.get("expected_minutes")
                                if isinstance(val_min, (int, float)):
                                    expected_minutes = int(val_min)
            except Exception:
                # Malformed JSON or timeout -> keep clamped default
                pass

        if not has_promise:
            return

        # Clamp expected_minutes between 15 and 240
        clamped_minutes = max(15, min(240, expected_minutes))
        review_time = now + timedelta(minutes=clamped_minutes)

        # Dedupe check: update existing open loop if open, else create
        stmt = (
            select(OpenLoop)
            .where(
                and_(
                    OpenLoop.relationship_id == relationship.id,
                    OpenLoop.status == "open"
                )
            )
        )
        existing = (await session.execute(stmt)).scalars().first()
        if existing:
            existing.topic = topic
            existing.next_review_at = review_time
            existing.last_relevant_at = now
        else:
            new_loop = OpenLoop(
                relationship_id=relationship.id,
                user_id=user.id,
                persona_id=relationship.persona_id,
                topic=topic,
                status="open",
                last_relevant_at=now,
                next_review_at=review_time
            )
            session.add(new_loop)


orchestrator = Orchestrator()
