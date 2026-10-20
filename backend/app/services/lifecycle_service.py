from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
from sqlalchemy import select, and_, delete
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.config import settings
from backend.app.db.models import (
    RelationshipState, SubscriptionEntitlement, Memory, OpenLoop, Message, Conversation
)
from backend.app.services.clock_service import ClockService


class LifecycleService:
    """
    Implements the 15-day inactivity lifecycle, day-12 notice,
    pilot dormant state evaluation, and atomic relationship memory deletion.
    """

    @staticmethod
    async def is_user_entitled(session: AsyncSession, user_id: str) -> bool:
        """
        Returns True if user has an active daily, weekly, monthly plan,
        or an active Beta Entitlement (pilot testers).
        """
        now = ClockService.now()
        stmt = (
            select(SubscriptionEntitlement)
            .where(
                and_(
                    SubscriptionEntitlement.user_id == user_id,
                    SubscriptionEntitlement.status == "active"
                )
            )
        )
        result = await session.execute(stmt)
        entitlements = result.scalars().all()
        for ent in entitlements:
            if ent.ended_at is None or ent.ended_at > now:
                return True
        return False

    @classmethod
    async def record_user_interaction(
        cls,
        session: AsyncSession,
        relationship: RelationshipState
    ) -> None:
        """
        Updates last interaction time.
        If user has active plan/beta entitlement: expires_at is None.
        If unsubscribed: sets expires_at to now + 15 days.
        """
        now = ClockService.now()
        relationship.last_user_initiated_interaction_at = now
        relationship.updated_at = now

        # If relationship was dormant, user reconnection brings it back to active
        if relationship.lifecycle_status == "dormant":
            relationship.lifecycle_status = "active"

        entitled = await cls.is_user_entitled(session, relationship.user_id)
        if entitled:
            relationship.expires_at = None
        else:
            relationship.expires_at = now + timedelta(days=settings.INACTIVITY_EXPIRY_DAYS)

        await session.commit()

    @classmethod
    async def process_lifecycle_checks(
        cls,
        session: AsyncSession
    ) -> Dict[str, Any]:
        """
        Runs periodic lifecycle checks:
        1. Day 12 notification check (unsubscribed users).
        2. Day 15 expiry / dormant transition and deletion.
        """
        now = ClockService.now()
        results = {
            "reminders_sent": [],
            "dormant_transitions": [],
            "expired_and_deleted": []
        }

        stmt = select(RelationshipState).where(
            RelationshipState.lifecycle_status.in_(["active", "dormant"])
        )
        relationships = (await session.execute(stmt)).scalars().all()

        for rel in relationships:
            entitled = await cls.is_user_entitled(session, rel.user_id)
            if entitled:
                # Active plan stops the clock
                if rel.expires_at is not None:
                    rel.expires_at = None
                    await session.commit()
                continue

            # Unsubscribed user: calculate remaining time
            if rel.expires_at is None:
                rel.expires_at = rel.last_user_initiated_interaction_at + timedelta(days=settings.INACTIVITY_EXPIRY_DAYS)
                await session.commit()

            time_remaining = rel.expires_at - now

            # Day 12 Neutral Notice (approx 3 days or fewer remaining)
            if timedelta(0) < time_remaining <= timedelta(days=settings.INACTIVITY_EXPIRY_DAYS - settings.INACTIVITY_REMINDER_DAYS):
                results["reminders_sent"].append({
                    "relationship_id": rel.id,
                    "user_id": rel.user_id,
                    "days_remaining": max(1, time_remaining.days),
                    "notice_text": (
                        "Notice from AI Companion: Your relationship memory will expire and be deleted "
                        f"in {max(1, time_remaining.days)} days due to inactivity, under our retention policy. "
                        "Subscribers keep their memories."
                    )
                })

            # Day 15 Threshold reached or passed
            elif time_remaining <= timedelta(0):
                # Check if testing pilot dormant state first
                if rel.lifecycle_status == "active":
                    rel.lifecycle_status = "dormant"
                    results["dormant_transitions"].append(rel.id)
                    await session.commit()
                else:
                    # Execute permanent deletion once confirmed expired
                    rel.lifecycle_status = "expired"
                    await session.commit()
                    deleted_counts = await cls.execute_relationship_deletion(session, rel.id)
                    results["expired_and_deleted"].append({
                        "relationship_id": rel.id,
                        "deleted_counts": deleted_counts
                    })

        return results

    @staticmethod
    async def execute_relationship_deletion(
        session: AsyncSession,
        relationship_id: str
    ) -> Dict[str, int]:
        """
        Idempotent permanent deletion of relationship-scoped context.
        Canonical Persona configuration remains untouched.
        """
        # Delete memories
        res_mem = await session.execute(
            delete(Memory).where(Memory.relationship_id == relationship_id)
        )
        # Delete open loops
        res_loops = await session.execute(
            delete(OpenLoop).where(OpenLoop.relationship_id == relationship_id)
        )
        # Delete messages
        res_msg = await session.execute(
            delete(Message).where(Message.relationship_id == relationship_id)
        )
        # Delete conversations
        res_conv = await session.execute(
            delete(Conversation).where(Conversation.relationship_id == relationship_id)
        )
        # Mark relationship deleted
        rel = await session.get(RelationshipState, relationship_id)
        if rel:
            rel.lifecycle_status = "deleted"
            rel.familiarity_context = {}
            rel.boundaries = {}

        await session.commit()

        return {
            "memories_deleted": res_mem.rowcount,
            "open_loops_deleted": res_loops.rowcount,
            "messages_deleted": res_msg.rowcount,
            "conversations_deleted": res_conv.rowcount
        }


lifecycle_service = LifecycleService()
