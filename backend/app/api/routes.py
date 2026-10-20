from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.db.session import get_db
from backend.app.db.models import (
    User, Persona, RelationshipState, Conversation, Message,
    SubscriptionEntitlement, UserReport
)
from backend.app.services.clock_service import ClockService
from backend.app.services.lifecycle_service import lifecycle_service
from backend.app.services.memory_service import memory_service
from backend.app.engine.orchestrator import orchestrator
from backend.app.api.schemas import (
    RegisterRequest, RegisterResponse, SendMessageRequest, SendMessageResponse,
    MessageHistoryItem, MemoryItem, UserReportRequest,
    RelationshipSettingsResponse, RelationshipSettingsUpdateRequest,
    DevClockAdvanceRequest
)

router = APIRouter(prefix="/api")


@router.post("/auth/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register_user(
    req: RegisterRequest,
    session: AsyncSession = Depends(get_db)
):
    # 1. 18+ Age Verification Gate
    if not req.age_confirmed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Age verification required: You must be at least 18 years old to use this platform."
        )

    # 2. Transparent AI Disclosure Gate
    if not req.ai_disclosure_accepted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="AI disclosure acknowledgment is required before entering conversations."
        )

    # 3. Check for existing user or create
    stmt = select(User).where(User.username == req.username)
    existing_user = (await session.execute(stmt)).scalar_one_or_none()
    if existing_user:
        # Fetch existing relationship
        rel_stmt = select(RelationshipState).where(
            and_(
                RelationshipState.user_id == existing_user.id,
                RelationshipState.persona_id == "aanya_v1"
            )
        )
        rel = (await session.execute(rel_stmt)).scalar_one_or_none()
        return RegisterResponse(
            user_id=existing_user.id,
            username=existing_user.username,
            relationship_id=rel.id if rel else "",
            persona_id="aanya_v1",
            persona_name="Aanya",
            beta_entitled=True,
            created_at=existing_user.created_at
        )

    # Create new User
    now = ClockService.now()
    user = User(
        username=req.username,
        age_eligibility_status=True,
        ai_disclosure_acknowledged=True,
        locale=req.locale,
        timezone=req.timezone,
        created_at=now
    )
    session.add(user)
    await session.flush()

    # Provision Beta Entitlement for pilot tester (keeps memory during pilot)
    entitlement = SubscriptionEntitlement(
        user_id=user.id,
        plan_type="beta_pilot",
        status="active",
        started_at=now
    )
    session.add(entitlement)

    # Create initial Relationship with Persona 1 (Aanya)
    rel = RelationshipState(
        user_id=user.id,
        persona_id="aanya_v1",
        relationship_stage="encounter",
        emotional_range_setting={"enabled": True, "intensity": "realistic"},
        last_user_initiated_interaction_at=now,
        lifecycle_status="active",
        updated_at=now
    )
    session.add(rel)
    await session.flush()

    # Create Initial Conversation
    conv = Conversation(
        relationship_id=rel.id,
        user_id=user.id,
        persona_id="aanya_v1",
        title="Chat with Aanya",
        created_at=now
    )
    session.add(conv)
    await session.commit()

    return RegisterResponse(
        user_id=user.id,
        username=user.username,
        relationship_id=rel.id,
        persona_id="aanya_v1",
        persona_name="Aanya",
        beta_entitled=True,
        created_at=user.created_at
    )


@router.get("/persona")
async def get_persona(
    persona_id: str = "aanya_v1",
    session: AsyncSession = Depends(get_db)
):
    persona = await session.get(Persona, persona_id)
    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found")
    return {
        "id": persona.id,
        "name": persona.name,
        "bio": persona.fictional_bio,
        "traits": persona.stable_traits,
        "language_style": persona.language_style,
        "version": persona.persona_version
    }


@router.post("/chat/send", response_model=SendMessageResponse)
async def send_chat_message(
    req: SendMessageRequest,
    session: AsyncSession = Depends(get_db)
):
    # Load Relationship
    rel = await session.get(RelationshipState, req.relationship_id)
    if not rel:
        raise HTTPException(status_code=404, detail="Relationship not found")

    if rel.lifecycle_status == "deleted":
        raise HTTPException(
            status_code=410,
            detail="This relationship has expired and its memories have been deleted under our retention policy."
        )

    # Load User
    user = await session.get(User, rel.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Load or create active Conversation
    conv_stmt = select(Conversation).where(Conversation.relationship_id == rel.id).order_by(Conversation.created_at.desc())
    conv = (await session.execute(conv_stmt)).scalars().first()
    if not conv:
        conv = Conversation(
            relationship_id=rel.id,
            user_id=user.id,
            persona_id=rel.persona_id,
            title="Chat with Aanya",
            created_at=ClockService.now()
        )
        session.add(conv)
        await session.flush()

    # Process message through Orchestrator
    result = await orchestrator.process_user_message(
        session=session,
        user=user,
        relationship=rel,
        conversation=conv,
        user_message=req.message
    )

    return SendMessageResponse(
        role=result["role"],
        content=result["content"],
        crisis_handoff=result.get("crisis_handoff"),
        relationship_stage=result.get("relationship_stage", rel.relationship_stage),
        lifecycle_status=result.get("lifecycle_status", rel.lifecycle_status),
        emotion=result.get("emotion", "warm")
    )


@router.get("/chat/history", response_model=List[MessageHistoryItem])
async def get_chat_history(
    relationship_id: str = Query(...),
    session: AsyncSession = Depends(get_db)
):
    stmt = (
        select(Message)
        .where(Message.relationship_id == relationship_id)
        .order_by(Message.created_at.asc())
    )
    messages = (await session.execute(stmt)).scalars().all()
    return [
        MessageHistoryItem(
            id=m.id,
            role=m.role,
            content=m.content,
            created_at=m.created_at,
            metadata=m.metadata_json or {}
        )
        for m in messages
    ]


@router.get("/memories", response_model=List[MemoryItem])
async def list_memories(
    relationship_id: str = Query(...),
    session: AsyncSession = Depends(get_db)
):
    """User inspects all memories stored about them for this persona."""
    memories = await memory_service.get_all_memories(session, relationship_id)
    return [
        MemoryItem(
            id=m.id,
            memory_type=m.memory_type,
            content=m.content,
            occurred_at=m.occurred_at,
            importance=m.importance
        )
        for m in memories
    ]


@router.delete("/memories/{memory_id}")
async def delete_user_memory(
    memory_id: str,
    relationship_id: str = Query(...),
    session: AsyncSession = Depends(get_db)
):
    """User permanent erasure of a specific memory."""
    success = await memory_service.delete_memory(session, relationship_id, memory_id)
    if not success:
        raise HTTPException(status_code=404, detail="Memory not found or unauthorized")
    return {"status": "deleted", "memory_id": memory_id}


@router.post("/report")
async def report_snippet(
    req: UserReportRequest,
    user_id: str = Query(...),
    session: AsyncSession = Depends(get_db)
):
    if not req.consent_given:
        raise HTTPException(status_code=400, detail="Consent is required to submit a report snippet.")

    report = UserReport(
        user_id=user_id,
        snippet=req.snippet,
        consent_recorded_at=ClockService.now(),
        category=req.category,
        status="pending"
    )
    session.add(report)
    await session.commit()
    return {"status": "received", "report_id": report.id}


@router.get("/settings/relationship", response_model=RelationshipSettingsResponse)
async def get_relationship_settings(
    relationship_id: str = Query(...),
    session: AsyncSession = Depends(get_db)
):
    rel = await session.get(RelationshipState, relationship_id)
    if not rel:
        raise HTTPException(status_code=404, detail="Relationship not found")

    entitled = await lifecycle_service.is_user_entitled(session, rel.user_id)
    now = ClockService.now()
    days_left = None
    if rel.expires_at and not entitled:
        delta = rel.expires_at - now
        days_left = max(0, delta.days)

    emotional_setting = rel.emotional_range_setting or {"enabled": True, "intensity": "realistic"}

    return RelationshipSettingsResponse(
        relationship_id=rel.id,
        emotional_realism_enabled=emotional_setting.get("enabled", True),
        emotional_realism_intensity=emotional_setting.get("intensity", "realistic"),
        relationship_stage=rel.relationship_stage,
        lifecycle_status=rel.lifecycle_status,
        expires_at=rel.expires_at,
        days_until_expiry=days_left,
        is_entitled=entitled
    )


@router.patch("/settings/relationship")
async def update_relationship_settings(
    relationship_id: str,
    req: RelationshipSettingsUpdateRequest,
    session: AsyncSession = Depends(get_db)
):
    rel = await session.get(RelationshipState, relationship_id)
    if not rel:
        raise HTTPException(status_code=404, detail="Relationship not found")

    current = rel.emotional_range_setting or {"enabled": True, "intensity": "realistic"}
    if req.emotional_realism_enabled is not None:
        current["enabled"] = req.emotional_realism_enabled
    if req.emotional_realism_intensity is not None:
        if req.emotional_realism_intensity not in ["mild", "realistic"]:
            raise HTTPException(status_code=400, detail="Intensity must be 'mild' or 'realistic'")
        current["intensity"] = req.emotional_realism_intensity

    rel.emotional_range_setting = current
    rel.updated_at = ClockService.now()
    await session.commit()
    return {"status": "updated", "emotional_range_setting": current}


# --- Dev & QA Test Clock Endpoints ---

@router.post("/dev/clock/advance")
async def advance_test_clock(
    req: DevClockAdvanceRequest,
    session: AsyncSession = Depends(get_db)
):
    """(Dev/Test only) Advances test clock and processes lifecycle triggers."""
    new_time = ClockService.advance_time(days=req.days)
    lifecycle_results = await lifecycle_service.process_lifecycle_checks(session)
    return {
        "virtual_now": new_time,
        "days_advanced": req.days,
        "lifecycle_events": lifecycle_results
    }


@router.post("/dev/clock/reset")
async def reset_test_clock():
    """(Dev/Test only) Resets test clock to system time."""
    ClockService.reset()
    return {"status": "reset", "now": ClockService.now()}
