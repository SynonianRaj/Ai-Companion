"""
Continuity Service:
Generates and manages Aanya's daily micro-journal (4-6 events per day)
with recurring cast members, rotating topics, multi-day storylines (including Delhi trip),
real Indian calendar events (Panchang verified), and strict time-of-day chronological filtering.
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from zoneinfo import ZoneInfo
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
import httpx

from backend.app.core.config import settings
from backend.app.db.models import PersonaDailyNote, PersonaStoryline
from backend.app.db.session import to_utc
from backend.app.services.clock_service import ClockService
from backend.app.engine.indian_calendar import IndianCalendar
from backend.app.engine.cast import cast_manager

logger = logging.getLogger(__name__)

# Fallback deterministic notes pool covering varied dates, cast, and festivals
DETERMINISTIC_JOURNAL_DAYS: Dict[str, List[Dict[str, str]]] = {
    # Default Weekday Template
    "default_weekday": [
        {"time_bracket": "morning", "topic": "food", "text": "Morning: Rekha Didi arrived at 8:45 AM and made hot aloo parathas with fresh dahi; sat on the balcony with ginger tea."},
        {"time_bracket": "morning", "topic": "family", "text": "Morning: Papa forwarded a 6:15 AM WhatsApp quote about staying hydrated; called briefly to check if I switched off the geyser."},
        {"time_bracket": "afternoon", "topic": "work", "text": "Afternoon: Vikram from Fintech requested minor color tweaks on the mobile checkout button; wrapped it up in 40 minutes."},
        {"time_bracket": "afternoon", "topic": "friends", "text": "Afternoon: Rhea sent three frantic voice notes dissecting a terrible Hinge date at 12th Main Indiranagar."},
        {"time_bracket": "evening", "topic": "errands", "text": "Evening: Stepped down to 100 Feet Road for groceries; auto anna refused meter so walked to Nature's Basket in the pleasant breeze."},
        {"time_bracket": "night", "topic": "family", "text": "Night: Mummy video called while folding laundry in Delhi; complained about Delhi weather and told me to oil my hair."}
    ],
    # 2026-10-28: Normal day before Karwa Chauth (Delhi wedding arc prep)
    "2026-10-28": [
        {"time_bracket": "morning", "topic": "family", "text": "Morning: Papa called early to ask if I checked ticket confirmation for cousin Meera's wedding next week."},
        {"time_bracket": "morning", "topic": "food", "text": "Morning: Brewed a quick filter coffee and had toast while listening to When Chai Met Toast on the balcony."},
        {"time_bracket": "afternoon", "topic": "plans", "text": "Afternoon: Meera frantically sent Pinterest links for wedding e-invites; promised to help her finalize typography tonight."},
        {"time_bracket": "afternoon", "topic": "work", "text": "Afternoon: Focused design sprint on Figma redesigning a profile dashboard, strictly closed work by 5 PM."},
        {"time_bracket": "evening", "topic": "friends", "text": "Evening: Met Rhea near Defence Colony for iced pour-over; she talked about her work burnout while I sketched border motifs."},
        {"time_bracket": "night", "topic": "family", "text": "Night: Mummy called mentioning she's preparing sargi for Karwa Chauth tomorrow and asked if I'm eating properly."}
    ],
    # 2026-10-29: Karwa Chauth (Drik Panchang Verified)
    "2026-10-29": [
        {"time_bracket": "morning", "topic": "family", "text": "Morning: Woke up to Mummy's message in the family group; she's fasting today for Karwa Chauth and Papa sent flowers."},
        {"time_bracket": "morning", "topic": "food", "text": "Morning: Rekha Didi made poori and aloo sabzi for breakfast; reminded her to buy cooking oil tomorrow."},
        {"time_bracket": "afternoon", "topic": "work", "text": "Afternoon: Reviewed Figma comments from client; wrapped up mobile screens before lunch."},
        {"time_bracket": "afternoon", "topic": "friends", "text": "Afternoon: Tanya called from Gurgaon during her tea break; nostalgic chat about how loud Rohini terrace moon-sightings get."},
        {"time_bracket": "evening", "topic": "music", "text": "Evening: Rain clouds gathered over Indiranagar; listened to acoustic Hindi songs while watching the street lights turn on."},
        {"time_bracket": "night", "topic": "family", "text": "Night: Group video call on 'Sharma Parivar' at 8:45 PM after moonrise; Mummy looked elegant in red saree and broke her fast."}
    ],
    # 2026-10-30: Wedding Invite Finishing & Pre-Travel
    "2026-10-30": [
        {"time_bracket": "morning", "topic": "family", "text": "Morning: Finished exporting the final PDF invitation cards for Meera's wedding; she sent 10 heart emojis on WhatsApp."},
        {"time_bracket": "morning", "topic": "errands", "text": "Morning: Quick run to local chemist on 12th Main for travel vitamins; Manjunath dropped Instamart groceries at the door."},
        {"time_bracket": "afternoon", "topic": "work", "text": "Afternoon: Handed off design specs to developers so I don't have to touch Figma while visiting Delhi."},
        {"time_bracket": "afternoon", "topic": "friends", "text": "Afternoon: Kabir texted asking if I can bring Bangalore Mysore Pak and filter coffee decoction for his college friends."},
        {"time_bracket": "evening", "topic": "plans", "text": "Evening: Started pulling out ethnic clothes and kurtas from the wardrobe to pack for Delhi."},
        {"time_bracket": "night", "topic": "health", "text": "Night: Feeling a mild travel tiredness; had warm haldi doodh and fell asleep early."}
    ],
    # 2026-10-31: Packing & Preparing for Travel
    "2026-10-31": [
        {"time_bracket": "morning", "topic": "family", "text": "Morning: Papa texted reminding me to keep Aadhaar card handy and web check-in for tomorrow's Delhi flight."},
        {"time_bracket": "morning", "topic": "food", "text": "Morning: Made scrambled eggs and toast; cleared out the fridge before leaving for the week."},
        {"time_bracket": "afternoon", "topic": "errands", "text": "Afternoon: Landlord Mr. Krishnamurthy saw my suitcase while checking water meters and politely wished me safe travels."},
        {"time_bracket": "afternoon", "topic": "friends", "text": "Afternoon: Rhea dropped by for 20 minutes to give me her silver earrings to wear at Meera's sangeet."},
        {"time_bracket": "evening", "topic": "money", "text": "Evening: Transferred November rent via UPI to Mr. Krishnamurthy so it's settled before the 1st."},
        {"time_bracket": "night", "topic": "plans", "text": "Night: Packed laptop and charger; alarm set for early morning cab to Kempegowda Airport."}
    ],
    # 2026-11-01: Kannada Rajyotsava & Travel Day to Delhi (Rohini)
    "2026-11-01": [
        {"time_bracket": "morning", "topic": "errands", "text": "Morning: Cabs in Indiranagar decorated with red and yellow flags for Kannada Rajyotsava; festive Kannada songs playing at every circle."},
        {"time_bracket": "morning", "topic": "plans", "text": "Morning: Boarded morning flight from Bengaluru to Delhi; read design essays during the flight."},
        {"time_bracket": "afternoon", "topic": "family", "text": "Afternoon: Landed at IGI Airport, crisp Delhi autumn air hit immediately; Kabir came on his scooter to help with luggage at Rohini."},
        {"time_bracket": "afternoon", "topic": "food", "text": "Afternoon: Mummy served steaming hot ghar ki dal makhani and jeera rice; nothing beats home food in Delhi."},
        {"time_bracket": "evening", "topic": "family", "text": "Evening: Meera and Sudha Bua arrived at the house with wedding lehengas; living room filled with loud laughter and chai."},
        {"time_bracket": "night", "topic": "family", "text": "Night: Sitting on the old Delhi bedroom mattress talking to Mummy late into the night; feeling cozy and nostalgic."}
    ],
    # 2026-11-02: Delhi Wedding Sangeet & Relatives
    "2026-11-02": [
        {"time_bracket": "morning", "topic": "food", "text": "Morning: Chole bhature breakfast from the corner shop in Rohini; Papa reading the Hindi newspaper on the terrace."},
        {"time_bracket": "morning", "topic": "family", "text": "Morning: Helping Meera and cousins coordinate sangeet dance tracks; Rajesh Chacha arguing loudly about parking."},
        {"time_bracket": "afternoon", "topic": "errands", "text": "Afternoon: Rushed to Karol Bagh with Mummy to pick up stitched blouses and matching bangles; crazy Delhi traffic."},
        {"time_bracket": "afternoon", "topic": "family", "text": "Afternoon: Sudha Bua playfully asked when my turn for wedding shopping is coming; laughed it off and changed the topic."},
        {"time_bracket": "evening", "topic": "family", "text": "Evening: Mehendi ceremony started; hands full of mehendi so Kabir had to feed me snacks while making fun of me."},
        {"time_bracket": "night", "topic": "music", "text": "Night: Sangeet dance performances went on till 1:30 AM with dhol beats; feet hurting but had so much fun."}
    ],
    # 2026-11-03: Wedding Day & Family Function
    "2026-11-03": [
        {"time_bracket": "morning", "topic": "family", "text": "Morning: House buzzing with wedding chaos since 7 AM; relatives bustling around, ironing sarees and steaming sherwanis."},
        {"time_bracket": "morning", "topic": "food", "text": "Morning: Quick chai and mathri between helping Meera get her bridal jewelry sorted."},
        {"time_bracket": "afternoon", "topic": "family", "text": "Afternoon: Wedding venue in Chattarpur; stunning floral mandap and baraat music in the distance."},
        {"time_bracket": "afternoon", "topic": "friends", "text": "Afternoon: Tanya drove down to the venue for an hour to see Meera and catch up over chaat in the garden."},
        {"time_bracket": "evening", "topic": "family", "text": "Evening: Meera looked gorgeous during the varmala; Papa got a little emotional watching Bua."},
        {"time_bracket": "night", "topic": "health", "text": "Night: Reached home exhausted at 2:00 AM; feet aching, taking off heavy earrings with immense relief."}
    ]
}


class ContinuityService:
    """Manages Aanya's daily micro-journal and ongoing storylines."""

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
    async def get_or_create_active_storyline(
        cls,
        session: AsyncSession,
        persona_id: str = "aanya_v1",
        current_time: Optional[datetime] = None
    ) -> Optional[PersonaStoryline]:
        """
        Retrieves the current major storyline arc.
        E.g. Meera's wedding leading into the Delhi trip.
        """
        ist_now = cls.get_ist_now(current_time)
        date_str = ist_now.strftime("%Y-%m-%d")

        stmt = (
            select(PersonaStoryline)
            .where(
                and_(
                    PersonaStoryline.persona_id == persona_id,
                    PersonaStoryline.status == "active"
                )
            )
            .order_by(PersonaStoryline.created_at.desc())
        )
        active = (await session.execute(stmt)).scalar_one_or_none()
        if active:
            return active

        # Auto-provision Meera's wedding storyline around late October / early November 2026
        if "2026-10-25" <= date_str <= "2026-11-06":
            loc = "Delhi (Rohini)" if date_str >= "2026-11-01" else "Indiranagar, Bengaluru"
            storyline = PersonaStoryline(
                persona_id=persona_id,
                storyline_id="meera_wedding",
                title="Cousin Meera's Wedding in Delhi",
                current_day=1 if date_str < "2026-11-01" else (4 if date_str == "2026-11-01" else 5),
                total_days=6,
                arc_summary="Helping cousin Meera design digital wedding invitations, flying to Delhi for sangeet and wedding at family home in Rohini.",
                status="active",
                location_override=loc,
                created_at=to_utc(ClockService.now()),
                updated_at=to_utc(ClockService.now())
            )
            session.add(storyline)
            await session.commit()
            return storyline

        return None

    @classmethod
    async def get_or_create_daily_notes(
        cls,
        session: AsyncSession,
        persona_id: str = "aanya_v1",
        current_time: Optional[datetime] = None
    ) -> List[Any]:
        """
        Retrieves today's 4-6 daily notes for Aanya from the database.
        If not yet generated for today's IST date, generates them and stores them.
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

        # Generate new notes for today
        storyline = await cls.get_or_create_active_storyline(session, persona_id, current_time)
        notes = await cls._generate_daily_notes(date_str, ist_now, storyline)

        new_entry = PersonaDailyNote(
            persona_id=persona_id,
            date_str=date_str,
            notes=notes,
            created_at=to_utc(ClockService.now())
        )
        session.add(new_entry)
        await session.commit()
        return notes

    @classmethod
    async def _generate_daily_notes(
        cls,
        date_str: str,
        ist_now: datetime,
        storyline: Optional[PersonaStoryline] = None
    ) -> List[Any]:
        """
        Generates 4-6 small events for Aanya's day involving the cast,
        rotating topics, real calendar events, and active storyline.
        Falls back to curated deterministic pool if remote LLM call is unavailable.
        """
        # Check deterministic pool first for exact date matches
        if date_str in DETERMINISTIC_JOURNAL_DAYS:
            return DETERMINISTIC_JOURNAL_DAYS[date_str]

        # Check calendar context
        cal_ctx = IndianCalendar.get_context_for_date(ist_now)
        active_ev = cal_ctx.get("active_event")
        upcoming_ev = cal_ctx.get("upcoming_event")

        # Sample cast tendencies
        is_first = ist_now.day == 1
        sampled_cast = cast_manager.sample_daily_cast_tendencies(
            current_date_str=date_str,
            is_first_of_month=is_first,
            has_active_storyline=bool(storyline),
            active_storyline_id=storyline.storyline_id if storyline else None
        )

        day_name = ist_now.strftime("%A")
        is_weekend = day_name in ("Saturday", "Sunday")
        loc_str = storyline.location_override if (storyline and storyline.location_override) else "Indiranagar, Bengaluru"

        # Remote generation prompt
        cast_hints = "\n".join(f"- {c['cast_name']} ({c['relation']}): {c['tendency']} ({c['timing']})" for c in sampled_cast)
        festival_hint = f"Festival/Holiday Today: {active_ev['name']} - {active_ev['cues']}" if active_ev else (
            f"Upcoming in {upcoming_ev['days_away']} days: {upcoming_ev['name']}" if upcoming_ev else ""
        )
        story_hint = f"Ongoing Storyline: {storyline.title} - {storyline.arc_summary}" if storyline else ""

        prompt = f"""You are generating 4 to 6 small daily background events for Aanya for {day_name}, {date_str}.
Current Location: {loc_str}
Identity: 24-year-old freelance UI/UX designer. Delhi family (Mummy, Papa, brother Kabir). Lives in Indiranagar, Bengaluru.
{festival_hint}
{story_hint}
Sampled Cast & Quirks:
{cast_hints}

Rules:
1. Generate EXACTLY 5 or 6 small realistic moments across: Morning, Afternoon, Evening, Night.
2. Rotating topics: family, friends, food, music, errands, health, money, plans, work.
3. WORK/FIGMA CAP: At most ONE event may mention work or Figma. Keep it a minor detail.
4. If in Delhi, routine is family-centered; if in Bengaluru, normal Indiranagar life.
5. Ordinary boring days and bad moods are welcome. Never contradict her persona.

Respond ONLY with valid JSON:
{{
  "notes": [
    {{"time_bracket": "morning", "topic": "food", "text": "Morning: ..."}},
    {{"time_bracket": "morning", "topic": "family", "text": "Morning: ..."}},
    {{"time_bracket": "afternoon", "topic": "work", "text": "Afternoon: ..."}},
    {{"time_bracket": "evening", "topic": "friends", "text": "Evening: ..."}},
    {{"time_bracket": "night", "topic": "music", "text": "Night: ..."}}
  ]
}}"""

        if getattr(settings, "GEMINI_API_KEY", None):
            try:
                model = getattr(settings, "GEMINI_MODEL", "gemini-3.5-flash")
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={settings.GEMINI_API_KEY}"
                payload = {
                    "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature": 0.8,
                        "maxOutputTokens": 600,
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
                        if isinstance(parsed, dict) and "notes" in parsed and len(parsed["notes"]) >= 4:
                            return parsed["notes"]
            except Exception as e:
                logger.warning("Remote daily journal generation failed: %s. Using fallback.", e)

        # Fallback to default weekday template
        return DETERMINISTIC_JOURNAL_DAYS["default_weekday"]

    @classmethod
    async def get_daily_notes_for_time(
        cls,
        session: AsyncSession,
        persona_id: str = "aanya_v1",
        current_time: Optional[datetime] = None
    ) -> List[Dict[str, str]]:
        """
        Retrieves daily notes filtered chronologically up to the current IST time.
        Events after the current hour have not occurred yet and are not known as past facts!
        """
        ist_now = cls.get_ist_now(current_time)
        hour = ist_now.hour

        all_notes = await cls.get_or_create_daily_notes(session, persona_id, current_time)
        if not all_notes:
            return []

        # Standardize items to dict with 'time_bracket' and 'text'
        standardized = []
        for n in all_notes:
            if isinstance(n, dict):
                standardized.append(n)
            elif isinstance(n, str):
                tb = "morning"
                if "afternoon" in n.lower():
                    tb = "afternoon"
                elif "evening" in n.lower():
                    tb = "evening"
                elif "night" in n.lower():
                    tb = "night"
                standardized.append({"time_bracket": tb, "text": n})

        # Chronological filter:
        # hour < 12 (Morning): only 'morning'
        # 12 <= hour < 18 (Afternoon): 'morning' and 'afternoon'
        # 18 <= hour < 22 (Evening): 'morning', 'afternoon', and 'evening'
        # hour >= 22 (Night): all brackets
        allowed_brackets = {"morning"}
        if hour >= 12:
            allowed_brackets.add("afternoon")
        if hour >= 18:
            allowed_brackets.add("evening")
        if hour >= 22:
            allowed_brackets.add("night")

        filtered = [n for n in standardized if n.get("time_bracket") in allowed_brackets]
        return filtered if filtered else standardized[:2]

    @classmethod
    async def get_location_override(
        cls,
        session: AsyncSession,
        persona_id: str = "aanya_v1",
        current_time: Optional[datetime] = None
    ) -> Optional[str]:
        """Returns location override if Aanya is traveling on a storyline (e.g. Delhi trip)."""
        storyline = await cls.get_or_create_active_storyline(session, persona_id, current_time)
        if storyline and storyline.location_override:
            return storyline.location_override
        return None


continuity_service = ContinuityService()
