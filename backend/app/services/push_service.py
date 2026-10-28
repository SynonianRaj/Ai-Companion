import json
import logging
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional, List
from sqlalchemy import select, delete, and_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import settings
from backend.app.db.models import PushSubscription, NotificationOutbox
from backend.app.db.session import to_utc
from backend.app.services.clock_service import ClockService

logger = logging.getLogger(__name__)


class PushService:
    """
    Handles reliable VAPID Web Push notifications for mobile PWAs.
    Features:
    - Persistent DB-backed outbox (NotificationOutbox) with exactly-once delivery per message.
    - Thread-offloaded non-blocking pywebpush execution with explicit timeout.
    - In-app presence check (skips push if user is actively in the app).
    - Graceful eviction of expired endpoints (HTTP 404/410).
    - Safe mock fallback in dev/test when VAPID keys are absent.
    """

    @staticmethod
    async def register_subscription(
        session: AsyncSession,
        user_id: str,
        relationship_id: str,
        endpoint: str,
        p256dh: str,
        auth: str
    ) -> PushSubscription:
        """Saves or updates a Web Push subscription."""
        stmt = select(PushSubscription).where(PushSubscription.endpoint == endpoint)
        existing = (await session.execute(stmt)).scalar_one_or_none()

        if existing:
            existing.user_id = user_id
            existing.relationship_id = relationship_id
            existing.p256dh = p256dh
            existing.auth = auth
            await session.commit()
            return existing

        sub = PushSubscription(
            user_id=user_id,
            relationship_id=relationship_id,
            endpoint=endpoint,
            p256dh=p256dh,
            auth=auth
        )
        session.add(sub)
        await session.commit()
        return sub

    @classmethod
    async def enqueue_outbox_notification(
        cls,
        session: AsyncSession,
        user_id: str,
        relationship_id: str,
        conversation_id: str,
        message_id: str,
        scheduled_at: datetime,
        title: str,
        body: str,
        tag: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None
    ) -> Optional[NotificationOutbox]:
        """
        Enqueues exactly ONE outbox notification for an assistant reply or spontaneous outreach.
        Survives server restarts and worker scaling.
        Enforces exactly-once notification creation via DB unique constraint on message_id.
        """
        # Check if already enqueued for this message
        stmt = select(NotificationOutbox).where(NotificationOutbox.message_id == message_id)
        existing = (await session.execute(stmt)).scalar_one_or_none()
        if existing:
            return existing

        notif_tag = tag or f"aanya-msg-{message_id}"
        meta = dict(data or {})
        meta["relationship_id"] = relationship_id
        meta["conversation_id"] = conversation_id
        meta["message_id"] = message_id
        meta["url"] = meta.get("url", "/")

        outbox_entry = NotificationOutbox(
            user_id=user_id,
            relationship_id=relationship_id,
            conversation_id=conversation_id,
            message_id=message_id,
            scheduled_at=to_utc(scheduled_at),
            title=title,
            body=body[:150],  # Consolidate first bubble / snippet
            tag=notif_tag,
            status="pending",
            metadata_json=meta
        )
        session.add(outbox_entry)
        await session.flush()
        return outbox_entry

    @classmethod
    async def process_outbox(cls, session: AsyncSession) -> int:
        """
        Atomically claims and processes all due pending notifications from the database outbox.
        - Skips push if user is online in the app.
        - Offloads pywebpush network requests to background thread.
        - Marks records as sent, skipped, or failed.
        """
        from backend.app.services.presence_service import presence_service

        now = to_utc(ClockService.now())

        # Select due pending outbox items
        stmt = (
            select(NotificationOutbox)
            .where(
                and_(
                    NotificationOutbox.status == "pending",
                    NotificationOutbox.scheduled_at <= now
                )
            )
            .order_by(NotificationOutbox.scheduled_at.asc())
            .limit(20)
        )
        due_items = (await session.execute(stmt)).scalars().all()
        if not due_items:
            return 0

        # Mark claimed
        for item in due_items:
            item.status = "claimed"
            item.claimed_at = now
        await session.commit()

        processed_count = 0
        for item in due_items:
            try:
                # 1. Check in-app presence: If user is online, do not send push
                if presence_service.is_online(item.relationship_id):
                    item.status = "skipped"
                    meta = dict(item.metadata_json or {})
                    meta["skip_reason"] = "user_online"
                    item.metadata_json = meta
                    processed_count += 1
                    continue

                # 2. Dispatch push to user's registered devices
                delivered = await cls.send_notification(
                    session=session,
                    user_id=item.user_id,
                    title=item.title,
                    body=item.body,
                    tag=item.tag,
                    data=item.metadata_json
                )

                item.status = "sent"
                item.sent_at = to_utc(ClockService.now())
                meta = dict(item.metadata_json or {})
                meta["delivered_count"] = delivered
                item.metadata_json = meta
                processed_count += 1
            except Exception as exc:
                logger.warning("Error processing outbox item %s: %s", item.id, exc)
                item.status = "failed"
                meta = dict(item.metadata_json or {})
                meta["error"] = str(exc)
                item.metadata_json = meta

        await session.commit()
        return processed_count

    @classmethod
    async def send_notification(
        cls,
        session: AsyncSession,
        user_id: str,
        title: str,
        body: str,
        tag: str = "aanya-spontaneous",
        data: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        Sends high-urgency web push to all active subscriptions of user.
        Offloads synchronous pywebpush network requests via asyncio.to_thread with explicit timeout.
        Evicts invalid/unregistered endpoints automatically (HTTP 404/410).
        Returns number of successful deliveries.
        """
        stmt = select(PushSubscription).where(PushSubscription.user_id == user_id)
        subs = (await session.execute(stmt)).scalars().all()
        if not subs:
            return 0

        payload = json.dumps({
            "title": title,
            "body": body,
            "icon": "/icons/icon-192.png",
            "badge": "/icons/icon-192.png",
            "tag": tag,
            "data": data or {}
        })

        # Check if pywebpush and keys are present
        has_keys = bool(
            getattr(settings, "VAPID_PUBLIC_KEY", None) and
            getattr(settings, "VAPID_PRIVATE_KEY", None)
        )

        claim_email = getattr(settings, "VAPID_CLAIM_EMAIL", "mailto:support@aanya-companion.app")
        if not claim_email.startswith("mailto:"):
            claim_email = f"mailto:{claim_email}"

        sent_count = 0
        stale_sub_ids: List[str] = []

        for sub in subs:
            if not has_keys:
                logger.info(
                    "[MOCK PUSH] Dispatched push to user=%s (endpoint=%s...): '%s - %s'",
                    user_id, sub.endpoint[:30], title, body
                )
                sent_count += 1
                continue

            try:
                from pywebpush import webpush
                subscription_info = {
                    "endpoint": sub.endpoint,
                    "keys": {
                        "p256dh": sub.p256dh,
                        "auth": sub.auth
                    }
                }

                # Offload synchronous pywebpush to thread pool with explicit timeout
                await asyncio.to_thread(
                    webpush,
                    subscription_info=subscription_info,
                    data=payload,
                    vapid_private_key=settings.VAPID_PRIVATE_KEY,
                    vapid_claims={"sub": claim_email},
                    headers={"Urgency": "high", "TTL": "86400"},
                    timeout=8
                )
                sent_count += 1
            except Exception as exc:
                status_code = getattr(getattr(exc, "response", None), "status_code", None)
                if status_code in (404, 410):
                    logger.info("Evicting expired push subscription id=%s (status %s)", sub.id, status_code)
                    stale_sub_ids.append(sub.id)
                else:
                    logger.warning("WebPush failed for endpoint %s...: %s", sub.endpoint[:30], exc)

        # Evict stale subscriptions
        if stale_sub_ids:
            await session.execute(
                delete(PushSubscription).where(PushSubscription.id.in_(stale_sub_ids))
            )
            await session.commit()

        return sent_count

    @classmethod
    async def send_push_notification(
        cls,
        session: AsyncSession,
        user_id: str,
        title: str,
        body: str,
        relationship_id: Optional[str] = None,
        tag: str = "aanya-spontaneous",
        data: Optional[Dict[str, Any]] = None
    ) -> int:
        """Alias accepting relationship_id for backward compatibility."""
        payload_data = dict(data or {})
        if relationship_id:
            payload_data["relationship_id"] = relationship_id
        return await cls.send_notification(
            session=session,
            user_id=user_id,
            title=title,
            body=body,
            tag=tag,
            data=payload_data
        )


push_service = PushService()
