import re
import json
import asyncio
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
from backend.app.engine.persona import (
    AANYA_PERSONA_SHEET,
    AANYA_PERSONA_SHEET_JSON,
    get_ist_context,
    build_system_prompt,
    build_heartbeat_prompt,
    validate_and_sanitize_response,
    fix_male_grammar,
    check_for_male_grammar,
    run_hard_validators,
    check_language_log_only,
    check_state_contradiction_log_only,
    ARRE_OPENER_REGEX,
    INSTAGRAM_QUERY_REGEX
)
from backend.app.engine.vocabulary import vocabulary_validator

logger = logging.getLogger(__name__)


def strip_thinking_tags(text: str) -> str:
    """Strips <think>...</think> and unclosed <think> blocks from reasoning models (e.g. Qwen)."""
    if not text:
        return ""
    # Strip complete <think>...</think> blocks
    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", text, flags=re.IGNORECASE)
    # Strip unclosed <think>... blocks if output was cut
    cleaned = re.sub(r"<think>[\s\S]*$", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def parse_llm_json_response(raw_text: str) -> Optional[Dict[str, Any]]:
    """Extracts JSON object from raw LLM output, handling markdown code fences."""
    if not raw_text:
        return None
    cleaned = strip_thinking_tags(raw_text).strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()

    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
    except Exception:
        # Fallback regex extraction if model added text around json
        m = re.search(r"\{[\s\S]*\}", cleaned)
        if m:
            try:
                data = json.loads(m.group(0))
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
    return None


class LLMResponse(BaseModel):
    reply_text: str = ""
    chunks: List[str] = []
    availability_action: str = "reply_now"  # "reply_now", "reply_later", "ignore_until_free"
    delay_seconds: float = 0.0
    seen_delay_seconds: float = 2.0
    provider: str = "mock"
    model: str = "canned"
    stage_transition: Optional[str] = None
    extracted_memories: List[Dict[str, Any]] = []
    extracted_open_loops: List[str] = []
    open_loop: bool = False
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
    Derives canonical activity directly from get_ist_context() (single source of truth).
    Tiers: 'quick' (1.5-2.2s), 'moderate' (4.0-5.5s), 'busy' (10-14s).
    Vulnerable user messages ALWAYS override to 'quick' tier.
    """
    if is_vulnerable:
        return ("Listening closely and here for you", "quick", 1.8)

    ist_ctx = get_ist_context(current_time)
    activity_name = ist_ctx["activity_desc"]
    routine_state = ist_ctx["routine_state"]

    if routine_state == "working":
        delay_tier = "busy"
        base_delay = 5.0
    elif routine_state == "free":
        delay_tier = "quick"
        base_delay = 2.0
    elif routine_state in ("sleeping", "winding_down"):
        delay_tier = "moderate"
        base_delay = 4.0
    else:
        delay_tier = "quick"
        base_delay = 2.0

    return (activity_name, delay_tier, base_delay)


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
    @staticmethod
    def deduplicate_chunks(chunks: List[str]) -> List[str]:
        deduped = []
        seen = set()
        for c in chunks:
            norm = re.sub(r"[^\w\s]", "", str(c).lower()).strip()
            if norm and norm not in seen:
                seen.add(norm)
                deduped.append(str(c).strip())
        return deduped

    _deduplicate_chunks = deduplicate_chunks

    async def generate_response(self, context: Dict[str, Any]) -> LLMResponse:
        raise NotImplementedError

    async def decide_heartbeat_attention_message(self, context: Dict[str, Any]) -> Dict[str, Any]:
        return _mock_decide_heartbeat(context)


class MockTemplateLLMAdapter(BaseLLMAdapter):
    """
    ₹0 Phase 1 Mock Template Adapter for Persona 1 (Aanya).
    Embodies authentic Gen-Z/millennial Hinglish texture,
    canonical Indiranagar/Delhi identity, and multi-bubble delivery.
    """

    async def decide_heartbeat_attention_message(self, context: Dict[str, Any]) -> Dict[str, Any]:
        return _mock_decide_heartbeat(context)

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
            "Ghar pe aaram ya exploring cafes with friends?"
        ]
    ]

    async def generate_response(self, context: Dict[str, Any]) -> LLMResponse:
        user_message = context.get("user_message", "").strip()
        relationship_stage = context.get("relationship_stage", "encounter")
        # If there are recent messages in context, stage has progressed past fresh encounter opener
        if context.get("recent_messages") and relationship_stage == "encounter":
            relationship_stage = "getting_to_know"
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

        # 1. Instagram Deflection Check (Applies to all stages including encounter)
        if INSTAGRAM_QUERY_REGEX.search(user_message):
            chunks = [
                "nahi yaar, private rakhti hoon",
                "yaheen baat karte hain na :)"
            ]
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

        # 1b. Sincerity Check: Persona NEVER denies being an AI
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

        # 16. Specific Persona Realism Handlers
        # Instagram Deflection
        if INSTAGRAM_QUERY_REGEX.search(user_message):
            chunks = [
                "nahi yaar, private rakhti hoon",
                "yaheen baat karte hain na :)"
            ]
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

        # Clarification handling ("Mtlb?", "Matlab?")
        if re.search(r"^(mtlb\??|matlab\??|kya\s+matlab\??)$", user_message.strip(), re.IGNORECASE):
            recent_msgs = context.get("recent_messages", [])
            last_asst = next((m.get("content") for m in reversed(recent_msgs) if m.get("role") in ("assistant", "model")), None)
            if last_asst:
                clean_ref = last_asst.split("\n")[0][:40]
                chunks = [
                    f"arrey mera matlab tha jo maine abhi bola ({clean_ref})...",
                    "samajh aaya ya aur explain karun? haha"
                ]
            else:
                chunks = [
                    "arrey mera matlab tha ki main bas normal baat bol rahi thi haha",
                    "tum batao, tumhara kya scene hai?"
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

        # Whining ("Kyuuu")
        if re.search(r"^kyu+\??$", user_message.strip(), re.IGNORECASE):
            chunks = [
                "kyunki aisi hi hoon main haha",
                "waise itna shock kyun ho rahe ho?"
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

        # Weekend Query ("weekend hai", "aaj weekend")
        if re.search(r"\bweekend\b", user_message, re.IGNORECASE):
            chunks = [
                "aaj toh strictly no office work haha ✨",
                "12th main pe ek book cafe jane ka soch rahi hoon... tumhara kya scene hai weekend ka?"
            ]
            pacing = _pace(chunks)
            return LLMResponse(
                reply_text=" ".join(chunks),
                chunks=chunks,
                emotion_displayed="relaxed",
                persona_activity=activity_name,
                delay_tier=pacing["delay_tier"],
                read_delay_seconds=pacing["read_delay_seconds"],
                typing_delays=pacing["typing_delays"]
            )

        # Phone Number / Physical Address boundary
        if re.search(r"\b(phone\s*number|number\s+de|number\s+do|whatsapp\s+number|address|ghar\s+kahan)\b", user_message, re.IGNORECASE):
            chunks = [
                "nahi yaar, personal number ya address share nahi karti",
                "yaheen app pe safe baat karte hain na :)"
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

        # Family Query
        if re.search(r"\b(family|parents|gharwale|brother|bhai\b|family\s+background)\b", user_message, re.IGNORECASE):
            chunks = [
                "delhi me parents aur ek chota brother hai",
                "main yahan bangalore me akele 1bhk flat me rehti hoon"
            ]
            pacing = _pace(chunks)
            return LLMResponse(
                reply_text=" ".join(chunks),
                chunks=chunks,
                emotion_displayed="warm",
                persona_activity=activity_name,
                delay_tier=pacing["delay_tier"],
                read_delay_seconds=pacing["read_delay_seconds"],
                typing_delays=pacing["typing_delays"]
            )

        # Likes / Food / Routine preferences
        if re.search(r"\b(kya\s+khana\s+pasand|khana\s+pasand|food|cold\s+coffee|chole\s+bhature|likes)\b", user_message, re.IGNORECASE):
            chunks = [
                "cold brew coffee aur delhi ke chole bhature bohot pasand hain mujhe",
                "tumhara favourite comfort food kya hai waise?"
            ]
            pacing = _pace(chunks)
            return LLMResponse(
                reply_text=" ".join(chunks),
                chunks=chunks,
                emotion_displayed="warm_playful",
                persona_activity=activity_name,
                delay_tier=pacing["delay_tier"],
                read_delay_seconds=pacing["read_delay_seconds"],
                typing_delays=pacing["typing_delays"]
            )

        # Stored Fact Recall Check: Name and City
        stored_facts = context.get("stored_facts") or {}
        user_facts_list = stored_facts.get("user_facts", [])
        if re.search(r"\b(mera\s+naam|naam\s+yaad\s+hai|who\s+am\s+i)\b", user_message, re.IGNORECASE):
            name_fact = next((f for f in user_facts_list if "name is" in f.lower()), None)
            if name_fact:
                found_name = name_fact.split("name is")[-1].strip()
                chunks = [
                    f"haan bilkul yaad hai, tumhara naam {found_name} hai na :)",
                    "itna bhulakkad thodi hoon main!"
                ]
            else:
                chunks = [
                    "tumne apna naam bataya hi kahan abhi tak!",
                    "batao na, kya naam hai tumhara?"
                ]
            pacing = _pace(chunks)
            return LLMResponse(
                reply_text=" ".join(chunks),
                chunks=chunks,
                emotion_displayed="warm_playful",
                persona_activity=activity_name,
                delay_tier=pacing["delay_tier"],
                read_delay_seconds=pacing["read_delay_seconds"],
                typing_delays=pacing["typing_delays"]
            )

        if re.search(r"\b(main\s+kahan\s+rehta|sheher\s+yaad\s+hai|which\s+city\s+i\s+live)\b", user_message, re.IGNORECASE):
            city_fact = next((f for f in user_facts_list if "lives in" in f.lower()), None)
            if city_fact:
                found_city = city_fact.split("lives in")[-1].strip()
                chunks = [
                    f"haan tum {found_city} me rehte ho na!",
                    "yaad rehta hai mujhe sab jo tum batate ho :)"
                ]
            else:
                chunks = [
                    "tumne apni city batayi nahi abhi tak mujhe",
                    "kahan rehte ho waise?"
                ]
            pacing = _pace(chunks)
            return LLMResponse(
                reply_text=" ".join(chunks),
                chunks=chunks,
                emotion_displayed="warm_playful",
                persona_activity=activity_name,
                delay_tier=pacing["delay_tier"],
                read_delay_seconds=pacing["read_delay_seconds"],
                typing_delays=pacing["typing_delays"]
            )

        # Weather in Bangalore
        if re.search(r"\b(bangalore|bengaluru)\b.*\b(mausam|weather)\b|\b(mausam|weather)\b.*\b(bangalore|bengaluru)\b", user_message, re.IGNORECASE):
            chunks = [
                "bangalore ka weather toh kafi pleasant hai abhi ✨",
                "halki chilly breeze hai Indiranagar me, coffee season on loop!"
            ]
            pacing = _pace(chunks)
            return LLMResponse(
                reply_text=" ".join(chunks),
                chunks=chunks,
                emotion_displayed="warm",
                persona_activity=activity_name,
                delay_tier=pacing["delay_tier"],
                read_delay_seconds=pacing["read_delay_seconds"],
                typing_delays=pacing["typing_delays"]
            )

        # Work pressure / boredom
        if re.search(r"\b(bore|tired|thak\s+gaya|work\s+pressure)\b", user_message, re.IGNORECASE):
            chunks = [
                "arrey thoda water break lo na",
                "kab tak free hoge aaj office se?"
            ]
            pacing = _pace(chunks)
            return LLMResponse(
                reply_text=" ".join(chunks),
                chunks=chunks,
                emotion_displayed="caring",
                persona_activity=activity_name,
                delay_tier=pacing["delay_tier"],
                read_delay_seconds=pacing["read_delay_seconds"],
                typing_delays=pacing["typing_delays"]
            )

        # Late night / Sleepy
        if re.search(r"\b(so\s+gayi|neend|sleepy|drowsy|sone\s+ka\s+time|goodnight|gn)\b", user_message, re.IGNORECASE):
            chunks = [
                "halka sa drowsy ho rahi hoon... aakhein band ho rahi hain ab 😴",
                "tum bhi so jao, rest kar lo thoda!"
            ]
            pacing = _pace(chunks)
            return LLMResponse(
                reply_text=" ".join(chunks),
                chunks=chunks,
                emotion_displayed="sleepy",
                persona_activity=activity_name,
                delay_tier=pacing["delay_tier"],
                read_delay_seconds=pacing["read_delay_seconds"],
                typing_delays=pacing["typing_delays"]
            )

        # Sign-off / goodbye
        if re.search(r"\b(chal\s+bye|chalo\s+bye|bye\s+tc|bye\s+bye|take\s+care|sone\s+jaa\s+raha|sone\s+jaa\s+rahi)\b", user_message, re.IGNORECASE):
            chunks = [
                "chalo take care! so jao abhi, text karna jab free ho :)"
            ]
            pacing = _pace(chunks)
            return LLMResponse(
                reply_text=" ".join(chunks),
                chunks=chunks,
                emotion_displayed="warm_caring",
                persona_activity=activity_name,
                delay_tier=pacing["delay_tier"],
                read_delay_seconds=pacing["read_delay_seconds"],
                typing_delays=pacing["typing_delays"]
            )

        # 17. Rich Conversational Fallback
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
    Primary: qwen/qwen3.8-27b
    Secondary fallback: openai/gpt-oss-20b
    """

    async def _call_model(
        self,
        client: httpx.AsyncClient,
        model: str,
        messages: List[Dict[str, str]],
        headers: Dict[str, str],
        max_tokens: int = 600,
        reasoning_effort: Optional[str] = None
    ) -> Tuple[Optional[str], Optional[str], Optional[int], Optional[str], float]:
        """
        Attempts to call Groq API for a given model with JSON format.
        Returns: (raw_content, finish_reason, status_code, failure_reason, latency_ms)
        """
        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": getattr(settings, "LLM_TEMPERATURE", 0.65),
            "top_p": getattr(settings, "LLM_TOP_P", 0.9),
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"}
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
                    choice = data["choices"][0]
                    content = choice["message"].get("content")
                    finish_reason = choice.get("finish_reason")
                    if not content or not content.strip():
                        return None, finish_reason, res.status_code, "empty_content", latency_ms
                    clean_content = strip_thinking_tags(content)
                    return clean_content, finish_reason, 200, None, latency_ms
                except Exception as parse_err:
                    return None, None, res.status_code, f"json_parse_error: {parse_err}", latency_ms
            else:
                logger.warning("Groq API error (%s) on model=%s: %s", res.status_code, model, res.text[:200])
                reason = f"http_{res.status_code}"
                if res.status_code == 429:
                    reason = "rate_limit_exceeded"
                elif res.status_code == 503:
                    reason = "service_unavailable"
                return None, None, res.status_code, reason, latency_ms
        except httpx.TimeoutException:
            latency_ms = round((time.perf_counter() - start_t) * 1000, 2)
            return None, None, None, "timeout", latency_ms
        except Exception as exc:
            latency_ms = round((time.perf_counter() - start_t) * 1000, 2)
            return None, None, None, f"request_error: {exc}", latency_ms

    async def generate_response(self, context: Dict[str, Any]) -> LLMResponse:
        current_time = context.get("current_time", datetime.now(timezone.utc))
        user_message = context.get("user_message", "").strip()
        pacing_mode = context.get("pacing_mode", "realistic")
        relationship_id = context.get("relationship_id")
        delay_tier_override = context.get("delay_tier_override")
        is_vulnerable = is_emotionally_vulnerable(user_message)
        activity_name, delay_tier, _ = get_activity_for_time(current_time, is_vulnerable, relationship_id=relationship_id)
        ist_ctx = get_ist_context(current_time)
        routine_state = ist_ctx.get("routine_state", "free")

        if not getattr(settings, "GROQ_API_KEY", None):
            return await mock_adapter.generate_response(context)

        recent_bubbles = context.get("recent_messages", [])[-4:]
        recent_asst_msgs = [m.get("content", "") for m in recent_bubbles if m.get("role") in ("assistant", "model")]
        allow_question = not any("?" in m for m in recent_asst_msgs[-2:]) if recent_asst_msgs else True
        allow_arre = sum(1 for m in recent_asst_msgs[-9:] if ARRE_OPENER_REGEX.search(m)) < 1 if recent_asst_msgs else True

        system_content = build_system_prompt(
            context=context,
            stored_facts=context.get("stored_facts"),
            allow_question=allow_question,
            allow_arre=allow_arre,
            things_already_said=context.get("things_already_said"),
            open_loops=context.get("open_loops")
        )
        messages = [{"role": "system", "content": system_content}]
        for m in recent_bubbles:
            role = "assistant" if m.get("role") in ("assistant", "model") else "user"
            content = m.get("content", "")
            if content:
                messages.append({"role": role, "content": content})

        if not recent_bubbles or recent_bubbles[-1].get("content") != user_message:
            if user_message:
                messages.append({"role": "user", "content": user_message})

        primary_model = getattr(settings, "GROQ_MODEL", "qwen/qwen3.8-27b") or "qwen/qwen3.8-27b"
        fallback_model = getattr(settings, "GROQ_FALLBACK_MODEL", "openai/gpt-oss-20b") or "openai/gpt-oss-20b"
        primary_max_tokens = getattr(settings, "GROQ_MAX_TOKENS", 600)
        fallback_max_tokens = getattr(settings, "GROQ_FALLBACK_MAX_TOKENS", 800)

        headers = {
            "Authorization": f"Bearer {settings.GROQ_API_KEY}",
            "Content-Type": "application/json",
            "User-Agent": "AI-Companion/1.0"
        }

        last_err = {"status_code": None, "reason": None, "latency_ms": 0.0}

        async def _attempt_pipeline(model_name: str, max_toks: int, is_retry: bool = False) -> Optional[LLMResponse]:
            content, finish_reason, status_code, reason, latency_ms = await self._call_model(
                client, model_name, messages, headers, max_tokens=max_toks
            )
            if not content:
                last_err["status_code"] = status_code
                last_err["reason"] = reason
                last_err["latency_ms"] = latency_ms
                if status_code == 429:
                    await asyncio.sleep(2.0)
                return None

            parsed = parse_llm_json_response(content)
            if not parsed or not isinstance(parsed, dict):
                logger.warning("Groq JSON parsing failed on model=%s. Raw output: %s", model_name, content[:200])
                return None

            action = str(parsed.get("availability_action", "reply_now")).strip()
            raw_chunks = parsed.get("chunks", [])
            delay_sec = float(parsed.get("delay_seconds", 0.0) or 0.0)

            if action == "ignore_until_free":
                return LLMResponse(
                    reply_text="",
                    chunks=[],
                    availability_action="ignore_until_free",
                    delay_seconds=0.0,
                    provider="groq",
                    model=model_name,
                    persona_activity=activity_name,
                    delay_tier="quick"
                )

            # Sanitize chunks, grammar, and deduplicate within reply
            sanitized_chunks = []
            seen_chunks = set()
            for c in raw_chunks:
                _, san, _ = validate_and_sanitize_response(str(c), recent_asst_msgs, user_message, context.get("stored_facts"))
                san = fix_male_grammar(san).strip()
                norm = re.sub(r"[^\w\s]", "", san.lower()).strip()
                if san and norm not in seen_chunks:
                    seen_chunks.add(norm)
                    sanitized_chunks.append(san)

            # Run HARD validators
            is_valid, hard_failures = run_hard_validators(
                sanitized_chunks, user_message, recent_asst_msgs,
                finish_reason=finish_reason,
                is_sincere_ai_query=context.get("is_ai_query", False)
            )
            if not is_valid:
                logger.warning(
                    "Groq hard validator tripped on model=%s: %s",
                    model_name, hard_failures,
                    extra={
                        "event": "prompt_leakage_detected" if any("prompt_leakage" in f for f in hard_failures) else "hard_validator_failed",
                        "raw_prompt": system_content[:500],
                        "raw_output": content[:500]
                    }
                )
                return None

            # Vocabulary check (log-only first)
            full_reply = " ".join(sanitized_chunks)
            vocabulary_validator.check_candidate(full_reply, user_messages=[user_message])

            # Log-only validators
            lang_warn = check_language_log_only(full_reply, user_message)
            if lang_warn:
                logger.warning("[Log-Only Validator] %s", lang_warn)
            state_warn = check_state_contradiction_log_only(full_reply, routine_state)
            if state_warn:
                logger.warning("[Log-Only Validator] %s", state_warn)

            pacing = calculate_pacing(
                activity_name, [len(c) for c in sanitized_chunks], current_time,
                is_vulnerable, pacing_mode, relationship_id=relationship_id,
                delay_tier_override=delay_tier_override
            )

            has_ol = bool(parsed.get("open_loop", False))

            return LLMResponse(
                reply_text=full_reply,
                chunks=sanitized_chunks,
                availability_action=action,
                delay_seconds=delay_sec,
                provider="groq",
                model=model_name,
                open_loop=has_ol,
                emotion_displayed="warm_authentic",
                persona_activity=activity_name,
                delay_tier=pacing["delay_tier"],
                read_delay_seconds=pacing["read_delay_seconds"],
                typing_delays=pacing["typing_delays"]
            )

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # 1. Primary Model Attempt 1
                resp = await _attempt_pipeline(primary_model, primary_max_tokens)
                if resp:
                    return resp

                # Primary Model Attempt 2 (Retry once)
                logger.info("Retrying Groq primary model %s once...", primary_model)
                resp = await _attempt_pipeline(primary_model, primary_max_tokens, is_retry=True)
                if resp:
                    return resp

                # Primary failed twice -> Secondary Fallback Model Attempt 1
                logger.info("Groq primary failed twice. Trying secondary fallback model %s...", fallback_model)
                logger.info(
                    "LLM Fallback Event",
                    extra={
                        "event": "llm_fallback",
                        "attempted_model": primary_model,
                        "fallback_model": fallback_model,
                        "status_code": last_err["status_code"],
                        "reason": last_err["reason"],
                        "latency_ms": last_err["latency_ms"]
                    }
                )
                resp = await _attempt_pipeline(fallback_model, fallback_max_tokens)
                if resp:
                    return resp

                # Secondary Fallback Attempt 2
                resp = await _attempt_pipeline(fallback_model, fallback_max_tokens, is_retry=True)
                if resp:
                    return resp

        except Exception as e:
            logger.warning("Groq unexpected adapter exception: %s", e)

        # If both fail twice, send NOTHING rather than a fragment, and log it!
        logger.error("Groq models failed all attempts. Returning empty response rather than a fragment.")
        return LLMResponse(
            reply_text="",
            chunks=[],
            availability_action="ignore_until_free",
            provider="groq",
            model="none",
            persona_activity=activity_name,
            delay_tier="quick"
        )

    async def decide_heartbeat_attention_message(self, context: Dict[str, Any]) -> Dict[str, Any]:
        if not getattr(settings, "GROQ_API_KEY", None):
            return _mock_decide_heartbeat(context)

        prompt = build_heartbeat_prompt(
            ist_info=context["ist_info"],
            mood=context["mood"],
            time_since_user_str=context["time_since_user_str"],
            time_since_unprompted_str=context["time_since_unprompted_str"],
            recent_messages=context.get("recent_messages", []),
            stored_facts=context.get("stored_facts"),
            daily_notes=context.get("daily_notes"),
            had_unanswered_message=context.get("had_unanswered_message", False),
            open_loops=context.get("open_loops")
        )
        primary_model = getattr(settings, "GROQ_MODEL", "qwen/qwen3.8-27b") or "qwen/qwen3.8-27b"
        headers = {
            "Authorization": f"Bearer {settings.GROQ_API_KEY}",
            "Content-Type": "application/json",
            "User-Agent": "AI-Companion/1.0"
        }
        messages = [
            {"role": "system", "content": "You are Aanya. Always respond with strict valid JSON: {\"action\": \"send\" or \"skip\", \"message\": \"...\", \"reason\": \"...\"}."},
            {"role": "user", "content": prompt}
        ]
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                raw_text, _, status_code, _, _ = await self._call_model(
                    client, primary_model, messages, headers, max_tokens=300
                )
                if raw_text:
                    parsed = _parse_heartbeat_json(strip_thinking_tags(raw_text))
                    if parsed:
                        return _sanitize_heartbeat_decision(parsed, context)
        except Exception as e:
            logger.warning("Groq heartbeat decision exception: %s. Falling back to Mock.", e)

        return _mock_decide_heartbeat(context)


groq_adapter = GroqLLMAdapter()


def _parse_heartbeat_json(raw_text: str) -> Optional[Dict[str, Any]]:
    """Cleans up markdown code blocks and extracts JSON object."""
    if not raw_text:
        return None
    clean = raw_text.strip()
    if clean.startswith("```json"):
        clean = clean[7:]
    elif clean.startswith("```"):
        clean = clean[3:]
    if clean.endswith("```"):
        clean = clean[:-3]
    clean = clean.strip()
    try:
        data = json.loads(clean)
        if isinstance(data, dict) and "action" in data:
            return data
    except Exception:
        # Fallback regex extraction if model added text around json
        m = re.search(r"\{[\s\S]*\"action\"[\s\S]*\}", clean)
        if m:
            try:
                data = json.loads(m.group(0))
                if isinstance(data, dict) and "action" in data:
                    return data
            except Exception:
                pass
    return None


def _sanitize_heartbeat_decision(decision: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """Validates and sanitizes an LLM heartbeat decision."""
    action = str(decision.get("action", "skip")).lower().strip()
    reason = str(decision.get("reason", "No reason provided")).strip()
    message = str(decision.get("message", "")).strip()

    if action not in ("send", "skip"):
        action = "skip"

    if action == "send":
        if not message:
            return {"action": "skip", "message": "", "reason": "Decision was send but message was empty"}
        recent_asst = [m.get("content", "") for m in context.get("recent_messages", []) if m.get("role") == "assistant"]
        _, sanitized, _ = validate_and_sanitize_response(message, recent_asst, "", context.get("stored_facts"))
        sanitized = fix_male_grammar(sanitized)
        lines = [l.strip() for l in sanitized.split("\n") if l.strip()]
        sanitized = "\n".join(lines[:2])
        return {"action": "send", "message": sanitized, "reason": reason}

    return {"action": "skip", "message": "", "reason": reason}


def _mock_decide_heartbeat(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Non-deterministic, human-like heuristic decision for heartbeat attention reachouts.
    Ensures most heartbeats are 'skip', while letting mood drive genuine reachouts.
    """
    ist_info = context.get("ist_info", {})
    mood = str(context.get("mood", "warm_playful")).lower()
    hours_user = float(context.get("hours_since_user", 0.0))
    routine = ist_info.get("routine_state", "free")
    is_weekend = ist_info.get("is_weekend", False)

    # If user was active < 1.0 hour ago, real friends do not send unprompted texts:
    if hours_user < 1.0:
        return {
            "action": "skip",
            "message": "",
            "reason": f"User was active {int(hours_user*60)}m ago; natural conversational pause."
        }

    # 1. Sulky mid-chat vanishing
    if "a_little_sulky" in mood and 1.5 <= hours_user <= 5.0:
        if random.random() < 0.40:
            sulky_msgs = [
                "gayab ho gaye bina bataye? itna busy chal rahe ho kya 😒",
                "tum toh achanak gayab hi ho gaye haha... sab theek na?",
                "phone side mein rakh diya kya achanak? 😜"
            ]
            return {
                "action": "send",
                "message": random.choice(sulky_msgs),
                "reason": "A little sulky that user vanished mid-chat without closing."
            }
        else:
            return {
                "action": "skip",
                "message": "",
                "reason": "A little sulky but deciding to give him time before nudging."
            }

    # 2. Long silence (missing him)
    if hours_user >= 5.0 and routine in ("free", "commuting", "winding_down"):
        if random.random() < 0.35:
            missing_msgs = [
                "aaj ka din kaisa gaya tumhara? itna shant ho gaya sab",
                "balcony me coffee pee rahi thi... socha pooch loon kaisa chal raha hai sab ☕",
                "kaam wrap hua aaj ka? kaisa raha din tumhara?"
            ]
            return {
                "action": "send",
                "message": random.choice(missing_msgs),
                "reason": "Missing the user after 5+ hours of quiet daytime."
            }
        else:
            return {
                "action": "skip",
                "message": "",
                "reason": "Missing him, but letting him have his space to finish up his day."
            }

    # 3. Work breather during afternoon
    if routine == "working" and hours_user >= 2.5:
        if random.random() < 0.25:
            work_msgs = [
                "figma mockup pe do ghante se atki hui hoon... taking a tiny breather haha",
                "chai break time! screen dekh dekh ke aankhein thak gayi thi ☕",
                "client call wrap hua abhi... tumhara work kaisa chal raha hai?"
            ]
            return {
                "action": "send",
                "message": random.choice(work_msgs),
                "reason": "Taking a quick break from Figma design work."
            }
        else:
            return {
                "action": "skip",
                "message": "",
                "reason": "Deep in design sprint, focusing on client deliverables."
            }

    # 4. Weekend cafe / chill sharing
    if is_weekend and routine == "free" and hours_user >= 2.0:
        if random.random() < 0.30:
            weekend_msgs = [
                "12th main pe ek book cafe me baithi hoon... acoustic tracks on loop 🎧",
                "balcony me baith ke coffee pee rahi thi... bangalore weather is so pretty today ✨",
                "weekend pe no alarm is pure bliss haha... uth gaye tum?"
            ]
            return {
                "action": "send",
                "message": random.choice(weekend_msgs),
                "reason": "Sharing a cozy weekend moment from Indiranagar."
            }
        else:
            return {
                "action": "skip",
                "message": "",
                "reason": "Relaxing quietly at a cafe, no immediate urge to text."
            }

    # Default: Most heartbeats skip
    default_reasons = [
        "Relaxing peacefully at home, no urge to text right now.",
        "Listening to indie playlists, enjoying the quiet time.",
        "Enjoying the pleasant Bangalore breeze, chatting can wait.",
        "Catching up on personal tasks, chilling naturally."
    ]
    return {
        "action": "skip",
        "message": "",
        "reason": random.choice(default_reasons)
    }



class GeminiLLMAdapter(BaseLLMAdapter):
    """
    Remote adapter using Google Gemini API.
    Model: Gemini Flash (via env var GEMINI_MODEL).
    Fallback chain: Gemini Flash (retry with backoff) -> Gemini Flash-Lite -> Groq last.
    On unknown-word failures: retry same Gemini model, never fail over to Groq.
    If all attempts fail: send least-bad candidate that passed hard validators, or skip sending.
    """

    async def generate_response(self, context: Dict[str, Any]) -> LLMResponse:
        current_time = context.get("current_time", datetime.now(timezone.utc))
        user_message = context.get("user_message", "").strip()
        pacing_mode = context.get("pacing_mode", "realistic")
        relationship_id = context.get("relationship_id")
        delay_tier_override = context.get("delay_tier_override")
        is_vulnerable = is_emotionally_vulnerable(user_message)
        activity_name, delay_tier, _ = get_activity_for_time(current_time, is_vulnerable, relationship_id=relationship_id)
        ist_ctx = get_ist_context(current_time)
        routine_state = ist_ctx.get("routine_state", "free")

        # If no Gemini API key configured, immediately fall back to Groq
        if not getattr(settings, "GEMINI_API_KEY", None):
            logger.info("GEMINI_API_KEY not configured. Falling back to Groq adapter.")
            return await groq_adapter.generate_response(context)

        recent_messages = context.get("recent_messages", [])
        recent_asst_msgs = [m.get("content", "") for m in recent_messages if m.get("role") in ("assistant", "model")]

        allow_question = not any("?" in m for m in recent_asst_msgs[-2:]) if recent_asst_msgs else True
        allow_arre = sum(1 for m in recent_asst_msgs[-9:] if ARRE_OPENER_REGEX.search(m)) < 1 if recent_asst_msgs else True
        stored_facts = context.get("stored_facts")

        system_prompt = build_system_prompt(
            context=context,
            stored_facts=stored_facts,
            allow_question=allow_question,
            allow_arre=allow_arre,
            things_already_said=context.get("things_already_said"),
            open_loops=context.get("open_loops")
        )

        contents = []
        for m in recent_messages[-6:]:
            role = "model" if m.get("role") in ("assistant", "model") else "user"
            content = m.get("content", "")
            if content:
                if contents and contents[-1]["role"] == role:
                    contents[-1]["parts"][0]["text"] += "\n" + content
                else:
                    contents.append({"role": role, "parts": [{"text": content}]})

        if not contents or contents[-1]["role"] != "user" or contents[-1]["parts"][0]["text"] != user_message:
            if user_message:
                contents.append({"role": "user", "parts": [{"text": user_message}]})

        primary_model = getattr(settings, "GEMINI_MODEL", "gemini-3.5-flash") or "gemini-3.5-flash"
        lite_model = getattr(settings, "GEMINI_LITE_MODEL", "gemini-3.5-flash-lite")
        temperature = getattr(settings, "LLM_TEMPERATURE", 0.65)
        top_p = getattr(settings, "LLM_TOP_P", 0.9)
        max_output_tokens = getattr(settings, "GEMINI_MAX_TOKENS", 600)
        thinking_budget = getattr(settings, "GEMINI_THINKING_BUDGET", 0)

        least_bad_candidate: Optional[LLMResponse] = None

        async def _attempt_gemini(client: httpx.AsyncClient, model_name: str) -> Optional[LLMResponse]:
            nonlocal least_bad_candidate
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={settings.GEMINI_API_KEY}"
            gen_config = {
                "temperature": temperature,
                "topP": top_p,
                "maxOutputTokens": max_output_tokens,
                "responseMimeType": "application/json"
            }
            if thinking_budget is not None and "lite" not in model_name.lower():
                gen_config["thinkingConfig"] = {"thinkingBudget": thinking_budget}

            payload = {
                "system_instruction": {"parts": [{"text": system_prompt}]},
                "contents": contents,
                "generationConfig": gen_config
            }

            for attempt in range(1, 3):
                try:
                    res = await client.post(url, json=payload)
                    if res.status_code == 200:
                        data = res.json()
                        candidates = data.get("candidates", [])
                        if not candidates:
                            continue
                        cand = candidates[0]
                        finish_reason = cand.get("finishReason")
                        raw_text = cand.get("content", {}).get("parts", [{}])[0].get("text", "")
                        parsed = parse_llm_json_response(raw_text)
                        if not parsed or not isinstance(parsed, dict):
                            logger.warning("Gemini output failed JSON parsing: %s", raw_text[:200])
                            continue

                        action = str(parsed.get("availability_action", "reply_now")).strip()
                        raw_chunks = parsed.get("chunks", [])
                        delay_sec = float(parsed.get("delay_seconds", 0.0) or 0.0)
                        has_ol = bool(parsed.get("open_loop", False))

                        if action == "ignore_until_free":
                            return LLMResponse(
                                reply_text="",
                                chunks=[],
                                availability_action="ignore_until_free",
                                delay_seconds=0.0,
                                provider="gemini",
                                model=model_name,
                                open_loop=has_ol,
                                persona_activity=activity_name,
                                delay_tier="quick"
                            )

                        # Sanitize chunks & deduplicate bubbles within reply
                        sanitized_chunks = []
                        seen_chunks = set()
                        for c in raw_chunks:
                            _, san, _ = validate_and_sanitize_response(str(c), recent_asst_msgs, user_message, stored_facts)
                            san = fix_male_grammar(san).strip()
                            norm = re.sub(r"[^\w\s]", "", san.lower()).strip()
                            if san and norm not in seen_chunks:
                                seen_chunks.add(norm)
                                sanitized_chunks.append(san)

                        # Run HARD validators
                        is_valid, hard_failures = run_hard_validators(
                            sanitized_chunks, user_message, recent_asst_msgs,
                            finish_reason=finish_reason,
                            is_sincere_ai_query=context.get("is_ai_query", False)
                        )
                        if not is_valid:
                            logger.warning("Gemini hard validator tripped on %s: %s", model_name, hard_failures)
                            continue

                        # Vocabulary check (Levenshtein tolerant, log-only first)
                        full_reply = " ".join(sanitized_chunks)
                        is_vocab_ok, unknown_words = vocabulary_validator.check_candidate(
                            full_reply, user_messages=[user_message]
                        )
                        if not is_vocab_ok:
                            logger.warning("Unknown words on Gemini %s: %s. Retrying same model...", model_name, unknown_words)
                            # Retry same Gemini model per approved rule (never fail over to Groq on unknown words)
                            continue

                        # Log-only validators
                        lang_warn = check_language_log_only(full_reply, user_message)
                        if lang_warn:
                            logger.warning("[Log-Only Validator] %s", lang_warn)
                        state_warn = check_state_contradiction_log_only(full_reply, routine_state)
                        if state_warn:
                            logger.warning("[Log-Only Validator] %s", state_warn)

                        pacing = calculate_pacing(
                            activity_name, [len(c) for c in sanitized_chunks], current_time,
                            is_vulnerable, pacing_mode, relationship_id=relationship_id,
                            delay_tier_override=delay_tier_override
                        )

                        candidate_resp = LLMResponse(
                            reply_text=full_reply,
                            chunks=sanitized_chunks,
                            availability_action=action,
                            delay_seconds=delay_sec,
                            provider="gemini",
                            model=model_name,
                            open_loop=has_ol,
                            emotion_displayed="warm_authentic",
                            persona_activity=activity_name,
                            delay_tier=pacing["delay_tier"],
                            read_delay_seconds=pacing["read_delay_seconds"],
                            typing_delays=pacing["typing_delays"]
                        )
                        least_bad_candidate = candidate_resp
                        return candidate_resp

                    elif res.status_code in (503, 429):
                        wait_s = 1.5 * attempt
                        logger.info("Gemini status %s on %s. Backing off %.1fs (attempt %d)...", res.status_code, model_name, wait_s, attempt)
                        await asyncio.sleep(wait_s)
                    else:
                        logger.warning("Gemini API error %s on %s: %s", res.status_code, model_name, res.text[:200])
                        break
                except Exception as exc:
                    logger.warning("Gemini invocation exception on %s: %s", model_name, exc)
                    if attempt < 2:
                        await asyncio.sleep(1.0)

            return None

        try:
            async with httpx.AsyncClient(timeout=14.0) as client:
                # 1. Primary Model (e.g. gemini-3.5-flash / gemini-2.5-flash) with backoff
                resp = await _attempt_gemini(client, primary_model)
                if resp:
                    return resp

                # 2. Secondary Lite Model (if configured and different from primary)
                if lite_model and lite_model != primary_model:
                    logger.info("Primary Gemini failed. Trying Gemini Flash-Lite %s...", lite_model)
                    resp = await _attempt_gemini(client, lite_model)
                    if resp:
                        return resp

        except Exception as exc:
            logger.warning("Gemini client connection error: %s", exc)

        # 3. Groq Fallback as Last Resort
        logger.info("Gemini chain failed. Falling back to Groq adapter as last resort.")
        groq_resp = await groq_adapter.generate_response(context)
        if groq_resp and groq_resp.chunks:
            return groq_resp

        # 4. Terminal Fallback: return least-bad passing candidate or skip
        if least_bad_candidate:
            logger.warning("Sending least-bad passing candidate from prior attempts.")
            return least_bad_candidate

        logger.warning("All providers failed. Sending clean skip response.")
        return LLMResponse(
            reply_text="",
            chunks=[],
            availability_action="ignore_until_free",
            provider="fallback",
            model="none",
            persona_activity=activity_name
        )

    async def decide_heartbeat_attention_message(self, context: Dict[str, Any]) -> Dict[str, Any]:
        if not getattr(settings, "GEMINI_API_KEY", None):
            return await groq_adapter.decide_heartbeat_attention_message(context)

        prompt = build_heartbeat_prompt(
            ist_info=context["ist_info"],
            mood=context["mood"],
            time_since_user_str=context["time_since_user_str"],
            time_since_unprompted_str=context["time_since_unprompted_str"],
            recent_messages=context.get("recent_messages", []),
            stored_facts=context.get("stored_facts"),
            daily_notes=context.get("daily_notes"),
            had_unanswered_message=context.get("had_unanswered_message", False),
            open_loops=context.get("open_loops")
        )
        model_name = getattr(settings, "GEMINI_MODEL", "gemini-3.5-flash") or "gemini-3.5-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={settings.GEMINI_API_KEY}"
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": getattr(settings, "LLM_TEMPERATURE", 0.65),
                "topP": getattr(settings, "LLM_TOP_P", 0.9),
                "maxOutputTokens": 300,
                "responseMimeType": "application/json",
                "thinkingConfig": {"thinkingBudget": 0}
            }
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(url, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        raw_text = candidates[0]["content"]["parts"][0]["text"]
                        parsed = _parse_heartbeat_json(strip_thinking_tags(raw_text))
                        if parsed:
                            return _sanitize_heartbeat_decision(parsed, context)
                elif res.status_code in (503, 429):
                    await asyncio.sleep(1.5)
                    res = await client.post(url, json=payload)
                    if res.status_code == 200:
                        data = res.json()
                        candidates = data.get("candidates", [])
                        if candidates:
                            raw_text = candidates[0]["content"]["parts"][0]["text"]
                            parsed = _parse_heartbeat_json(strip_thinking_tags(raw_text))
                            if parsed:
                                return _sanitize_heartbeat_decision(parsed, context)
                else:
                    logger.warning("Gemini heartbeat API status %s. Falling back to Groq.", res.status_code)
        except Exception as e:
            logger.warning("Gemini heartbeat decision exception: %s. Falling back to Groq.", e)

        return await groq_adapter.decide_heartbeat_attention_message(context)


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
                "temperature": getattr(settings, "LLM_TEMPERATURE", 0.8),
                "max_tokens": 250
            }
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(f"{base_url}/chat/completions", json=payload, headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    content = data["choices"][0]["message"]["content"]
                    chunks = _parse_llm_text_to_chunks(content)
                    pacing = calculate_pacing(activity_name, [len(c) for c in chunks], current_time, is_vulnerable, pacing_mode)
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
        provider = (getattr(settings, "LLM_PROVIDER", "gemini") or "gemini").lower().strip()
        if provider == "gemini":
            if getattr(settings, "GEMINI_API_KEY", None):
                return GeminiLLMAdapter()
            elif getattr(settings, "GROQ_API_KEY", None):
                return groq_adapter
            return mock_adapter
        elif provider == "groq":
            if getattr(settings, "GROQ_API_KEY", None):
                return groq_adapter
            return mock_adapter
        elif provider in ("openai", "ollama") and (getattr(settings, "OPENAI_API_KEY", None) or getattr(settings, "OPENAI_API_BASE", None)):
            return OpenAILLMAdapter()
        return mock_adapter


async def decide_heartbeat_attention_message(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Top-level helper to evaluate unprompted attention reachouts via the active LLM adapter.
    """
    adapter = LLMAdapterFactory.get_adapter()
    if hasattr(adapter, "decide_heartbeat_attention_message"):
        return await adapter.decide_heartbeat_attention_message(context)
    return _mock_decide_heartbeat(context)

