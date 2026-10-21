import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List
from sqlalchemy import select, and_, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from backend.app.db.models import (
    User, RelationshipState, Conversation, Message, SafetyEvent
)
from backend.app.db.session import to_utc
from backend.app.safety.crisis_detector import crisis_detector
from backend.app.safety.content_gate import content_gate
from backend.app.services.clock_service import ClockService
from backend.app.services.lifecycle_service import lifecycle_service
from backend.app.services.memory_service import memory_service
from backend.app.engine.adapter import (
    LLMAdapterFactory, mock_adapter, LLMResponse, calculate_pacing, get_activity_for_time
)


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

            # Step 4: Soft-Cancel any pending assistant chunks from previous interrupted turn
            cancel_stmt = (
                update(Message)
                .where(
                    and_(
                        Message.relationship_id == relationship.id,
                        Message.role == "assistant",
                        Message.status == "active",
                        Message.deliver_at > now
                    )
                )
                .values(status="cancelled")
            )
            await session.execute(cancel_stmt)

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
            recent_messages = [
                {"role": m.role, "content": m.content}
                for m in reversed(recent_msgs_raw)
            ]

            context = {
                "user_message": combined_text,
                "relationship_stage": relationship.relationship_stage,
                "lifecycle_status": relationship.lifecycle_status,
                "emotional_range": relationship.emotional_range_setting or {"enabled": True, "intensity": "realistic"},
                "memories": scoped_memories,
                "recent_messages": recent_messages,
                "is_ai_query": is_ai_query,
                "user_name": user.username,
                "user_city": user.city,
                "awaiting_city_reply": awaiting_city_reply,
                "current_time": now,
                "pacing_mode": pacing_mode
            }

            active_adapter = LLMAdapterFactory.get_adapter()
            response: LLMResponse = await active_adapter.generate_response(context)

            # If opening turn and user has no city, set awaiting_city_reply for next turn
            if relationship.relationship_stage == "encounter" and not user.city:
                fam_context["awaiting_city_reply"] = True
                relationship.familiarity_context = fam_context
                flag_modified(relationship, "familiarity_context")

            # Step 7: Calculate Authoritative Server Timestamps
            read_delay = response.read_delay_seconds
            seen_at = now + timedelta(seconds=read_delay)

            # Step 8: Persist User Messages
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

            # Step 9: Persist Assistant Chunks with Sequential deliver_at
            chunk_details = []
            cumulative_typing_offset = 0.0

            for idx, chunk_text in enumerate(response.chunks):
                typing_dur = response.typing_delays[idx] if idx < len(response.typing_delays) else 1.5
                cumulative_typing_offset += typing_dur
                chunk_deliver_at = seen_at + timedelta(seconds=cumulative_typing_offset)

                meta_json = {
                    "emotion": response.emotion_displayed,
                    "typing_duration": typing_dur
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

            # Step 10: Persist Extracted Memories from User Message
            user_msg_ids = [u.id for u in user_msg_records]
            for mem_data in response.extracted_memories:
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

            if response.stage_transition and response.stage_transition != relationship.relationship_stage:
                relationship.relationship_stage = response.stage_transition
                relationship.updated_at = now

            await session.commit()

            return {
                "role": "assistant",
                "content": response.reply_text,
                "chunks": response.chunks,
                "chunk_details": chunk_details,
                "crisis_handoff": None,
                "relationship_stage": response.stage_transition or relationship.relationship_stage,
                "lifecycle_status": relationship.lifecycle_status,
                "emotion": response.emotion_displayed,
                "persona_activity": response.persona_activity,
                "delay_tier": response.delay_tier,
                "read_delay_seconds": read_delay,
                "seen_at": seen_at
            }


orchestrator = Orchestrator()
