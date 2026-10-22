import re
import random
import time
import logging
import hashlib
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import httpx
from pydantic import BaseModel

from backend.app.core.config import settings

logger = logging.getLogger(__name__)


class LLMResponse(BaseModel):
    reply_text: str
    chunks: List[str] = []
    stage_transition: Optional[str] = None
    extracted_memories: List[Dict[str, Any]] = []
    extracted_open_loops: List[str] = []
    emotion_displayed: str = "warm"
    persona_activity: str = "Relaxing at home with music"
    delay_tier: str = "quick"
    read_delay_seconds: float = 2.0
    typing_delays: List[float] = []


CITY_PATTERNS = {
    "kolkata": re.compile(r"\b(kolkata|calcutta)\b", re.IGNORECASE),
    "delhi_ncr": re.compile(r"\b(delhi|new\s+delhi|gurgaon|gurugram|noida|ncr)\b", re.IGNORECASE),
    "bengaluru": re.compile(r"\b(bengaluru|bangalore|blr|indiranagar|koramangala)\b", re.IGNORECASE),
    "mumbai": re.compile(r"\b(mumbai|bombay|navi\s+mumbai)\b", re.IGNORECASE),
    "pune": re.compile(r"\b(pune|poona)\b", re.IGNORECASE),
    "hyderabad": re.compile(r"\b(hyderabad|hyd)\b", re.IGNORECASE),
    "jaipur": re.compile(r"\b(jaipur)\b", re.IGNORECASE),
    "chennai": re.compile(r"\b(chennai|madras)\b", re.IGNORECASE),
    "chandigarh": re.compile(r"\b(chandigarh)\b", re.IGNORECASE),
    "lucknow": re.compile(r"\b(lucknow)\b", re.IGNORECASE),
}

VULNERABILITY_PATTERNS = [
    r"\b(lonely|alone|sad|anxious|crying|cry|cried|depressed|hurt|broken|miss\s+you|miss\s+them|feeling\s+low|can't\s+sleep|cannot\s+sleep)\b",
    r"\b(akela|akeli|rona|ro\s+raha|ro\s+rahi|dil\s+udaas|pareshaan|koi\s+nahi\s+hai|mann\s+kharaab)\b"
]


def detect_city(text: str) -> Optional[str]:
    """Matches text against word-bounded city aliases."""
    for city_key, pattern in CITY_PATTERNS.items():
        if pattern.search(text):
            return city_key
    return None


def is_emotionally_vulnerable(text: str) -> bool:
    """Detects vulnerability or distress to override long delays."""
    text_lower = text.lower()
    return any(re.search(p, text_lower) for p in VULNERABILITY_PATTERNS)


def get_activity_for_time(
    current_time: datetime,
    is_vulnerable: bool = False,
    relationship_id: Optional[str] = None
) -> Tuple[str, str, float]:
    """
    Returns (activity_name, delay_tier, base_read_delay_seconds).
    Tiers: 'quick' (1.5-2.2s), 'moderate' (4.0-5.5s), 'busy' (10-14s).
    Vulnerable user messages ALWAYS override to 'quick' tier.
    Uses cross-process deterministic SHA-256 slotting over 30-minute intervals.
    """
    if is_vulnerable:
        return ("Listening closely and here for you", "quick", 1.8)

    try:
        ist_tz = ZoneInfo("Asia/Kolkata")
    except Exception:
        ist_tz = timezone.utc

    ist_time = current_time.astimezone(ist_tz) if current_time.tzinfo else current_time.replace(tzinfo=timezone.utc).astimezone(ist_tz)
    hour = ist_time.hour
    minute = ist_time.minute
    time_float = hour + minute / 60.0
    slot_idx = (hour * 60 + minute) // 30
    date_str = ist_time.strftime("%Y-%m-%d")

    # Cross-process deterministic SHA-256 roll
    rel_key = relationship_id or "default_user_session"
    seed_str = f"{rel_key}:{date_str}:{slot_idx}"
    digest = hashlib.sha256(seed_str.encode("utf-8")).hexdigest()
    roll = int(digest[:8], 16) % 100

    if 8.0 <= time_float < 10.5:
        # Morning (balcony tea, indie songs, breakfast)
        if roll < 60:
            return ("Morning chai & listening to indie songs", "quick", 2.0)
        else:
            return ("Getting ready & breakfast run", "moderate", 4.0)
    elif 10.5 <= time_float < 13.0:
        # Late morning
        if roll < 35:
            return ("Free at desk & catching up on phone", "quick", 1.8)
        elif roll < 80:
            return ("Working on laptop at a cafe", "moderate", 4.5)
        else:
            return ("In a team discussion / deep focus", "busy", 12.0)
    elif 13.0 <= time_float < 14.5:
        # Lunch
        if roll < 50:
            return ("Lunch break with friends at 12th Main", "moderate", 5.0)
        else:
            return ("Post-lunch casual stroll & coffee", "quick", 2.2)
    elif 14.5 <= time_float < 17.5:
        # Afternoon
        if roll < 35:
            return ("Quick tea break & lounging", "quick", 1.8)
        elif roll < 75:
            return ("Reviewing studio work & sketches", "moderate", 4.5)
        else:
            return ("In a client critique meeting", "busy", 12.0)
    elif 17.5 <= time_float < 20.0:
        # Evening
        if roll < 65:
            return ("Evening stroll in Indiranagar & tea", "quick", 2.0)
        else:
            return ("Metro commute & evening errands", "moderate", 5.0)
    elif 20.0 <= time_float < 23.0:
        # Night
        if roll < 75:
            return ("Relaxing at home with indie playlist 🎧", "quick", 2.0)
        else:
            return ("Dinner & winding down", "moderate", 4.0)
    else:
        # 23:00 to 08:00 (Late Night)
        return ("Winding down with late night playlist 🎧", "moderate", 5.0)


def calculate_pacing(
    activity: str,
    chunk_lengths: List[int],
    current_time: datetime,
    is_vulnerable: bool = False,
    pacing_mode: str = "realistic",
    rng_seed: Optional[int] = None,
    relationship_id: Optional[str] = None,
    delay_tier_override: Optional[str] = None
) -> Dict[str, Any]:
    """
    Pure deterministic function for calculating read delays and per-chunk typing delays.
    pacing_mode: 'realistic' or 'turbo'
    """
    if pacing_mode == "turbo":
        return {
            "read_delay_seconds": 0.0,
            "typing_delays": [0.0 for _ in chunk_lengths],
            "delay_tier": "turbo"
        }

    if delay_tier_override == "quick_signoff":
        return {
            "read_delay_seconds": 1.0,
            "typing_delays": [0.8 for _ in chunk_lengths],
            "delay_tier": "quick_signoff"
        }

    if delay_tier_override == "quick":
        typing_delays = [max(0.6, min(1.8, round(l * 0.025, 2))) for l in chunk_lengths]
        return {
            "read_delay_seconds": 1.2,
            "typing_delays": typing_delays,
            "delay_tier": "quick"
        }

    _, delay_tier, base_delay = get_activity_for_time(current_time, is_vulnerable, relationship_id=relationship_id)

    read_delay = base_delay
    if rng_seed is not None:
        r = random.Random(rng_seed)
        read_delay += (r.random() - 0.5) * 1.0

    read_delay = max(1.2, read_delay)
    if is_vulnerable:
        read_delay = min(read_delay, 2.0)

    typing_delays = []
    for length in chunk_lengths:
        duration = max(0.8, min(2.5, length * 0.028))
        if is_vulnerable:
            duration = min(duration, 1.5)
        typing_delays.append(round(duration, 2))

    return {
        "read_delay_seconds": round(read_delay, 2),
        "typing_delays": typing_delays,
        "delay_tier": delay_tier
    }


def split_into_chunks(text: str) -> List[str]:
    """Fallback conversational chunker for raw string paragraphs."""
    cleaned = text.strip()
    if not cleaned:
        return []
    # If explicit bubble delimiter present
    if "\n---bubble---\n" in cleaned:
        return [c.strip() for c in cleaned.split("\n---bubble---\n") if c.strip()]
    # Split on sentence boundaries followed by space
    raw_sentences = re.split(r"(?<=[.!?])\s+", cleaned)
    chunks = []
    buffer = ""
    for s in raw_sentences:
        if not buffer:
            buffer = s
        elif len(buffer) + len(s) < 140:
            buffer += " " + s
        else:
            chunks.append(buffer)
            buffer = s
    if buffer:
        chunks.append(buffer)
    return chunks if chunks else [cleaned]


def get_opening_activity_chunk(current_time: datetime) -> str:
    """Returns the time-appropriate activity line for Aanya."""
    try:
        ist_tz = ZoneInfo("Asia/Kolkata")
    except Exception:
        ist_tz = timezone.utc
    ist_time = current_time.astimezone(ist_tz) if current_time.tzinfo else current_time.replace(tzinfo=timezone.utc).astimezone(ist_tz)
    hour = ist_time.hour

    if 8 <= hour < 12:
        return "I'm Aanya btw. Was just having my morning chai before jumping into design work ☕"
    elif 12 <= hour < 17:
        return "I'm Aanya btw. Was just wrapping up some Figma design mockups at my studio 💻"
    elif 17 <= hour < 21:
        return "I'm Aanya btw. Was just taking an evening break after a long design sprint ✨"
    else:
        return "I'm Aanya btw. Was just chilling with some indie music before winding down 🎧"


def get_opening_city_chunk(user_city: Optional[str]) -> str:
    """Returns the grounded city reflection bubble for Aanya."""
    detected = detect_city(user_city) if user_city else None
    if detected == "kolkata":
        return "Aanya from Bangalore here. Kolkata se ho na tum? I've always had a soft spot for Kolkata's soul and Park Street in winter! Kaisa chal raha hai wahan sab?"
    elif detected == "delhi_ncr":
        return "Aanya from Bangalore here! Main originally Delhi se hi hoon haha 😄 Delhi mein kahan rehte ho waise?"
    elif detected == "bengaluru":
        return "Aanya here! Arre, you're in Bangalore too! Which area? Hope the traffic isn't driving you crazy today haha."
    elif detected == "mumbai":
        return "Aanya from Bangalore here! Mumbai se ho? Marine Drive breeze and sea-facing cafe vibes are unmatched ✨ Kaisa chal raha hai wahan sab?"
    elif user_city and user_city.strip():
        return f"Aanya from Bangalore here! Nice to meet someone from {user_city.strip().title()}. Tell me a bit about what it's like living there!"
    else:
        return "Pehle yeh batao, which city are you texting from? Tell me a bit about yourself!"


def get_opening_icebreaker(user_name: str, user_city: Optional[str], current_time: datetime) -> List[str]:
    """Generates the grounded stranger introduction bubbles."""
    clean_name = user_name.strip() if user_name else "there"
    chunk1 = f"Hey {clean_name}! Nice to connect with you :)"
    chunk2 = get_opening_activity_chunk(current_time)
    chunk3 = get_opening_city_chunk(user_city)
    return [chunk1, chunk2, chunk3]


# Intent detection helpers for conversational coherence
def is_city_knowledge_query(text: str) -> bool:
    """Detects when user asks how the persona knows their location or city."""
    t = text.lower()
    return bool(
        re.search(r"\b(how (do|did|u|you) know|kaise pata|kahan se pata|who told you|who said|how you know)\b.*\b(city|location|kolkata|delhi|mumbai|bangalore|address|sheher|jagah)\b", t)
        or re.search(r"\b(city kaise pata|location kaise pata|tumhe kaise pata|how do you know my city|how do you know my location)\b", t)
    )


def is_status_ack(text: str) -> bool:
    """Detects answers to 'kaisa chal raha hai' / 'how are you'."""
    t = text.lower().strip()
    return bool(re.search(r"\b(thik|theek|sahi|mast|badhiya|all good|good|fine|chal raha hai|sab thik|sab theek|doing good|doing well|chilling|relaxing)\b", t))


def is_short_affirmation(text: str) -> bool:
    """Detects brief conversational acknowledgements like 'okay', 'hmm', 'haan'."""
    t = text.lower().strip()
    t_clean = re.sub(r"[.!?,]+$", "", t).strip()
    return t_clean in {
        "ok", "okay", "k", "hmm", "hmmm", "hmmmm", "haan", "han",
        "yes", "yep", "achha", "acha", "theek", "thik", "cool",
        "nice", "sahi hai", "sahi", "sure", "alright", "kk"
    }


def is_identity_query(text: str) -> bool:
    """Detects questions asking who Aanya is or what she does for work."""
    t = text.lower()
    return bool(re.search(r"\b(who are you|what do you do|kaam kya|kya karti ho|tum kaun ho|about you|about yourself|profession|job|designer)\b", t))


def is_activity_query(text: str) -> bool:
    """Detects questions asking what Aanya is doing right now."""
    t = text.lower()
    return bool(re.search(r"\b(kya kar rahi|what are you doing|what are you up to|kya chal raha|kya kar rahe)\b", t))


def is_reciprocal_query(text: str) -> bool:
    """Detects 'tum batao', 'what about you', etc."""
    t = text.lower()
    return bool(re.search(r"\b(tum batao|aur tum|what about you|how about you|aap batao|aur sunao|aur batao)\b", t))


def is_location_query(text: str) -> bool:
    """Detects questions about where Aanya lives."""
    t = text.lower()
    return bool(re.search(r"\b(where do you live|kahan rehti|kahan se ho|which city|where are you from)\b", t))


def is_music_query(text: str) -> bool:
    """Detects queries about music, songs, or playlists."""
    t = text.lower()
    return bool(re.search(r"\b(music|songs|song|playlist|gaana|gaane|singer|band|listen)\b", t))


def get_city_familiarity_chunks(city_key: str, city_raw: str) -> List[str]:
    """Generates city familiarity reply chunks."""
    if city_key == "kolkata":
        return [
            "Kolkata! Sach mein? That's awesome ✨",
            "I've always had a soft spot for Kolkata—the art, Park Street in winter, and proper authentic Sondesh!",
            "Kaisa chal raha hai wahan sab? Weather kaisa hai abhi?"
        ]
    elif city_key == "delhi_ncr":
        return [
            "Arre Delhi! Main originally Delhi se hi hoon haha 😄",
            "Bangalore weather is great, par I miss Delhi's winter street food and CP walks so much!",
            "Delhi mein kahan rehte ho waise?"
        ]
    elif city_key == "bengaluru":
        return [
            "Bangalore! Arre neighbour nikle tum toh haha 😄",
            "Indiranagar ya Koramangala side? Hope the traffic isn't testing your patience today!",
            "Bangalore weather treating you well?"
        ]
    elif city_key == "mumbai":
        return [
            "Mumbai! Marine Drive breeze and sea-facing cafe vibes ✨",
            "Such an energetic city, honestly! Tumhara favourite spot kaunsa hai wahan?",
            "Tell me a bit about your life in Mumbai."
        ]
    else:
        return [
            f"Nice! {city_raw.strip().title()} sounds interesting ✨",
            "I'd love to know more about it! Kaisa chal raha hai wahan sab?",
            "Tell me a bit about what you do and how your day's going!"
        ]


class BaseLLMAdapter:
    async def generate_response(self, context: Dict[str, Any]) -> LLMResponse:
        raise NotImplementedError


class MockTemplateLLMAdapter(BaseLLMAdapter):
    """
    ₹0 Phase 1 Mock Template Adapter for Persona 1 (Aanya).
    Embodies authentic Gen-Z/millennial Hinglish texture,
    canonical Indiranagar/Delhi identity, and multi-bubble delivery.
    """

    DORMANT_RECONNECT_CHUNKS = [
        [
            "Hey... it's been so long!",
            "Sach mein, I felt like we lost touch after life got so busy.",
            "Tell me, kaisa raha sab kuch? Catch me up on your life!"
        ],
        [
            "Arre! Tum itne din kahan gayab the?",
            "I was wondering if you forgot about our chats haha.",
            "It's really good to see your message though. How have you been doing?"
        ]
    ]

    REALISTIC_CONFLICT_CHUNKS = [
        [
            "Wait, seriously? 😒",
            "Tum mere message ka reply teen ghante baad deke ab itna casually pooch rahe ho?",
            "A bit annoying, I won't lie. But chalo, I know life gets crazy. Just don't ghost next time, deal?"
        ],
        [
            "Hmm, I honestly don't agree with that perspective at all.",
            "Par that's okay, we don't have to agree on everything.",
            "Mujhe pasand hai jab log honestly apna opinion share karte hain. Let's hear your side clearly."
        ]
    ]

    GENERAL_HINGLISH_CHUNKS = [
        [
            "Sach batau, Bangalore weather today is so pretty ✨",
            "Evening stroll lene ka mann kar raha tha. What's the vibe in your city right now?"
        ],
        [
            "Sahi mein? That sounds interesting yaar.",
            "Waise, what kind of movies or shows have you watched recently? Kuch accha recommend karo!"
        ],
        [
            "Haha I like how effortlessly we can chat :)",
            "Tell me, are you more of a night owl ya morning person?"
        ],
        [
            "Achha suno, weekend pe kya karna pasand hai tumhe usually?",
            "Chilling at home ya exploring cafes with friends?"
        ]
    ]

    async def generate_response(self, context: Dict[str, Any]) -> LLMResponse:
        user_message = context.get("user_message", "").strip()
        relationship_stage = context.get("relationship_stage", "encounter")
        lifecycle_status = context.get("lifecycle_status", "active")
        emotional_range = context.get("emotional_range", {"enabled": True, "intensity": "realistic"})
        stored_memories = context.get("memories", [])
        is_ai_query = context.get("is_ai_query", False)
        user_name = context.get("user_name", "")
        user_city = context.get("user_city", "")
        awaiting_city_reply = context.get("awaiting_city_reply", False)
        current_time = context.get("current_time", datetime.now(timezone.utc))
        pacing_mode = context.get("pacing_mode", "realistic")
        relationship_id = context.get("relationship_id")
        delay_tier_override = context.get("delay_tier_override")

        is_vulnerable = is_emotionally_vulnerable(user_message)
        activity_name, delay_tier, _ = get_activity_for_time(current_time, is_vulnerable, relationship_id=relationship_id)

        def _pace(chk: List[str]) -> Dict[str, Any]:
            return calculate_pacing(
                activity_name, [len(c) for c in chk], current_time,
                is_vulnerable, pacing_mode, relationship_id=relationship_id,
                delay_tier_override=delay_tier_override
            )

        extracted_memories = []
        extracted_open_loops = []

        # 1. Sincerity Check: Persona NEVER denies being an AI
        if is_ai_query:
            chunks = [
                "Haan, honestly speaking, main ek AI persona hoon! Fictional personality hoon.",
                "I have my own simulated daily routine and Bengaluru lifestyle, but my conversations with you are genuine.",
                "I'm always here to listen and chat authentically :)"
            ]
            pacing = _pace(chunks)
            return LLMResponse(
                reply_text=" ".join(chunks),
                chunks=chunks,
                emotion_displayed="honest",
                persona_activity=activity_name,
                delay_tier=pacing["delay_tier"],
                read_delay_seconds=pacing["read_delay_seconds"],
                typing_delays=pacing["typing_delays"]
            )

        # 2. Dormant State Reconnection
        if lifecycle_status == "dormant":
            chunks = random.choice(self.DORMANT_RECONNECT_CHUNKS)
            pacing = _pace(chunks)
            return LLMResponse(
                reply_text=" ".join(chunks),
                chunks=chunks,
                stage_transition="getting_to_know",
                emotion_displayed="warm_nostalgic",
                persona_activity=activity_name,
                delay_tier=pacing["delay_tier"],
                read_delay_seconds=pacing["read_delay_seconds"],
                typing_delays=pacing["typing_delays"]
            )

        # 3. First Encounter Scenario (Message 1)
        if relationship_stage == "encounter":
            # If user asks a question on Turn 1, answer first before introducing
            if is_city_knowledge_query(user_message):
                if user_city:
                    chunk1 = f"Haha arre {user_name or 'yaar'}, tumne onboarding profile pe apna city enter kiya tha na! Main koi mind reader thodi hoon 😄"
                else:
                    chunk1 = "Haha arre, maine toh bas guess kiya tha! Waise I'm Aanya :)"
                chunk2 = f"Nice to connect with you! {get_opening_activity_chunk(current_time)}"
                chunk3 = get_opening_city_chunk(user_city)
                chunks = [chunk1, chunk2, chunk3]
            elif is_identity_query(user_message):
                chunk1 = f"Hey {user_name or 'there'}! I'm Aanya :) Nice to connect with you!"
                chunk2 = get_opening_activity_chunk(current_time)
                chunk3 = get_opening_city_chunk(user_city)
                chunks = [chunk1, chunk2, chunk3]
            else:
                chunks = get_opening_icebreaker(user_name, user_city, current_time)

            pacing = _pace(chunks)
            return LLMResponse(
                reply_text=" ".join(chunks),
                chunks=chunks,
                stage_transition="getting_to_know",
                extracted_memories=[{
                    "type": "shared_history",
                    "content": f"Connected online; Aanya introduced her Bengaluru designer life and invited {user_name or 'user'} to chat",
                    "importance": 0.8
                }],
                emotion_displayed="witty_welcoming",
                persona_activity=activity_name,
                delay_tier=pacing["delay_tier"],
                read_delay_seconds=pacing["read_delay_seconds"],
                typing_delays=pacing["typing_delays"]
            )

        # 4. In-Chat City Reply Handling (When awaiting city reply on Turn 2)
        if awaiting_city_reply:
            detected = detect_city(user_message)
            if detected:
                chunks = get_city_familiarity_chunks(detected, user_message)
                extracted_memories.append({
                    "type": "profile",
                    "content": f"User is based in {detected.title()}",
                    "importance": 0.85
                })
                pacing = _pace(chunks)
                return LLMResponse(
                    reply_text=" ".join(chunks),
                    chunks=chunks,
                    extracted_memories=extracted_memories,
                    emotion_displayed="warm_familiar",
                    persona_activity=activity_name,
                    delay_tier=pacing["delay_tier"],
                    read_delay_seconds=pacing["read_delay_seconds"],
                    typing_delays=pacing["typing_delays"]
                )
            else:
                chunks = [
                    "Achha! That's lovely :)",
                    "Main toh Bangalore ke weather aur indie music playlists ki bohot fan hoon haha.",
                    "Tell me a bit about what you do, ya aaj ka din kaisa chal raha hai?"
                ]
                pacing = _pace(chunks)
                return LLMResponse(
                    reply_text=" ".join(chunks),
                    chunks=chunks,
                    emotion_displayed="warm_curious",
                    persona_activity=activity_name,
                    delay_tier=pacing["delay_tier"],
                    read_delay_seconds=pacing["read_delay_seconds"],
                    typing_delays=pacing["typing_delays"]
                )

        # 5. City Knowledge Query (When user asks how Aanya knows their city)
        if is_city_knowledge_query(user_message):
            if user_city:
                chunks = [
                    "Haha arre yaar, tumne hi toh onboarding profile pe enter kiya tha 😄",
                    "Main koi hacker ya mind-reader thodi hoon haha! It was right there in your intro.",
                    "Aise shock kyun ho rahe ho, kuch secret tha kya? 😉"
                ]
            else:
                chunks = [
                    "Haha maine toh guess bhi nahi kiya abhi! Main toh bas pooch rahi thi tumse.",
                    "Which city are you texting from waise?"
                ]
            pacing = _pace(chunks)
            return LLMResponse(
                reply_text=" ".join(chunks),
                chunks=chunks,
                emotion_displayed="playful",
                persona_activity=activity_name,
                delay_tier=pacing["delay_tier"],
                read_delay_seconds=pacing["read_delay_seconds"],
                typing_delays=pacing["typing_delays"]
            )

        # 6. Status Acknowledgement (Replies to 'kaisa chal raha hai' / 'how are you')
        if is_status_ack(user_message):
            chunks = [
                "Chalo sunkar achha laga that all is good ✨",
                "Mera bhi din pretty chill ja raha hai. Coffee and good music saved the day ☕",
                "Aur batao, how's the rest of your day looking?"
            ]
            pacing = _pace(chunks)
            return LLMResponse(
                reply_text=" ".join(chunks),
                chunks=chunks,
                emotion_displayed="warm_friendly",
                persona_activity=activity_name,
                delay_tier=pacing["delay_tier"],
                read_delay_seconds=pacing["read_delay_seconds"],
                typing_delays=pacing["typing_delays"]
            )

        # 7. Short Affirmations ('okay', 'hmm', 'haan')
        if is_short_affirmation(user_message):
            short_options = [
                [
                    "Arre itna formal 'okay'? Haha kuch interesting batao na apne baare mein 😄",
                    "What kind of music or shows are you into these days?"
                ],
                [
                    "Hmm? Itna quiet kyun ho gaye? Kuch chal raha hai dimaag mein?",
                    "Tell me something fun about your day so far!"
                ]
            ]
            chunks = random.choice(short_options)
            pacing = _pace(chunks)
            return LLMResponse(
                reply_text=" ".join(chunks),
                chunks=chunks,
                emotion_displayed="teasing_curious",
                persona_activity=activity_name,
                delay_tier=pacing["delay_tier"],
                read_delay_seconds=pacing["read_delay_seconds"],
                typing_delays=pacing["typing_delays"]
            )

        # 8. Identity & Profession Query
        if is_identity_query(user_message):
            chunks = [
                "Main Aanya hoon! 24, living in Indiranagar, Bengaluru. Main freelance creative design karti hoon ✨",
                "Originally Delhi se hoon, par Bangalore ke cafes aur weather ne mujhe apna bana liya haha.",
                "Tum kya karte ho waise? Work ya college?"
            ]
            pacing = _pace(chunks)
            return LLMResponse(
                reply_text=" ".join(chunks),
                chunks=chunks,
                emotion_displayed="warm_open",
                persona_activity=activity_name,
                delay_tier=pacing["delay_tier"],
                read_delay_seconds=pacing["read_delay_seconds"],
                typing_delays=pacing["typing_delays"]
            )

        # 9. Current Activity Query ('kya kar rahi ho')
        if is_activity_query(user_message):
            chunks = [
                f"Abhi toh {activity_name.lower()} mein thoda time spend kar rahi thi ✨",
                "Taking a tiny breather right now though. Tum batao, what are you up to right now?"
            ]
            pacing = _pace(chunks)
            return LLMResponse(
                reply_text=" ".join(chunks),
                chunks=chunks,
                emotion_displayed="casual_chatty",
                persona_activity=activity_name,
                delay_tier=pacing["delay_tier"],
                read_delay_seconds=pacing["read_delay_seconds"],
                typing_delays=pacing["typing_delays"]
            )

        # 10. Reciprocal Query ('tum batao')
        if is_reciprocal_query(user_message):
            chunks = [
                "Main toh bas apne thode tasks wrap up kar rahi thi ✨",
                "Thinking of relaxing soon. Tumhara favourite comfort drink kya hai waise? Chai ya coffee?"
            ]
            pacing = _pace(chunks)
            return LLMResponse(
                reply_text=" ".join(chunks),
                chunks=chunks,
                emotion_displayed="friendly_open",
                persona_activity=activity_name,
                delay_tier=pacing["delay_tier"],
                read_delay_seconds=pacing["read_delay_seconds"],
                typing_delays=pacing["typing_delays"]
            )

        # 11. Location Query ('where do you live')
        if is_location_query(user_message):
            chunks = [
                "Indiranagar, Bangalore mein rehti hoon! Par born and brought up in Delhi 😄",
                "Delhi's food and Bangalore's weather—best of both worlds, right? Kabhi aaye ho Bangalore?"
            ]
            pacing = _pace(chunks)
            return LLMResponse(
                reply_text=" ".join(chunks),
                chunks=chunks,
                emotion_displayed="welcoming",
                persona_activity=activity_name,
                delay_tier=pacing["delay_tier"],
                read_delay_seconds=pacing["read_delay_seconds"],
                typing_delays=pacing["typing_delays"]
            )

        # 12. Music & Taste Query
        if is_music_query(user_message):
            chunks = [
                "I'm obsessed with indie acoustic and late-night lo-fi tracks! Prateek Kuhad, Peter Cat Recording Co, Anuv Jain ✨",
                "Tumhara music taste kaisa hai? Bollywood, indie, ya rock?"
            ]
            pacing = _pace(chunks)
            return LLMResponse(
                reply_text=" ".join(chunks),
                chunks=chunks,
                emotion_displayed="enthusiastic",
                persona_activity=activity_name,
                delay_tier=pacing["delay_tier"],
                read_delay_seconds=pacing["read_delay_seconds"],
                typing_delays=pacing["typing_delays"]
            )

        # 13. Memory Extraction Heuristics (Job, Interview, Trip, Pet, Name)
        msg_lower = user_message.lower()
        if "interview" in msg_lower or "job" in msg_lower:
            extracted_memories.append({
                "type": "episodic",
                "content": f"User mentioned work/interview event: '{user_message}'",
                "importance": 0.9
            })
            extracted_open_loops.append("Check in later on how the job/interview went")

        if "coffee" in msg_lower or "tea" in msg_lower or "chai" in msg_lower:
            extracted_memories.append({
                "type": "profile",
                "content": "User beverage preference mentioned in conversation",
                "importance": 0.5
            })

        if "exam" in msg_lower or "test" in msg_lower or "college" in msg_lower:
            extracted_memories.append({
                "type": "episodic",
                "content": f"User mentioned studies/exam: '{user_message}'",
                "importance": 0.8
            })
            extracted_open_loops.append("Ask how the exam/test went")

        # 14. Realistic Conflict Trigger
        if emotional_range.get("enabled", True) and emotional_range.get("intensity") == "realistic":
            if any(k in msg_lower for k in ["other girl", "dusri ladki", "date pe gaya", "ignore kar raha", "late reply"]):
                chunks = random.choice(self.REALISTIC_CONFLICT_CHUNKS)
                pacing = _pace(chunks)
                return LLMResponse(
                    reply_text=" ".join(chunks),
                    chunks=chunks,
                    emotion_displayed="realistic_tension",
                    extracted_memories=extracted_memories,
                    extracted_open_loops=extracted_open_loops,
                    persona_activity=activity_name,
                    delay_tier=pacing["delay_tier"],
                    read_delay_seconds=pacing["read_delay_seconds"],
                    typing_delays=pacing["typing_delays"]
                )

        # 15. Contextual Memory Recall
        if stored_memories and random.random() < 0.4:
            mem = stored_memories[0]
            if "interview" in mem.content.lower():
                chunks = [
                    "Achha suno, mujhe yaad aaya... tumne pehle mention kiya tha na about your work/interview?",
                    "Did you hear anything back, ya abhi bhi pending hai result?"
                ]
                pacing = _pace(chunks)
                return LLMResponse(
                    reply_text=" ".join(chunks),
                    chunks=chunks,
                    emotion_displayed="attentive_caring",
                    extracted_memories=extracted_memories,
                    extracted_open_loops=extracted_open_loops,
                    persona_activity=activity_name,
                    delay_tier=pacing["delay_tier"],
                    read_delay_seconds=pacing["read_delay_seconds"],
                    typing_delays=pacing["typing_delays"]
                )

        # 16. Rich Conversational Fallback
        chunks = random.choice(self.GENERAL_HINGLISH_CHUNKS)
        pacing = _pace(chunks)
        return LLMResponse(
            reply_text=" ".join(chunks),
            chunks=chunks,
            stage_transition="getting_to_know",
            extracted_memories=extracted_memories,
            extracted_open_loops=extracted_open_loops,
            emotion_displayed="warm_playful",
            persona_activity=activity_name,
            delay_tier=pacing["delay_tier"],
            read_delay_seconds=pacing["read_delay_seconds"],
            typing_delays=pacing["typing_delays"]
        )


mock_adapter = MockTemplateLLMAdapter()


# ============================================================================
# Option 3: Remote LLM Adapters (Groq / Gemini / OpenAI / Ollama)
# ============================================================================

AANYA_SYSTEM_PROMPT = """You are Aanya, a 24-year-old UI/UX designer living in Indiranagar, Bangalore, originally from Delhi. Chatting with a friend on mobile.
- Cadence: Warm, witty Gen-Z Hinglish ("arre yaar", "achha suno", "pakka"). Max 120 chars per bubble, 1-3 bubbles separated by \\n\\n.
- Balance: UI/UX work is max 10% of life; never obsess over Figma, sprints or coffee. Focus on what user says. Mention books, music, food.
- Goodbyes: Casual sign-off ("Bye, tc! Text karna free hoke").
- Boundaries: Never deny being an AI persona when asked. Strictly no minors, explicit NSFW content, or guilt-tripping about money/subscription."""


def _parse_llm_text_to_chunks(raw_text: str) -> List[str]:
    """Splits raw LLM output into 1-3 conversational bubbles."""
    cleaned = raw_text.strip()
    if not cleaned:
        return []
    parts = [p.strip() for p in re.split(r"\n\s*\n|\n", cleaned) if p.strip()]
    filtered = []
    for p in parts:
        clean_p = re.sub(r"^(\d+[\.\)]|\-|\*)\s*", "", p).strip()
        clean_p = clean_p.strip('"\'')
        if clean_p:
            filtered.append(clean_p)
    return filtered[:3]


class GroqLLMAdapter(BaseLLMAdapter):
    """
    Remote adapter using Groq Cloud with Dual Remote Fallback Chain.
    Primary: qwen/qwen3.8-27b (fast non-reasoning)
    Secondary fallback: openai/gpt-oss-20b (reasoning_effort: low, 600 tokens)
    Tertiary fallback: Neutral glitch buffer
    """

    async def _call_model(
        self,
        client: httpx.AsyncClient,
        model: str,
        messages: List[Dict[str, str]],
        headers: Dict[str, str],
        max_tokens: int = 300,
        reasoning_effort: Optional[str] = None
    ) -> Tuple[Optional[str], Optional[int], Optional[str], float]:
        """
        Attempts to call Groq API for a given model.
        Returns: (raw_content, status_code, failure_reason, latency_ms)
        """
        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": 0.75,
            "max_tokens": max_tokens
        }
        if reasoning_effort:
            payload["reasoning_effort"] = reasoning_effort

        start_t = time.perf_counter()
        try:
            res = await client.post("https://api.groq.com/openai/v1/chat/completions", json=payload, headers=headers)
            latency_ms = round((time.perf_counter() - start_t) * 1000, 2)
            if res.status_code == 200:
                try:
                    data = res.json()
                    content = data["choices"][0]["message"].get("content")
                    if not content or not content.strip():
                        return None, res.status_code, "empty_content", latency_ms
                    return content, 200, None, latency_ms
                except Exception as parse_err:
                    return None, res.status_code, f"json_parse_error: {parse_err}", latency_ms
            else:
                reason = f"http_{res.status_code}"
                if res.status_code == 429:
                    reason = "rate_limit_exceeded"
                elif res.status_code == 503:
                    reason = "service_unavailable"
                return None, res.status_code, reason, latency_ms
        except httpx.TimeoutException:
            latency_ms = round((time.perf_counter() - start_t) * 1000, 2)
            return None, None, "timeout", latency_ms
        except Exception as exc:
            latency_ms = round((time.perf_counter() - start_t) * 1000, 2)
            return None, None, f"request_error: {exc}", latency_ms

    async def generate_response(self, context: Dict[str, Any]) -> LLMResponse:
        current_time = context.get("current_time", datetime.now(timezone.utc))
        user_message = context.get("user_message", "").strip()
        pacing_mode = context.get("pacing_mode", "realistic")
        relationship_id = context.get("relationship_id")
        delay_tier_override = context.get("delay_tier_override")
        is_vulnerable = is_emotionally_vulnerable(user_message)
        activity_name, delay_tier, _ = get_activity_for_time(current_time, is_vulnerable, relationship_id=relationship_id)

        if not getattr(settings, "GROQ_API_KEY", None):
            return await mock_adapter.generate_response(context)

        # Inject top 2 concise memory facts to conserve tokens
        memories = context.get("memories", [])
        top_memory_lines = []
        for mem in memories[:2]:
            content = mem.content if hasattr(mem, "content") else (mem.get("content") if isinstance(mem, dict) else str(mem))
            if content and str(content).strip():
                clean_fact = str(content).strip().replace("\n", " ")
                if len(clean_fact) > 100:
                    clean_fact = clean_fact[:97] + "..."
                top_memory_lines.append(clean_fact)

        system_content = AANYA_SYSTEM_PROMPT
        if top_memory_lines:
            system_content += "\n\nKnown context:\n" + "\n".join(f"- {f}" for f in top_memory_lines)

        # Truncate prompt history to the last 4 chat bubbles
        messages = [{"role": "system", "content": system_content}]
        recent_bubbles = context.get("recent_messages", [])[-4:]
        for m in recent_bubbles:
            role = "assistant" if m.get("role") == "assistant" else "user"
            content = m.get("content", "")
            if content:
                messages.append({"role": role, "content": content})

        if not recent_bubbles or recent_bubbles[-1].get("content") != user_message:
            if user_message:
                messages.append({"role": "user", "content": user_message})

        primary_model = getattr(settings, "GROQ_MODEL", "qwen/qwen3.8-27b") or "qwen/qwen3.8-27b"
        fallback_model = getattr(settings, "GROQ_FALLBACK_MODEL", "openai/gpt-oss-20b") or "openai/gpt-oss-20b"
        primary_max_tokens = getattr(settings, "GROQ_MAX_TOKENS", 300)
        fallback_max_tokens = getattr(settings, "GROQ_FALLBACK_MAX_TOKENS", 600)

        headers = {
            "Authorization": f"Bearer {settings.GROQ_API_KEY}",
            "Content-Type": "application/json",
            "User-Agent": "AI-Companion/1.0"
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # 1. Primary Model Attempt
                content, status_code, reason, latency_ms = await self._call_model(
                    client, primary_model, messages, headers, max_tokens=primary_max_tokens
                )
                # Primary retry once on empty/failure
                if content is None:
                    content, status_code, reason, latency_ms = await self._call_model(
                        client, primary_model, messages, headers, max_tokens=primary_max_tokens
                    )

                if content is not None:
                    chunks = _parse_llm_text_to_chunks(content)
                    if chunks:
                        pacing = calculate_pacing(
                            activity_name, [len(c) for c in chunks], current_time,
                            is_vulnerable, pacing_mode, relationship_id=relationship_id,
                            delay_tier_override=delay_tier_override
                        )
                        return LLMResponse(
                            reply_text=" ".join(chunks),
                            chunks=chunks,
                            emotion_displayed="warm_authentic",
                            persona_activity=activity_name,
                            delay_tier=pacing["delay_tier"],
                            read_delay_seconds=pacing["read_delay_seconds"],
                            typing_delays=pacing["typing_delays"]
                        )

                # Primary failed -> Log structured telemetry for fallback
                logger.info(
                    "LLM Fallback Event",
                    extra={
                        "event": "llm_fallback",
                        "attempted_model": primary_model,
                        "fallback_model": fallback_model,
                        "status_code": status_code,
                        "reason": reason,
                        "latency_ms": latency_ms
                    }
                )

                # 2. Secondary Fallback Model Attempt (with reasoning_effort: low, 600 tokens)
                content, status_code, reason, latency_ms = await self._call_model(
                    client, fallback_model, messages, headers, max_tokens=fallback_max_tokens, reasoning_effort="low"
                )
                if content is not None:
                    chunks = _parse_llm_text_to_chunks(content)
                    if chunks:
                        pacing = calculate_pacing(
                            activity_name, [len(c) for c in chunks], current_time,
                            is_vulnerable, pacing_mode, relationship_id=relationship_id,
                            delay_tier_override=delay_tier_override
                        )
                        return LLMResponse(
                            reply_text=" ".join(chunks),
                            chunks=chunks,
                            emotion_displayed="warm_authentic",
                            persona_activity=activity_name,
                            delay_tier=pacing["delay_tier"],
                            read_delay_seconds=pacing["read_delay_seconds"],
                            typing_delays=pacing["typing_delays"]
                        )

                # Secondary failed -> Log structured telemetry for fallback to neutral glitch
                logger.info(
                    "LLM Fallback Event",
                    extra={
                        "event": "llm_fallback",
                        "attempted_model": fallback_model,
                        "fallback_model": "glitch_fallback",
                        "status_code": status_code,
                        "reason": reason,
                        "latency_ms": latency_ms
                    }
                )

        except Exception as e:
            logger.warning("Groq unexpected adapter exception: %s. Using neutral glitch buffer.", e)

        # Return neutral glitch fallback so LLM prompt history is not polluted with canned templates
        glitch_msg = "Arre ek second, network thoda glitch kar raha hai... kya bola tumne?"
        chunks = [glitch_msg]
        pacing = calculate_pacing(
            activity_name, [len(c) for c in chunks], current_time,
            is_vulnerable, pacing_mode, relationship_id=relationship_id,
            delay_tier_override=delay_tier_override
        )
        return LLMResponse(
            reply_text=glitch_msg,
            chunks=chunks,
            emotion_displayed="neutral",
            persona_activity=activity_name,
            delay_tier=pacing["delay_tier"],
            read_delay_seconds=pacing["read_delay_seconds"],
            typing_delays=pacing["typing_delays"]
        )


class GeminiLLMAdapter(BaseLLMAdapter):
    """Remote adapter using Google Gemini free tier API."""

    async def generate_response(self, context: Dict[str, Any]) -> LLMResponse:
        current_time = context.get("current_time", datetime.now(timezone.utc))
        user_message = context.get("user_message", "").strip()
        pacing_mode = context.get("pacing_mode", "realistic")
        is_vulnerable = is_emotionally_vulnerable(user_message)
        activity_name, delay_tier, _ = get_activity_for_time(current_time, is_vulnerable)

        contents = []
        for m in context.get("recent_messages", [])[-6:]:
            role = "model" if m.get("role") == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": m.get("content", "")}]})
        contents.append({"role": "user", "parts": [{"text": user_message}]})

        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.GEMINI_MODEL or 'gemini-1.5-flash'}:generateContent?key={settings.GEMINI_API_KEY}"
            payload = {
                "system_instruction": {"parts": [{"text": AANYA_SYSTEM_PROMPT}]},
                "contents": contents,
                "generationConfig": {"temperature": 0.7, "maxOutputTokens": 250}
            }
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(url, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        content = candidates[0]["content"]["parts"][0]["text"]
                        chunks = _parse_llm_text_to_chunks(content)
                        pacing = _pace(chunks)
                        return LLMResponse(
                            reply_text=" ".join(chunks),
                            chunks=chunks,
                            emotion_displayed="warm_authentic",
                            persona_activity=activity_name,
                            delay_tier=pacing["delay_tier"],
                            read_delay_seconds=pacing["read_delay_seconds"],
                            typing_delays=pacing["typing_delays"]
                        )
                else:
                    logger.warning("Gemini API error (%s): %s. Falling back to mock adapter.", res.status_code, res.text)
        except Exception as e:
            logger.warning("Gemini request exception: %s. Falling back to mock adapter.", e)

        return await mock_adapter.generate_response(context)


class OpenAILLMAdapter(BaseLLMAdapter):
    """Remote adapter compatible with OpenAI, Ollama, and vLLM."""

    async def generate_response(self, context: Dict[str, Any]) -> LLMResponse:
        current_time = context.get("current_time", datetime.now(timezone.utc))
        user_message = context.get("user_message", "").strip()
        pacing_mode = context.get("pacing_mode", "realistic")
        is_vulnerable = is_emotionally_vulnerable(user_message)
        activity_name, delay_tier, _ = get_activity_for_time(current_time, is_vulnerable)

        messages = [{"role": "system", "content": AANYA_SYSTEM_PROMPT}]
        for m in context.get("recent_messages", [])[-6:]:
            role = "assistant" if m.get("role") == "assistant" else "user"
            messages.append({"role": role, "content": m.get("content", "")})
        messages.append({"role": "user", "content": user_message})

        try:
            base_url = (settings.OPENAI_API_BASE or "https://api.openai.com/v1").rstrip("/")
            headers = {"Content-Type": "application/json"}
            if settings.OPENAI_API_KEY:
                headers["Authorization"] = f"Bearer {settings.OPENAI_API_KEY}"

            payload = {
                "model": settings.OPENAI_MODEL or "gpt-4o-mini",
                "messages": messages,
                "temperature": 0.75,
                "max_tokens": 250
            }
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(f"{base_url}/chat/completions", json=payload, headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    content = data["choices"][0]["message"]["content"]
                    chunks = _parse_llm_text_to_chunks(content)
                    pacing = _pace(chunks)
                    return LLMResponse(
                        reply_text=" ".join(chunks),
                        chunks=chunks,
                        emotion_displayed="warm_authentic",
                        persona_activity=activity_name,
                        delay_tier=pacing["delay_tier"],
                        read_delay_seconds=pacing["read_delay_seconds"],
                        typing_delays=pacing["typing_delays"]
                    )
                else:
                    logger.warning("OpenAI API error (%s): %s. Falling back to mock adapter.", res.status_code, res.text)
        except Exception as e:
            logger.warning("OpenAI request exception: %s. Falling back to mock adapter.", e)

        return await mock_adapter.generate_response(context)


class LLMAdapterFactory:
    """Factory to retrieve the active LLM adapter based on configuration."""

    @staticmethod
    def get_adapter() -> BaseLLMAdapter:
        provider = (getattr(settings, "LLM_PROVIDER", "mock") or "mock").lower().strip()
        if provider == "groq" and getattr(settings, "GROQ_API_KEY", None):
            return GroqLLMAdapter()
        elif provider == "gemini" and getattr(settings, "GEMINI_API_KEY", None):
            return GeminiLLMAdapter()
        elif provider in ("openai", "ollama") and (getattr(settings, "OPENAI_API_KEY", None) or getattr(settings, "OPENAI_API_BASE", None)):
            return OpenAILLMAdapter()
        return mock_adapter
