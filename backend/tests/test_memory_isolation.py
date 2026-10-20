import pytest
from backend.app.services.memory_service import memory_service
from backend.app.db.models import User, RelationshipState


@pytest.mark.asyncio
async def test_relationship_memory_isolation(db_session):
    # User 1
    u1 = User(username="user_one", age_eligibility_status=True, ai_disclosure_acknowledged=True)
    db_session.add(u1)
    await db_session.flush()
    r1 = RelationshipState(user_id=u1.id, persona_id="aanya_v1")
    db_session.add(r1)

    # User 2
    u2 = User(username="user_two", age_eligibility_status=True, ai_disclosure_acknowledged=True)
    db_session.add(u2)
    await db_session.flush()
    r2 = RelationshipState(user_id=u2.id, persona_id="aanya_v1")
    db_session.add(r2)
    await db_session.commit()

    # Store memory for Relationship 1
    mem1 = await memory_service.store_memory(
        session=db_session,
        relationship_id=r1.id,
        user_id=u1.id,
        persona_id="aanya_v1",
        memory_type="profile",
        content="Secret: User One works as an architect in Whitefield"
    )

    # Store memory for Relationship 2
    mem2 = await memory_service.store_memory(
        session=db_session,
        relationship_id=r2.id,
        user_id=u2.id,
        persona_id="aanya_v1",
        memory_type="profile",
        content="Secret: User Two is preparing for UPSC in Koramangala"
    )
    await db_session.commit()

    # Verify Relationship 1 can only see its own memories
    r1_mems = await memory_service.get_all_memories(db_session, r1.id)
    assert len(r1_mems) == 1
    assert "architect" in r1_mems[0].content
    assert "UPSC" not in r1_mems[0].content

    # Verify Relationship 2 can only see its own memories
    r2_mems = await memory_service.get_all_memories(db_session, r2.id)
    assert len(r2_mems) == 1
    assert "UPSC" in r2_mems[0].content
    assert "architect" not in r2_mems[0].content

    # User 1 deletes their memory
    deleted = await memory_service.delete_memory(db_session, r1.id, mem1.id)
    assert deleted is True

    # Check R1 memories empty, R2 untouched
    assert len(await memory_service.get_all_memories(db_session, r1.id)) == 0
    assert len(await memory_service.get_all_memories(db_session, r2.id)) == 1
