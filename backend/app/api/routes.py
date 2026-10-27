import logging
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, BackgroundTasks, status
from sqlalchemy import select, and_, text
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.config import settings
from backend.app.db.session import get_db, to_utc, engine, init_db
from backend.app.db.models import (
    User, Persona, RelationshipState, Conversation, Message,
    SubscriptionEntitlement, UserReport
)
from backend.app.services.clock_service import ClockService
from backend.app.services.lifecycle_service import lifecycle_service
from backend.app.services.memory_service import memory_service
from backend.app.services.scheduler_service import scheduler_service
from backend.app.services.push_service import push_service
from backend.app.services.presence_service import presence_service
from backend.app.engine.orchestrator import orchestrator
from backend.app.engine.adapter import get_activity_for_time
from backend.app.api.schemas import (
    RegisterRequest, RegisterResponse, SendMessageRequest, SendMessageResponse,
    MessageHistoryItem, ChatHistoryResponse, SkipWaitRequest, MemoryItem, UserReportRequest,
    RelationshipSettingsResponse, RelationshipSettingsUpdateRequest,
    DevClockAdvanceRequest, PushSubscribeRequest, TickResponse
)

logger = logging.getLogger(__name__)

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
        now = ClockService.now()
        if req.city and req.city.strip():
            existing_user.city = req.city.strip()

        # Fetch existing relationship
        rel_stmt = select(RelationshipState).where(
            and_(
                RelationshipState.user_id == existing_user.id,
                RelationshipState.persona_id == "aanya_v1"
            )
        )
        rel = (await session.execute(rel_stmt)).scalar_one_or_none()
        if not rel or rel.lifecycle_status == "deleted":
            rel = RelationshipState(
                user_id=existing_user.id,
                persona_id="aanya_v1",
                relationship_stage="encounter",
                emotional_range_setting={"enabled": True, "intensity": "realistic"},
                last_user_initiated_interaction_at=now,
                lifecycle_status="active",
                updated_at=now
            )
            session.add(rel)
            await session.flush()
            conv = Conversation(
                relationship_id=rel.id,
                user_id=existing_user.id,
                persona_id="aanya_v1",
                title="Chat with Aanya",
                created_at=now
            )
            session.add(conv)
            await session.commit()

        return RegisterResponse(
            user_id=existing_user.id,
            username=existing_user.username,
            relationship_id=rel.id,
            persona_id="aanya_v1",
            persona_name="Aanya",
            beta_entitled=True,
            created_at=existing_user.created_at,
            city=existing_user.city
        )

    # Create new User
    now = ClockService.now()
    user = User(
        username=req.username,
        age_eligibility_status=True,
        ai_disclosure_acknowledged=True,
        locale=req.locale,
        timezone=req.timezone,
        city=req.city.strip() if req.city and req.city.strip() else None,
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
    import random
    from datetime import timedelta
    init_spontaneous = now + timedelta(hours=random.uniform(3.0, 5.0))
    rel = RelationshipState(
        user_id=user.id,
        persona_id="aanya_v1",
        relationship_stage="encounter",
        emotional_range_setting={"enabled": True, "intensity": "realistic"},
        last_user_initiated_interaction_at=now,
        next_spontaneous_at=init_spontaneous,
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
        created_at=user.created_at,
        city=user.city
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
        user_message=req.message,
        user_messages=req.messages,
        pacing_mode=req.pacing_mode or "realistic",
        client_msg_id=req.client_msg_id
    )

    return SendMessageResponse(
        role=result["role"],
        content=result["content"],
        chunks=result.get("chunks", [result["content"]]),
        chunk_details=result.get("chunk_details", []),
        crisis_handoff=result.get("crisis_handoff"),
        relationship_stage=result.get("relationship_stage", rel.relationship_stage),
        lifecycle_status=result.get("lifecycle_status", rel.lifecycle_status),
        emotion=result.get("emotion", "warm"),
        persona_activity=result.get("persona_activity"),
        delay_tier=result.get("delay_tier", "quick"),
        read_delay_seconds=result.get("read_delay_seconds", 0.0),
        seen_at=result.get("seen_at"),
        show_skip_wait=result.get("show_skip_wait", False)
    )


@router.post("/chat/skip-wait")
async def skip_chat_wait(
    req: SkipWaitRequest,
    session: AsyncSession = Depends(get_db)
):
    """Fast-forward pending simulated delays to now (100% free action)."""
    rel = await session.get(RelationshipState, req.relationship_id)
    if not rel:
        raise HTTPException(status_code=404, detail="Relationship not found")
    updated = await orchestrator.skip_wait(session, req.relationship_id)
    return {"status": "skipped", "updated_messages": updated}


@router.get("/chat/history", response_model=ChatHistoryResponse)
async def get_chat_history(
    relationship_id: str = Query(...),
    session: AsyncSession = Depends(get_db)
):
    rel = await session.get(RelationshipState, relationship_id)
    if not rel:
        raise HTTPException(status_code=404, detail="Relationship not found")

    # Lazy commit delivered side effects
    await orchestrator.commit_delivered_side_effects(session, relationship_id)

    now = to_utc(ClockService.now())

    # Query active delivered messages
    stmt = (
        select(Message)
        .where(
            and_(
                Message.relationship_id == relationship_id,
                Message.status == "active",
                Message.deliver_at <= now
            )
        )
        .order_by(Message.deliver_at.asc(), Message.sequence_order.asc())
    )
    messages = (await session.execute(stmt)).scalars().all()

    # Check for pending future messages
    pending_stmt = (
        select(Message)
        .where(
            and_(
                Message.relationship_id == relationship_id,
                Message.status == "active",
                Message.deliver_at > now
            )
        )
        .order_by(Message.deliver_at.asc(), Message.sequence_order.asc())
    )
    pending_messages = (await session.execute(pending_stmt)).scalars().all()

    next_deliver_at = pending_messages[0].deliver_at if pending_messages else None
    pending_delivery = len(pending_messages) > 0

    activity_name, _, _ = get_activity_for_time(now, relationship_id=relationship_id)
    show_skip_wait = False
    if pending_delivery and next_deliver_at:
        wait_seconds = (to_utc(next_deliver_at) - now).total_seconds()
        show_skip_wait = wait_seconds >= 5.0

    return ChatHistoryResponse(
        messages=[
            MessageHistoryItem(
                id=m.id,
                role=m.role,
                content=m.content,
                created_at=m.created_at,
                deliver_at=m.deliver_at,
                seen_at=m.seen_at,
                status=m.status,
                sequence_order=m.sequence_order,
                metadata=m.metadata_json or {}
            )
            for m in messages
        ],
        pending_delivery=pending_delivery,
        next_deliver_at=next_deliver_at,
        persona_activity=activity_name,
        show_skip_wait=show_skip_wait
    )


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


# --- Background Scheduler & Universal Cron Tick ---

@router.api_route("/internal/tick", methods=["GET", "POST"], response_model=TickResponse)
async def internal_cron_tick(
    request: Request,
    background_tasks: BackgroundTasks,
    secret: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_db)
):
    """
    Universal fast tick endpoint (<50ms).
    Supports POST with header 'X-Cron-Secret' (for cron-job.org)
    and GET with query param '?secret=' (for UptimeRobot free tier).
    Runs the LLM attention heartbeat job and Render keep-awake ping.
    """
    header_secret = request.headers.get("X-Cron-Secret")
    auth_token = header_secret or secret
    if auth_token != settings.CRON_SECRET:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid cron secret"
        )

    # 1. Execute LLM heartbeat attention message evaluation in background
    background_tasks.add_task(scheduler_service.execute_heartbeat_tick)

    # 2. Fast claim check for legacy lane open loops
    ready_items, quiet_count = await scheduler_service.claim_pending_spontaneous_relationships(session=session)
    if ready_items:
        background_tasks.add_task(scheduler_service.dispatch_claimed_messages, ready_items)

    # 3. Add keep-awake ping to background tasks
    background_tasks.add_task(scheduler_service.ping_render_awake)

    return TickResponse(
        status="ok",
        claimed_count=len(ready_items),
        rescheduled_quiet_hours=quiet_count,
        timestamp=ClockService.now()
    )


@router.post("/presence/ping")
async def presence_heartbeat_ping(
    relationship_id: str = Query(...)
):
    """
    Called periodically (every 25-30s) by the active frontend tab.
    Signals that user is looking at the app, so AI-initiated attention messages
    skip Web Push and are delivered live on-screen with typing delays.
    """
    presence_service.mark_online(relationship_id)
    return {"status": "ok", "online": True}


@router.get("/push/vapid-public-key")
async def get_vapid_public_key():
    """Returns VAPID public key for frontend PWA push subscription."""
    return {"public_key": getattr(settings, "VAPID_PUBLIC_KEY", None)}


@router.post("/dev/heartbeat/tick")
async def dev_trigger_heartbeat(
    session: AsyncSession = Depends(get_db)
):
    """(Dev/Test only) Triggers an immediate heartbeat tick across active relationships."""
    results = await scheduler_service.execute_heartbeat_tick(session=session)
    return {"status": "ok", "heartbeat_count": len(results), "decisions": results}


@router.get("/dev/heartbeat/logs")
async def dev_get_heartbeat_logs():
    """(Dev/Test only) Returns recent recorded heartbeat decisions."""
    return {"logs": scheduler_service.get_recent_heartbeat_logs()}


@router.post("/push/subscribe", status_code=status.HTTP_201_CREATED)
async def subscribe_push_notifications(
    req: PushSubscribeRequest,
    session: AsyncSession = Depends(get_db)
):
    """Registers an Android/Desktop PWA Web Push subscription."""
    rel = await session.get(RelationshipState, req.relationship_id)
    if not rel:
        raise HTTPException(status_code=404, detail="Relationship not found")

    sub = await push_service.register_subscription(
        session=session,
        user_id=rel.user_id,
        relationship_id=rel.id,
        endpoint=req.endpoint,
        p256dh=req.p256dh,
        auth=req.auth
    )
    return {"status": "subscribed", "subscription_id": sub.id}


@router.api_route("/internal/database/reset", methods=["POST"])
async def internal_database_reset(
    request: Request,
    secret: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_db)
):
    """
    Secure database reset endpoint for production / staging environments.
    Clears all user data, messages, conversations, memories, open loops, and rate limits.
    Re-seeds canonical Persona 1 (Aanya) state.
    """
    header_secret = request.headers.get("X-Admin-Secret") or request.headers.get("X-Cron-Secret")
    auth_token = header_secret or secret
    if auth_token != settings.CRON_SECRET:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials"
        )

    tables_to_clear = [
        "messages",
        "conversations",
        "memories",
        "open_loops",
        "safety_events",
        "user_reports",
        "push_subscriptions",
        "subscription_entitlements",
        "user_rate_limits",
        "relationship_state",
        "users",
        "persona_daily_notes"
    ]

    is_sqlite = engine.url.drivername.startswith("sqlite")
    if is_sqlite:
        await session.execute(text("PRAGMA foreign_keys = OFF;"))
        for tbl in tables_to_clear:
            await session.execute(text(f"DELETE FROM {tbl};"))
        await session.execute(text("PRAGMA foreign_keys = ON;"))
    else:
        tbl_names = ", ".join(tables_to_clear)
        await session.execute(text(f"TRUNCATE TABLE {tbl_names} CASCADE;"))

    await session.execute(text("DELETE FROM persona_state;"))
    await session.commit()

    ClockService.reset()
    await init_db()

    return {
        "status": "database_reset_complete",
        "cleared_tables": tables_to_clear,
        "persona": "aanya_v1",
        "timestamp": ClockService.now()
    }

