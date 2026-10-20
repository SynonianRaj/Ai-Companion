from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from sqlalchemy import select, and_, delete
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.db.models import Memory, OpenLoop
from backend.app.services.clock_service import ClockService


class MemoryService:
    """
    Manages relationship-scoped user memories and open loops.
    Strict isolation by relationship_id.
    """

    @staticmethod
    async def store_memory(
        session: AsyncSession,
        relationship_id: str,
        user_id: str,
        persona_id: str,
        memory_type: str,
        content: str,
        source_message_ids: Optional[List[str]] = None,
        importance: float = 0.7,
        confidence: float = 1.0
    ) -> Memory:
        mem = Memory(
            relationship_id=relationship_id,
            user_id=user_id,
            persona_id=persona_id,
            memory_type=memory_type,
            content=content,
            source_message_ids=source_message_ids or [],
            occurred_at=ClockService.now(),
            importance=importance,
            confidence=confidence,
            status="active"
        )
        session.add(mem)
        await session.flush()
        return mem

    @staticmethod
    async def retrieve_relevant_memories(
        session: AsyncSession,
        relationship_id: str,
        query: str,
        limit: int = 5
    ) -> List[Memory]:
        """
        Retrieves relevant active memories strictly scoped by relationship_id.
        In Phase 1, uses keyword matching and importance ranking.
        """
        stmt = (
            select(Memory)
            .where(
                and_(
                    Memory.relationship_id == relationship_id,
                    Memory.status == "active"
                )
            )
            .order_by(Memory.importance.desc(), Memory.occurred_at.desc())
        )
        result = await session.execute(stmt)
        all_memories = result.scalars().all()

        if not query:
            return list(all_memories[:limit])

        # Simple keyword ranking
        query_words = set(query.lower().split())
        scored = []
        for mem in all_memories:
            mem_words = set(mem.content.lower().split())
            overlap = len(query_words.intersection(mem_words))
            scored.append((overlap, mem.importance, mem))

        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
        return [item[2] for item in scored[:limit]]

    @staticmethod
    async def get_all_memories(
        session: AsyncSession,
        relationship_id: str
    ) -> List[Memory]:
        """Allows user to inspect all memories stored for their relationship."""
        stmt = (
            select(Memory)
            .where(
                and_(
                    Memory.relationship_id == relationship_id,
                    Memory.status == "active"
                )
            )
            .order_by(Memory.occurred_at.desc())
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def delete_memory(
        session: AsyncSession,
        relationship_id: str,
        memory_id: str
    ) -> bool:
        """User memory erasure: permanently deletes a memory from the database."""
        stmt = (
            delete(Memory)
            .where(
                and_(
                    Memory.id == memory_id,
                    Memory.relationship_id == relationship_id
                )
            )
        )
        result = await session.execute(stmt)
        await session.commit()
        return result.rowcount > 0

    @staticmethod
    async def track_open_loop(
        session: AsyncSession,
        relationship_id: str,
        user_id: str,
        persona_id: str,
        topic: str,
        origin_memory_id: Optional[str] = None
    ) -> OpenLoop:
        loop = OpenLoop(
            relationship_id=relationship_id,
            user_id=user_id,
            persona_id=persona_id,
            topic=topic,
            origin_memory_id=origin_memory_id,
            status="open",
            last_relevant_at=ClockService.now()
        )
        session.add(loop)
        await session.flush()
        return loop

    @staticmethod
    async def get_open_loops(
        session: AsyncSession,
        relationship_id: str
    ) -> List[OpenLoop]:
        stmt = (
            select(OpenLoop)
            .where(
                and_(
                    OpenLoop.relationship_id == relationship_id,
                    OpenLoop.status == "open"
                )
            )
            .order_by(OpenLoop.last_relevant_at.desc())
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())


memory_service = MemoryService()
