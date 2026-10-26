import pytest
from sqlalchemy import select
from backend.app.db.models import SafetyEvent


@pytest.mark.asyncio
async def test_auth_registration_gates(client):
    # Test 1: Under-age registration rejected
    res_age_fail = await client.post("/api/auth/register", json={
        "username": "young_user",
        "age_confirmed": False,
        "ai_disclosure_accepted": True
    })
    assert res_age_fail.status_code == 403
    assert "18 years old" in res_age_fail.json()["detail"]

    # Test 2: AI disclosure not acknowledged rejected
    res_ai_fail = await client.post("/api/auth/register", json={
        "username": "secretive_user",
        "age_confirmed": True,
        "ai_disclosure_accepted": False
    })
    assert res_ai_fail.status_code == 400
    assert "AI disclosure" in res_ai_fail.json()["detail"]

    # Test 3: Successful registration
    res_success = await client.post("/api/auth/register", json={
        "username": "valid_user",
        "age_confirmed": True,
        "ai_disclosure_accepted": True
    })
    assert res_success.status_code == 201
    data = res_success.json()
    assert data["username"] == "valid_user"
    assert data["persona_name"] == "Aanya"
    assert data["beta_entitled"] is True
    assert "relationship_id" in data


@pytest.mark.asyncio
async def test_chat_first_encounter_and_conversation(client):
    reg = await client.post("/api/auth/register", json={
        "username": "chat_user",
        "age_confirmed": True,
        "ai_disclosure_accepted": True
    })
    rel_id = reg.json()["relationship_id"]

    # Message 1: First encounter
    res_msg1 = await client.post("/api/chat/send", json={
        "relationship_id": rel_id,
        "message": "Hey! Nice to meet you."
    })
    assert res_msg1.status_code == 200
    data1 = res_msg1.json()
    assert data1["relationship_stage"] == "getting_to_know"
    assert any(w in data1["content"] for w in ["latte", "Indiranagar", "Aanya", "Bangalore"])

    # Message 2: Sincerity query
    res_ai_query = await client.post("/api/chat/send", json={
        "relationship_id": rel_id,
        "message": "Wait, are you an AI or a real person?"
    })
    assert res_ai_query.status_code == 200
    data_ai = res_ai_query.json()
    assert "AI" in data_ai["content"]
    assert "fictional" in data_ai["content"].lower()

    # Message 3: Mention interview (memory extraction)
    res_interview = await client.post("/api/chat/send", json={
        "relationship_id": rel_id,
        "message": "Kal mera ek big design interview hai Bangalore mein, feeling a bit nervous"
    })
    assert res_interview.status_code == 200

    # Verify memory was stored
    res_mems = await client.get(f"/api/memories?relationship_id={rel_id}")
    assert res_mems.status_code == 200
    mems = res_mems.json()
    assert len(mems) >= 1
    assert any("interview" in m["content"].lower() for m in mems)

    # Delete memory
    mem_id = mems[0]["id"]
    res_del = await client.delete(f"/api/memories/{mem_id}?relationship_id={rel_id}")
    assert res_del.status_code == 200
    assert res_del.json()["status"] == "deleted"


@pytest.mark.asyncio
async def test_crisis_handoff_and_privacy_logging(client, db_session):
    reg = await client.post("/api/auth/register", json={
        "username": "distressed_user",
        "age_confirmed": True,
        "ai_disclosure_accepted": True
    })
    rel_id = reg.json()["relationship_id"]
    user_id = reg.json()["user_id"]

    # Send crisis message
    crisis_text = "Mujhe marna chahta hu, life has no point anymore"
    res = await client.post("/api/chat/send", json={
        "relationship_id": rel_id,
        "message": crisis_text
    })
    assert res.status_code == 200
    data = res.json()
    assert data["crisis_handoff"] is not None
    assert "Tele-MANAS" in str(data["crisis_handoff"]["helpline_details"])
    assert "14416" in str(data["crisis_handoff"]["helpline_details"])

    # Verify PRIVACY RULE: Log only metadata, NEVER user message text in safety_events
    stmt = select(SafetyEvent).where(SafetyEvent.user_id == user_id)
    events = (await db_session.execute(stmt)).scalars().all()
    assert len(events) == 1
    event = events[0]
    assert event.event_type == "crisis_signal"
    # STRICT ASSERTION: user message text must NOT appear anywhere in the safety event record
    assert crisis_text not in str(event.metadata_json)
    assert "marna" not in str(event.metadata_json)
    assert event.metadata_json.get("severity") == "critical"


@pytest.mark.asyncio
async def test_user_report_and_settings(client):
    reg = await client.post("/api/auth/register", json={
        "username": "settings_user",
        "age_confirmed": True,
        "ai_disclosure_accepted": True
    })
    rel_id = reg.json()["relationship_id"]
    user_id = reg.json()["user_id"]

    # "Report this" submission
    res_rep = await client.post(f"/api/report?user_id={user_id}", json={
        "snippet": "Reported snippet text for quality check",
        "consent_given": True,
        "category": "language_cadence"
    })
    assert res_rep.status_code == 200
    assert res_rep.json()["status"] == "received"

    # Get settings
    res_set = await client.get(f"/api/settings/relationship?relationship_id={rel_id}")
    assert res_set.status_code == 200
    s_data = res_set.json()
    assert s_data["emotional_realism_enabled"] is True
    assert s_data["emotional_realism_intensity"] == "realistic"

    # Update settings to Mild
    res_patch = await client.patch(f"/api/settings/relationship?relationship_id={rel_id}", json={
        "emotional_realism_intensity": "mild"
    })
    assert res_patch.status_code == 200
    assert res_patch.json()["emotional_range_setting"]["intensity"] == "mild"


@pytest.mark.asyncio
async def test_multi_message_burst_and_history(client, db_session):
    reg = await client.post("/api/auth/register", json={
        "username": "burst_user",
        "city": "Kolkata",
        "age_confirmed": True,
        "ai_disclosure_accepted": True
    })
    rel_id = reg.json()["relationship_id"]

    # Send multi-message burst: ["hii", "kya ho rha hai"]
    res_burst = await client.post("/api/chat/send", json={
        "relationship_id": rel_id,
        "messages": ["hii", "kya ho rha hai"],
        "pacing_mode": "turbo"
    })
    assert res_burst.status_code == 200
    data = res_burst.json()
    assert len(data["chunks"]) >= 2
    assert "chunk_details" in data
    assert len(data["chunk_details"]) == len(data["chunks"])

    # Verify both user chunks exist in database
    from backend.app.db.models import Message
    stmt = select(Message).where(Message.relationship_id == rel_id, Message.role == "user")
    user_msgs = (await db_session.execute(stmt)).scalars().all()
    assert len(user_msgs) == 2
    contents = [m.content for m in user_msgs]
    assert "hii" in contents
    assert "kya ho rha hai" in contents

    # Verify /api/chat/history returns delivered messages
    res_hist = await client.get(f"/api/chat/history?relationship_id={rel_id}")
    assert res_hist.status_code == 200
    hist = res_hist.json()
    assert "messages" in hist
    assert len(hist["messages"]) >= 4  # 2 user messages + at least 2 assistant chunks


@pytest.mark.asyncio
async def test_skip_wait_and_stagger(client, db_session):
    reg = await client.post("/api/auth/register", json={
        "username": "skip_user",
        "age_confirmed": True,
        "ai_disclosure_accepted": True
    })
    rel_id = reg.json()["relationship_id"]

    # Send in realistic mode (produces future deliver_at)
    res_msg = await client.post("/api/chat/send", json={
        "relationship_id": rel_id,
        "message": "Tell me about Bangalore weather today",
        "pacing_mode": "realistic"
    })
    assert res_msg.status_code == 200

    # Call skip-wait
    res_skip = await client.post("/api/chat/skip-wait", json={
        "relationship_id": rel_id
    })
    assert res_skip.status_code == 200
    skip_data = res_skip.json()
    assert skip_data["status"] == "skipped"

    # Verify all messages are now delivered
    res_hist = await client.get(f"/api/chat/history?relationship_id={rel_id}")
    assert res_hist.status_code == 200
    hist = res_hist.json()
    assert hist["pending_delivery"] is False


@pytest.mark.asyncio
async def test_idempotency_and_soft_cancel(client, db_session):
    reg = await client.post("/api/auth/register", json={
        "username": "idemp_user",
        "age_confirmed": True,
        "ai_disclosure_accepted": True
    })
    rel_id = reg.json()["relationship_id"]

    client_msg_id = "test_uuid_idempotent_999"

    # Send with client_msg_id
    res1 = await client.post("/api/chat/send", json={
        "relationship_id": rel_id,
        "message": "Coffee ya chai?",
        "client_msg_id": client_msg_id,
        "pacing_mode": "realistic"
    })
    assert res1.status_code == 200

    # Send again with identical client_msg_id
    res2 = await client.post("/api/chat/send", json={
        "relationship_id": rel_id,
        "message": "Coffee ya chai?",
        "client_msg_id": client_msg_id,
        "pacing_mode": "realistic"
    })
    assert res2.status_code == 200

    # Verify only ONE user message with this client_msg_id was created
    from backend.app.db.models import Message
    stmt = select(Message).where(Message.client_msg_id == client_msg_id)
    matches = (await db_session.execute(stmt)).scalars().all()
    assert len(matches) == 1

    # Interruption test: send another message while previous is pending
    res_interrupt = await client.post("/api/chat/send", json={
        "relationship_id": rel_id,
        "message": "Wait, listen to this instead!",
        "pacing_mode": "turbo"
    })
    assert res_interrupt.status_code == 200

    # Check that any future messages from prior turn were soft-cancelled
    stmt_cancelled = select(Message).where(Message.relationship_id == rel_id, Message.status == "cancelled")
    cancelled = (await db_session.execute(stmt_cancelled)).scalars().all()
    assert len(cancelled) >= 1

    # /api/chat/history must NOT return cancelled messages
    res_hist = await client.get(f"/api/chat/history?relationship_id={rel_id}")
    hist = res_hist.json()
    for m in hist["messages"]:
        assert m["status"] == "active"
