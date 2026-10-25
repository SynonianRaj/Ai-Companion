import re
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
    def extract_user_facts(text: str) -> List[Dict[str, Any]]:
        """
        Extracts structured facts about the user (name, city, job, preferences).
        """
        facts = []
        t = text.strip()
        t_lower = t.lower()

        # Name extraction (only if user is actually stating their name, not asking a question)
        is_name_query = bool(re.search(r"\b(yaad|pata|kya|batao|kyun|kaun|who)\b", t_lower) or "?" in t)
        if not is_name_query:
            name_patterns = [
                r"(?:mera\s+naam|naam\s+hai|my\s+name\s+is|i(?:'m|\s+am))\s+([A-Za-z]+)",
                r"(?:call\s+me|this\s+is)\s+([A-Za-z]+)"
            ]
            for p in name_patterns:
                m = re.search(p, t, re.IGNORECASE)
                if m:
                    val = m.group(1).strip()
                    blacklist = {
                        "aanya", "nahi", "ek", "batao", "theek", "free", "working", "chilling",
                        "delhi", "bangalore", "yaad", "pata", "kya", "kyun", "hoga", "bhi",
                        "software", "engineer", "designer", "doctor", "student"
                    }
                    if val.lower() not in blacklist and len(val) >= 2:
                        facts.append({
                            "type": "user_name",
                            "content": f"User's name is {val.capitalize()}",
                            "importance": 0.95
                        })
                    break

        # City extraction
        is_city_query = "?" in t or any(q in t_lower for q in ["kaisa", "kya", "kab", "kaun", "kahan", "batao", "bata", "pata", "yaad", "mausam", "weather"])
        if not is_city_query:
            city_aliases = {
                "delhi": "Delhi",
                "mumbai": "Mumbai",
                "bengaluru": "Bengaluru",
                "bangalore": "Bengaluru",
                "kolkata": "Kolkata",
                "pune": "Pune",
                "hyderabad": "Hyderabad",
                "jaipur": "Jaipur",
                "chennai": "Chennai",
                "gurgaon": "Gurgaon",
                "noida": "Noida",
                "lucknow": "Lucknow"
            }
            for alias, canon in city_aliases.items():
                if re.search(rf"\b(?:main|me|i)\s+.*?\b{alias}\b", t_lower) or \
                   re.search(rf"\b(?:{alias}\s+(?:se\s+hoon|mein\s+rehta|me\s+rehta|se\s+belong)|live\s+in\s+{alias}|from\s+{alias})\b", t_lower):
                    facts.append({
                        "type": "user_city",
                        "content": f"User lives in {canon}",
                        "importance": 0.9
                    })
                    break

        # Job / Profession extraction
        job_matches = [
            (r"\b(software\s+engineer|sde|developer|coder|programmer)\b", "Software Engineer"),
            (r"\b(ui/ux\s+designer|product\s+designer|designer)\b", "Designer"),
            (r"\b(doctor|physician|surgeon)\b", "Doctor"),
            (r"\b(chartered\s+accountant|ca)\b", "Chartered Accountant"),
            (r"\b(lawyer|advocate)\b", "Lawyer"),
            (r"\b(teacher|professor)\b", "Teacher"),
            (r"\b(student|college)\b", "Student"),
            (r"\b(banker|banking)\b", "Banker"),
            (r"\b(product\s+manager|pm)\b", "Product Manager"),
        ]
        for pattern, role_title in job_matches:
            if re.search(pattern, t_lower):
                facts.append({
                    "type": "user_job",
                    "content": f"User works as a {role_title}",
                    "importance": 0.85
                })
                break

        # Preferences extraction
        pref_m = re.search(r"(?:mujhe|i\s+like|i\s+love)\s+([a-zA-Z\s]{3,30}?)\s+(?:bahut\s+pasand|pasand\s+hai|accha\s+lagta)", t_lower)
        if pref_m:
            item = pref_m.group(1).strip()
            if item:
                facts.append({
                    "type": "user_preference",
                    "content": f"User likes {item}",
                    "importance": 0.75
                })

        return facts

    @staticmethod
    def extract_persona_facts(text: str) -> List[Dict[str, Any]]:
        """
        Extracts facts Aanya has shared about herself during the chat.
        """
        facts = []
        t = text.strip()
        t_lower = t.lower()

        # If Aanya shared a specific activity or detail
        if "cold brew" in t_lower or "filter coffee" in t_lower:
            facts.append({
                "type": "persona_fact",
                "content": "Aanya mentioned drinking coffee/cold brew",
                "importance": 0.6
            })
        if "figma" in t_lower or "design" in t_lower:
            facts.append({
                "type": "persona_fact",
                "content": "Aanya mentioned working on UI/UX designs",
                "importance": 0.6
            })
        if "indie" in t_lower or "prateek kuhad" in t_lower:
            facts.append({
                "type": "persona_fact",
                "content": "Aanya mentioned listening to indie music",
                "importance": 0.6
            })
        return facts

    @staticmethod
    async def get_structured_facts(
        session: AsyncSession,
        relationship_id: str
    ) -> Dict[str, List[str]]:
        """
        Retrieves active facts about the user and Aanya for prompt injection.
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
        res = await session.execute(stmt)
        memories = res.scalars().all()

        user_facts = []
        persona_facts = []
        seen = set()

        for m in memories:
            clean = m.content.strip()
            if clean in seen:
                continue
            seen.add(clean)

            if m.memory_type in ("user_fact", "profile", "user_name", "user_city", "user_job", "user_preference"):
                user_facts.append(clean)
            elif m.memory_type in ("persona_fact", "shared_history"):
                persona_facts.append(clean)
            else:
                user_facts.append(clean)

        return {
            "user_facts": user_facts[:6],
            "persona_facts": persona_facts[:4]
        }

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
