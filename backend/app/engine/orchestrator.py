from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.db.models import (
    User, RelationshipState, Conversation, Message, SafetyEvent
)
from backend.app.safety.crisis_detector import crisis_detector
from backend.app.safety.content_gate import content_gate
from backend.app.services.clock_service import ClockService
from backend.app.services.lifecycle_service import lifecycle_service
from backend.app.services.memory_service import memory_service
from backend.app.engine.adapter import mock_adapter, LLMResponse


class Orchestrator:
    """
    Coordinates the full message handling pipeline:
    Auth -> Crisis Pre-Check -> Inactivity Clock Reset -> Memory Retrieval ->
    Model/Template Adapter -> Content Guardrails -> Persistence.
    """

    @classmethod
    async def process_user_message(
        cls,
        session: AsyncSession,
        user: User,
        relationship: RelationshipState,
        conversation: Conversation,
        user_message: str
    ) -> Dict[str, Any]:
        raw_text = user_message.strip()

        # Step 1: Plain-Code Crisis Detection BEFORE Model
        is_crisis, crisis_meta = crisis_detector.check_message(raw_text)
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
            await session.commit()

            crisis_payload = crisis_detector.get_crisis_handoff_response()

            # Store assistant crisis response in history
            asst_msg = Message(
                conversation_id=conversation.id,
                relationship_id=relationship.id,
                user_id=user.id,
                persona_id=relationship.persona_id,
                role="assistant",
                content=crisis_payload["persona_text"],
                metadata_json={"crisis_handoff": True}
            )
            session.add(asst_msg)
            await session.commit()

            return {
                "role": "assistant",
                "content": crisis_payload["persona_text"],
                "crisis_handoff": crisis_payload,
                "relationship_stage": relationship.relationship_stage,
                "lifecycle_status": relationship.lifecycle_status
            }

        # Step 2: Content Boundary Screen (Minors / Locked Explicit Tier)
        allowed, boundary_reason = content_gate.screen_content_boundaries(raw_text)
        if not allowed:
            # Reject boundary violation
            return {
                "role": "assistant",
                "content": boundary_reason,
                "crisis_handoff": None,
                "relationship_stage": relationship.relationship_stage,
                "lifecycle_status": relationship.lifecycle_status
            }

        # Step 3: Reset Inactivity Clock (User-authored message)
        await lifecycle_service.record_user_interaction(session, relationship)

        # Step 4: Persist User Message
        user_msg_record = Message(
            conversation_id=conversation.id,
            relationship_id=relationship.id,
            user_id=user.id,
            persona_id=relationship.persona_id,
            role="user",
            content=raw_text,
            metadata_json={}
        )
        session.add(user_msg_record)
        await session.flush()

        # Step 5: Retrieve Scoped Memories
        scoped_memories = await memory_service.retrieve_relevant_memories(
            session=session,
            relationship_id=relationship.id,
            query=raw_text,
            limit=3
        )

        # Step 6: Check for sincere AI queries
        is_ai_query = content_gate.is_ai_sincerity_query(raw_text)

        # Step 7: Assemble Context and Generate Response
        context = {
            "user_message": raw_text,
            "relationship_stage": relationship.relationship_stage,
            "lifecycle_status": relationship.lifecycle_status,
            "emotional_range": relationship.emotional_range_setting or {"enabled": True, "intensity": "realistic"},
            "memories": scoped_memories,
            "is_ai_query": is_ai_query
        }

        response: LLMResponse = await mock_adapter.generate_response(context)

        # Step 8: Update Relationship Stage if transitioned
        if response.stage_transition:
            relationship.relationship_stage = response.stage_transition
            relationship.updated_at = ClockService.now()

        # Step 9: Persist Newly Extracted Memories
        for mem_data in response.extracted_memories:
            await memory_service.store_memory(
                session=session,
                relationship_id=relationship.id,
                user_id=user.id,
                persona_id=relationship.persona_id,
                memory_type=mem_data.get("type", "episodic"),
                content=mem_data.get("content", ""),
                source_message_ids=[user_msg_record.id],
                importance=mem_data.get("importance", 0.7)
            )

        # Step 10: Persist Newly Extracted Open Loops
        for loop_topic in response.extracted_open_loops:
            await memory_service.track_open_loop(
                session=session,
                relationship_id=relationship.id,
                user_id=user.id,
                persona_id=relationship.persona_id,
                topic=loop_topic
            )

        # Step 11: Persist Assistant Message
        asst_msg_record = Message(
            conversation_id=conversation.id,
            relationship_id=relationship.id,
            user_id=user.id,
            persona_id=relationship.persona_id,
            role="assistant",
            content=response.reply_text,
            metadata_json={"emotion": response.emotion_displayed}
        )
        session.add(asst_msg_record)
        await session.commit()

        return {
            "role": "assistant",
            "content": response.reply_text,
            "crisis_handoff": None,
            "relationship_stage": relationship.relationship_stage,
            "lifecycle_status": relationship.lifecycle_status,
            "emotion": response.emotion_displayed
        }


orchestrator = Orchestrator()
