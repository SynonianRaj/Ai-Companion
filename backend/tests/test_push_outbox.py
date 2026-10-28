import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import settings
from backend.app.db.models import User, RelationshipState, Conversation, Message, PushSubscription, NotificationOutbox
from backend.app.services.push_service import push_service
from backend.app.services.presence_service import presence_service
from backend.app.services.clock_service import ClockService


@pytest.mark.asyncio
async def test_vapid_public_key_endpoint(client: AsyncClient):
    """Verify that VAPID public key is returned for frontend subscription."""
    res = await client.get("/api/push/vapid-public-key")
    assert res.status_code == 200
    data = res.json()
    assert "public_key" in data
    assert data["public_key"] == settings.VAPID_PUBLIC_KEY
    assert data["public_key"] is not None


@pytest.mark.asyncio
async def test_push_subscription_registration(client: AsyncClient, db_session: AsyncSession):
    """Test registering and updating a push subscription."""
    # 1. Setup user & relationship
    user = User(username="test_push_user", age_eligibility_status=True, ai_disclosure_acknowledged=True)
    db_session.add(user)
    await db_session.flush()

    rel = RelationshipState(user_id=user.id, persona_id="aanya_v1")
    db_session.add(rel)
    await db_session.commit()

    # 2. Register push subscription
    endpoint = "https://fcm.googleapis.com/fcm/send/sample_push_endpoint_123"
    payload = {
        "relationship_id": rel.id,
        "endpoint": endpoint,
        "p256dh": "sample_p256dh_key",
        "auth": "sample_auth_secret"
    }
    res = await client.post("/api/push/subscribe", json=payload)
    assert res.status_code == 201
    assert res.json()["status"] == "subscribed"

    # Verify stored in DB
    sub = (await db_session.execute(select(PushSubscription).where(PushSubscription.endpoint == endpoint))).scalar_one()
    assert sub.user_id == user.id
    assert sub.relationship_id == rel.id

    # 3. Re-registering with updated keys should update, not duplicate
    payload["p256dh"] = "updated_p256dh_key"
    res2 = await client.post("/api/push/subscribe", json=payload)
    assert res2.status_code == 201

    db_session.expire_all()
    all_subs = (await db_session.execute(select(PushSubscription).where(PushSubscription.endpoint == endpoint))).scalars().all()
    assert len(all_subs) == 1
    assert all_subs[0].p256dh == "updated_p256dh_key"


@pytest.mark.asyncio
async def test_notification_outbox_uniqueness_and_processing(db_session: AsyncSession):
    """Test outbox uniqueness guarantee and presence-aware processing."""
    now = datetime.now(timezone.utc)
    user = User(username="outbox_user", age_eligibility_status=True, ai_disclosure_acknowledged=True)
    db_session.add(user)
    await db_session.flush()

    rel = RelationshipState(user_id=user.id, persona_id="aanya_v1")
    db_session.add(rel)
    await db_session.flush()

    conv = Conversation(relationship_id=rel.id, user_id=user.id, persona_id="aanya_v1")
    db_session.add(conv)
    await db_session.flush()

    msg = Message(
        conversation_id=conv.id,
        relationship_id=rel.id,
        user_id=user.id,
        persona_id="aanya_v1",
        role="assistant",
        content="Hey! Sometime today let's catch up.",
        deliver_at=now - timedelta(seconds=5),
        status="active"
    )
    db_session.add(msg)
    await db_session.commit()

    # 1. Enqueue outbox notification
    entry1 = await push_service.enqueue_outbox_notification(
        session=db_session,
        user_id=user.id,
        relationship_id=rel.id,
        conversation_id=conv.id,
        message_id=msg.id,
        scheduled_at=msg.deliver_at,
        title="Aanya",
        body=msg.content
    )
    assert entry1 is not None
    await db_session.commit()

    # 2. Duplicate enqueue for same message_id should return existing record (exactly-once)
    entry2 = await push_service.enqueue_outbox_notification(
        session=db_session,
        user_id=user.id,
        relationship_id=rel.id,
        conversation_id=conv.id,
        message_id=msg.id,
        scheduled_at=msg.deliver_at,
        title="Aanya",
        body=msg.content
    )
    assert entry2.id == entry1.id

    # 3. Test outbox processing when user is ONLINE in the app
    presence_service.mark_online(rel.id)
    assert presence_service.is_online(rel.id) is True

    processed_count = await push_service.process_outbox(db_session)
    assert processed_count == 1

    await db_session.refresh(entry1)
    assert entry1.status == "skipped"
    assert entry1.metadata_json.get("skip_reason") == "user_online"


@pytest.mark.asyncio
async def test_outbox_processing_when_user_offline(db_session: AsyncSession):
    """When user is offline, outbox processes and marks sent."""
    now = datetime.now(timezone.utc)
    user = User(username="offline_user", age_eligibility_status=True, ai_disclosure_acknowledged=True)
    db_session.add(user)
    await db_session.flush()

    rel = RelationshipState(user_id=user.id, persona_id="aanya_v1")
    db_session.add(rel)
    await db_session.flush()

    conv = Conversation(relationship_id=rel.id, user_id=user.id, persona_id="aanya_v1")
    db_session.add(conv)
    await db_session.flush()

    msg = Message(
        conversation_id=conv.id,
        relationship_id=rel.id,
        user_id=user.id,
        persona_id="aanya_v1",
        role="assistant",
        content="Free right now?",
        deliver_at=now - timedelta(seconds=10),
        status="active"
    )
    db_session.add(msg)
    await db_session.commit()

    # Register subscription
    sub = PushSubscription(
        user_id=user.id,
        relationship_id=rel.id,
        endpoint="https://push.example.com/sub_offline",
        p256dh="key",
        auth="auth"
    )
    db_session.add(sub)
    await db_session.commit()

    # Enqueue
    entry = await push_service.enqueue_outbox_notification(
        session=db_session,
        user_id=user.id,
        relationship_id=rel.id,
        conversation_id=conv.id,
        message_id=msg.id,
        scheduled_at=msg.deliver_at,
        title="Aanya",
        body=msg.content
    )
    await db_session.commit()

    # User is NOT online
    presence_service._last_seen.pop(rel.id, None)
    assert presence_service.is_online(rel.id) is False

    with patch("pywebpush.webpush", return_value=None):
        processed = await push_service.process_outbox(db_session)
    assert processed == 1

    await db_session.refresh(entry)
    assert entry.status == "sent"
    assert entry.sent_at is not None


@pytest.mark.asyncio
async def test_authenticated_test_push_endpoint(client: AsyncClient, db_session: AsyncSession):
    """Test POST /api/push/test endpoint."""
    user = User(username="test_push_api_user", age_eligibility_status=True, ai_disclosure_acknowledged=True)
    db_session.add(user)
    await db_session.flush()

    rel = RelationshipState(user_id=user.id, persona_id="aanya_v1")
    db_session.add(rel)
    await db_session.commit()

    # 1. Invalid relationship
    res_bad = await client.post("/api/push/test", json={"relationship_id": "non_existent_id"})
    assert res_bad.status_code == 404

    # 2. Valid relationship with no active subscription
    res_ok_no_sub = await client.post("/api/push/test", json={"relationship_id": rel.id})
    assert res_ok_no_sub.status_code == 200
    assert res_ok_no_sub.json()["delivered_count"] == 0

    # 3. Valid relationship with active subscription
    sub = PushSubscription(
        user_id=user.id,
        relationship_id=rel.id,
        endpoint="https://push.example.com/test_endpoint_abc",
        p256dh="key",
        auth="auth"
    )
    db_session.add(sub)
    await db_session.commit()

    with patch("pywebpush.webpush", return_value=None):
        res_ok = await client.post("/api/push/test", json={"relationship_id": rel.id})
    assert res_ok.status_code == 200
    assert res_ok.json()["status"] == "ok"
    assert res_ok.json()["delivered_count"] == 1


@pytest.mark.asyncio
async def test_chat_history_canonical_ordering(client: AsyncClient, db_session: AsyncSession):
    """Test that /chat/history strictly orders by deliver_at, then sequence_order, then id."""
    now = datetime.now(timezone.utc)
    user = User(username="ordering_user", age_eligibility_status=True, ai_disclosure_acknowledged=True)
    db_session.add(user)
    await db_session.flush()

    rel = RelationshipState(user_id=user.id, persona_id="aanya_v1")
    db_session.add(rel)
    await db_session.flush()

    conv = Conversation(relationship_id=rel.id, user_id=user.id, persona_id="aanya_v1")
    db_session.add(conv)
    await db_session.flush()

    # Insert messages in reverse order of delivery
    msg2 = Message(
        id="msg_second",
        conversation_id=conv.id,
        relationship_id=rel.id,
        user_id=user.id,
        persona_id="aanya_v1",
        role="assistant",
        content="Second message",
        created_at=now - timedelta(minutes=5),
        deliver_at=now - timedelta(minutes=2),
        sequence_order=1,
        status="active"
    )
    msg1 = Message(
        id="msg_first",
        conversation_id=conv.id,
        relationship_id=rel.id,
        user_id=user.id,
        persona_id="aanya_v1",
        role="assistant",
        content="First message",
        created_at=now - timedelta(minutes=5),
        deliver_at=now - timedelta(minutes=4),
        sequence_order=0,
        status="active"
    )
    db_session.add_all([msg2, msg1])
    await db_session.commit()

    res = await client.get(f"/api/chat/history?relationship_id={rel.id}")
    assert res.status_code == 200
    msgs = res.json()["messages"]
    assert len(msgs) == 2
    assert msgs[0]["id"] == "msg_first"
    assert msgs[1]["id"] == "msg_second"
