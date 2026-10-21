import json
import logging
import asyncio
from typing import Dict, Any, Optional, List
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import settings
from backend.app.db.models import PushSubscription

logger = logging.getLogger(__name__)


class PushService:
    """
    Handles high-urgency VAPID Web Push notifications for mobile PWAs.
    Gracefully evicts expired endpoints (HTTP 404/410) and safely mocks
    push delivery when VAPID keys or pywebpush are not installed.
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
        Evicts invalid/unregistered endpoints automatically.
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
                from pywebpush import webpush, WebPushException
                subscription_info = {
                    "endpoint": sub.endpoint,
                    "keys": {
                        "p256dh": sub.p256dh,
                        "auth": sub.auth
                    }
                }
                
                # Execute in background thread to prevent blocking event loop
                await asyncio.to_thread(
                    webpush,
                    subscription_info=subscription_info,
                    data=payload,
                    vapid_private_key=settings.VAPID_PRIVATE_KEY,
                    vapid_claims={"sub": f"mailto:{getattr(settings, 'VAPID_CLAIM_EMAIL', 'admin@ai-companion.local')}"},
                    headers={"Urgency": "high", "TTL": "86400"}
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


push_service = PushService()
