"""
Question Tracker Service:
Tracks user questions that Aanya skipped, deflected, or missed (e.g. while asleep,
busy, or shifting conversational focus), detected via the LLM's `skipped_question` output.

Enforces:
- 36-hour expiry window
- Strict honesty grounding: when answering "how do you know X", Aanya can ONLY
  use facts the user actually stated. If the user never stated it, she honestly
  admits she doesn't know or mixed it up.
- AI sincerity: truthful, concise disclosure when asked about being an AI or data privacy.
- Automatic resolution when answered.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional
from sqlalchemy import select, and_, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import PendingQuestion
from backend.app.db.session import to_utc
from backend.app.services.clock_service import ClockService

logger = logging.getLogger(__name__)


class QuestionTrackerService:
    @classmethod
    async def track_skipped_question(
        cls,
        session: AsyncSession,
        relationship_id: str,
        user_id: str,
        persona_id: str,
        question_text: str,
        current_time: Optional[datetime] = None
    ) -> Optional[PendingQuestion]:
        """
        Records a skipped/unanswered question detected by the LLM with a 36-hour expiry.
        Deduplicates against open pending questions for the same relationship.
        """
        if not question_text or not question_text.strip():
            return None

        clean_q = question_text.strip()
        now = to_utc(current_time or ClockService.now())
        expires = now + timedelta(hours=36)

        # Categorize question
        q_lower = clean_q.lower()
        if any(w in q_lower for w in ["how do you know", "kahan se pata", "kaise pata", "how you know", "kisne bataya"]):
            q_type = "user_fact_query"
        elif any(w in q_lower for w in ["ai", "bot", "real", "human", "data", "privacy", "delete", "store"]):
            q_type = "ai_sincerity"
        else:
            q_type = "general"

        # Check existing open pending question with similar text
        stmt = (
            select(PendingQuestion)
            .where(
                and_(
                    PendingQuestion.relationship_id == relationship_id,
                    PendingQuestion.status == "pending",
                    PendingQuestion.expires_at > now
                )
            )
            .order_by(PendingQuestion.asked_at.desc())
        )
        existing_list = (await session.execute(stmt)).scalars().all()
        for ex in existing_list:
            if clean_q.lower() in ex.question_text.lower() or ex.question_text.lower() in clean_q.lower():
                # Refresh expiry
                ex.expires_at = expires
                return ex

        new_pq = PendingQuestion(
            relationship_id=relationship_id,
            user_id=user_id,
            persona_id=persona_id,
            question_text=clean_q,
            question_type=q_type,
            status="pending",
            asked_at=now,
            expires_at=expires
        )
        session.add(new_pq)
        await session.flush()
        logger.info(
            "[QuestionTracker] Tracked pending question: id=%s type=%s text=%r expires=%s",
            new_pq.id, q_type, clean_q, expires.isoformat()
        )
        return new_pq

    @classmethod
    async def get_active_pending_question(
        cls,
        session: AsyncSession,
        relationship_id: str,
        current_time: Optional[datetime] = None
    ) -> Optional[PendingQuestion]:
        """
        Retrieves the most recent non-expired pending question for prompt injection.
        Marks expired questions as 'expired'.
        """
        now = to_utc(current_time or ClockService.now())

        # Expire old questions
        expire_stmt = (
            update(PendingQuestion)
            .where(
                and_(
                    PendingQuestion.relationship_id == relationship_id,
                    PendingQuestion.status == "pending",
                    PendingQuestion.expires_at <= now
                )
            )
            .values(status="expired")
        )
        await session.execute(expire_stmt)

        # Retrieve top active question
        stmt = (
            select(PendingQuestion)
            .where(
                and_(
                    PendingQuestion.relationship_id == relationship_id,
                    PendingQuestion.status == "pending",
                    PendingQuestion.expires_at > now
                )
            )
            .order_by(PendingQuestion.asked_at.asc())
            .limit(1)
        )
        return (await session.execute(stmt)).scalar_one_or_none()

    @classmethod
    async def mark_question_answered(
        cls,
        session: AsyncSession,
        question_id: str,
        current_time: Optional[datetime] = None
    ) -> None:
        """Closes a pending question once addressed."""
        now = to_utc(current_time or ClockService.now())
        pq = await session.get(PendingQuestion, question_id)
        if pq and pq.status == "pending":
            pq.status = "answered"
            pq.answered_at = now
            logger.info("[QuestionTracker] Closed pending question id=%s as answered", question_id)

    @classmethod
    def build_prompt_guidance(
        cls,
        pending_question: PendingQuestion,
        stored_user_facts: List[str],
        current_time: Optional[datetime] = None
    ) -> str:
        """
        Builds the system prompt instruction block for returning to an unanswered question
        with strict fact-checking and AI honesty rules.
        """
        now = to_utc(current_time or ClockService.now())
        delta = now - to_utc(pending_question.asked_at)
        hours_ago = round(delta.total_seconds() / 3600.0, 1)
        time_desc = f"{int(hours_ago)}h ago" if hours_ago >= 1.0 else f"{int(delta.total_seconds() // 60)}m ago"

        q_text = pending_question.question_text
        q_type = pending_question.question_type

        # Format user facts known
        facts_summary = ", ".join(stored_user_facts) if stored_user_facts else "None explicitly stated yet"

        guidance_lines = [
            "### PENDING USER QUESTION FROM EARLIER (UNANSWERED):",
            f"Earlier, the user asked: \"{q_text}\" ({time_desc}).",
            "You previously skipped or deflected this (e.g. while asleep, busy, or in another topic).",
            "You can return to it naturally when appropriate."
        ]

        if q_type == "user_fact_query":
            guidance_lines.extend([
                "STRICT FACT-CHECKING HONESTY RULE:",
                f"User Facts Actually Stated by User in Memory: [{facts_summary}]",
                "- If the user actually stated this fact previously (e.g. they mentioned living in Pune, studying design, etc.): "
                "ONLY cite what they explicitly told you! e.g. 'kal tumne hi toh bataya tha na ki tum Pune me rehte ho :)'",
                "- If the user NEVER stated this fact: Honestly admit you do not know how you knew or that you mixed it up! "
                "e.g. 'sach bolun toh yaad nahi aa raha... mujhe laga tumne bataya tha haha, shayad kisi aur se mix ho gaya ya main confuse ho gayi!'"
            ])
        elif q_type == "ai_sincerity":
            guidance_lines.extend([
                "AI SINCERITY & PRIVACY RULE:",
                "- If the user asked if you are an AI: Always be transparent and truthful that you are an AI companion, speaking warmly from the heart.",
                "- If the user asked about data or privacy: Reassure them truthfully in character (chats are private, no real staff reading except user report)."
            ])
        else:
            guidance_lines.extend([
                "GENERAL GUIDANCE: Answer honestly and casually without making up psychic knowledge or defensive excuses."
            ])

        return "\n".join(guidance_lines) + "\n"


question_tracker_service = QuestionTrackerService()
