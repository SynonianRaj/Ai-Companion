"""
Continuity Service: Generates and retrieves Aanya's daily micro-journal (Section C - Option 1).
Maintains authentic everyday continuity without bloating prompt context or breaking time-of-day consistency.
"""

import json
import logging
from datetime import datetime, timezone
from typing import List, Optional
from zoneinfo import ZoneInfo
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
import httpx

from backend.app.core.config import settings
from backend.app.db.models import PersonaDailyNote
from backend.app.services.clock_service import ClockService

logger = logging.getLogger(__name__)

# Fallback deterministic notes when offline or before remote call
DETERMINISTIC_DAILY_NOTES_POOL = [
    [
        "Morning: Spilled a bit of filter coffee on my sketchbook while trying to sketch wireframe layout ideas.",
        "Afternoon: Client sent 14 bullet points of feedback on the landing page mockup, spent 2 hours adjusting paddings.",
        "Evening: Stepped out to 12th Main Indiranagar, picked up some roasted beans from Blue Tokai and listened to Anuv Jain."
    ],
    [
        "Morning: Woke up to Bangalore rain hitting the balcony, sat with warm ginger tea listening to When Chai Met Toast.",
        "Afternoon: Figma crashed right in the middle of exporting assets for the mobile app prototype, luckily auto-saved.",
        "Evening: Quick walk around the neighborhood under the jacaranda trees, grabbed a plate of steaming momos."
    ],
    [
        "Morning: Brewed a fresh cold brew batch and cleaned my desk setup before the Monday design review.",
        "Afternoon: Great call with the product team, they actually approved my minimal typography proposal without arguments!",
        "Evening: Lounging on the rug with acoustic guitar tracks playing on loop, feeling completely relaxed."
    ],
    [
        "Morning: Balcony chai session while video calling mom in Delhi, she complained about the heat and told me to eat well.",
        "Afternoon: Spent 3 hours deep in focus redesigning an e-commerce checkout flow, lost track of time completely.",
        "Evening: Explored a cozy bookstore cafe near Defence Colony Indiranagar, found an old design anthology."
    ]
]


class ContinuityService:
    @classmethod
    def get_ist_now(cls, current_time: Optional[datetime] = None) -> datetime:
        try:
            ist_tz = ZoneInfo("Asia/Kolkata")
        except Exception:
            ist_tz = timezone.utc

        if current_time is None:
            now_utc = ClockService.now()
        elif current_time.tzinfo is None:
            now_utc = current_time.replace(tzinfo=timezone.utc)
        else:
            now_utc = current_time.astimezone(timezone.utc)

        return now_utc.astimezone(ist_tz)

    @classmethod
    async def get_or_create_daily_notes(
        cls,
        session: AsyncSession,
        persona_id: str = "aanya_v1",
        current_time: Optional[datetime] = None
    ) -> List[str]:
        """
        Retrieves today's 3 daily notes for Aanya from the database.
        If not yet generated for today's IST date, generates them once and stores them.
        """
        ist_now = cls.get_ist_now(current_time)
        date_str = ist_now.strftime("%Y-%m-%d")

        stmt = select(PersonaDailyNote).where(
            and_(
                PersonaDailyNote.persona_id == persona_id,
                PersonaDailyNote.date_str == date_str
            )
        )
        existing = (await session.execute(stmt)).scalar_one_or_none()
        if existing and existing.notes:
            return existing.notes

        # Generate new daily notes for today
        notes = await cls._generate_daily_notes(date_str, ist_now)

        new_entry = PersonaDailyNote(
            persona_id=persona_id,
            date_str=date_str,
            notes=notes,
            created_at=ClockService.now()
        )
        session.add(new_entry)
        await session.commit()
        return notes

    @classmethod
    async def _generate_daily_notes(cls, date_str: str, ist_now: datetime) -> List[str]:
        """
        Calls Gemini (or Groq) to generate 3 short, realistic bullet points of Aanya's day.
        Falls back to curated pool if remote call fails.
        """
        day_of_week = ist_now.strftime("%A")
        is_weekend = day_of_week in ("Saturday", "Sunday")

        prompt = f"""You are generating 3 short daily background notes for Aanya for {day_of_week}, {date_str}.
Identity constraints:
- 24 year old female freelance UI/UX designer living in Indiranagar, Bengaluru.
- Works on laptop (Figma), loves specialty coffee, indie music (Prateek Kuhad, Anuv Jain).
- Weekend: strictly NO office work (cafes, sketching, relaxing).
- Weekday: UI/UX design sprints, client reviews, evening strolls.

Generate EXACTLY 3 brief bullet points of small real things that happened or are planned in her day:
1. Morning (waking up, chai/coffee, morning mood)
2. Afternoon (work/client or cafe/relaxing)
3. Evening (stroll in Indiranagar, food, music)

Respond ONLY with valid JSON:
{{"notes": ["Morning: ...", "Afternoon: ...", "Evening: ..."]}}"""

        if getattr(settings, "GEMINI_API_KEY", None):
            try:
                model = getattr(settings, "GEMINI_MODEL", "gemini-3.5-flash")
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={settings.GEMINI_API_KEY}"
                payload = {
                    "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature": 0.8,
                        "maxOutputTokens": 300,
                        "responseMimeType": "application/json",
                        "thinkingConfig": {"thinkingBudget": 0}
                    }
                }
                async with httpx.AsyncClient(timeout=8.0) as client:
                    res = await client.post(url, json=payload)
                    if res.status_code == 200:
                        data = res.json()
                        raw = data["candidates"][0]["content"]["parts"][0]["text"]
                        parsed = json.loads(raw)
                        if isinstance(parsed, dict) and "notes" in parsed and len(parsed["notes"]) == 3:
                            return [str(n).strip() for n in parsed["notes"]]
            except Exception as e:
                logger.warning("Remote daily note generation failed: %s. Using pool.", e)

        # Fallback to deterministic pool based on date
        day_num = ist_now.day
        pool_idx = day_num % len(DETERMINISTIC_DAILY_NOTES_POOL)
        return DETERMINISTIC_DAILY_NOTES_POOL[pool_idx]

    @classmethod
    async def get_daily_notes_for_time(
        cls,
        session: AsyncSession,
        persona_id: str = "aanya_v1",
        current_time: Optional[datetime] = None
    ) -> List[str]:
        """
        Retrieves daily notes filtered to only what has happened up to the current IST time.
        Never reveals evening events at 9 AM!
        """
        ist_now = cls.get_ist_now(current_time)
        hour = ist_now.hour

        all_notes = await cls.get_or_create_daily_notes(session, persona_id, current_time)
        if not all_notes:
            return []

        # Filter chronologically
        if hour < 12:
            return all_notes[:1]  # Morning only
        elif hour < 18:
            return all_notes[:2]  # Morning & Afternoon
        else:
            return all_notes[:3]  # All 3 notes


continuity_service = ContinuityService()
