import re
import random
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from pydantic import BaseModel


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


def get_activity_for_time(current_time: datetime, is_vulnerable: bool = False) -> Tuple[str, str, float]:
    """
    Returns (activity_name, delay_tier, base_read_delay_seconds).
    Tiers: 'quick' (2-4s), 'moderate' (6-10s), 'busy' (15-22s).
    Vulnerable user messages ALWAYS override to 'quick' tier.
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

    if 8.0 <= time_float < 10.5:
        return ("Morning chai & checking design emails", "quick", 2.5)
    elif 10.5 <= time_float < 13.0:
        return ("In a deep Figma UI design sprint", "moderate", 7.0)
    elif 13.0 <= time_float < 14.5:
        return ("Grabbing lunch at an Indiranagar cafe", "moderate", 8.5)
    elif 14.5 <= time_float < 17.5:
        return ("In a client design critique meeting", "busy", 16.0)
    elif 17.5 <= time_float < 19.5:
        return ("Metro commute & evening tea break", "moderate", 7.5)
    elif 19.5 <= time_float < 23.0:
        return ("Relaxing at home with indie music", "quick", 2.8)
    else:
        # 23:00 to 08:00
        return ("Winding down with late night playlist 🎧", "moderate", 5.0)


def calculate_pacing(
    activity: str,
    chunk_lengths: List[int],
    current_time: datetime,
    is_vulnerable: bool = False,
    pacing_mode: str = "realistic",
    rng_seed: Optional[int] = None
) -> Dict[str, Any]:
    """
    Pure deterministic function for calculating read delays and per-chunk typing delays.
    pacing_mode: 'realistic' or 'turbo'
    """
    if pacing_mode == "turbo":
        return {
            "read_delay_seconds": 0.0,
            "typing_delays": [0.2 for _ in chunk_lengths],
            "delay_tier": "turbo"
        }

    _, delay_tier, base_delay = get_activity_for_time(current_time, is_vulnerable)

    read_delay = base_delay
    if rng_seed is not None:
        r = random.Random(rng_seed)
        read_delay += (r.random() - 0.5) * 1.5

    read_delay = max(1.5, read_delay)
    if is_vulnerable:
        read_delay = min(read_delay, 2.5)

    typing_delays = []
    for length in chunk_lengths:
        duration = max(1.0, min(3.0, length * 0.035))
        if is_vulnerable:
            duration = min(duration, 1.8)
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


def get_opening_icebreaker(user_name: str, user_city: Optional[str], current_time: datetime) -> List[str]:
    """Generates the grounded stranger introduction bubbles."""
    clean_name = user_name.strip() if user_name else "there"
    chunk1 = f"Hey {clean_name}! Nice to connect with you :)"

    try:
        ist_tz = ZoneInfo("Asia/Kolkata")
    except Exception:
        ist_tz = timezone.utc
    ist_time = current_time.astimezone(ist_tz) if current_time.tzinfo else current_time.replace(tzinfo=timezone.utc).astimezone(ist_tz)
    hour = ist_time.hour

    if 8 <= hour < 12:
        chunk2 = "I'm Aanya btw. Was just having my morning chai before jumping into design work ☕"
    elif 12 <= hour < 17:
        chunk2 = "I'm Aanya btw. Was just wrapping up some Figma design mockups at my studio 💻"
    elif 17 <= hour < 21:
        chunk2 = "I'm Aanya btw. Was just taking an evening break after a long design sprint ✨"
    else:
        chunk2 = "I'm Aanya btw. Was just chilling with some indie music before winding down 🎧"

    detected = detect_city(user_city) if user_city else None
    if detected == "kolkata":
        chunk3 = "Aanya from Bangalore here. Kolkata se ho na tum? I've always had a soft spot for Kolkata's soul and Park Street in winter! Kaisa chal raha hai wahan sab?"
    elif detected == "delhi_ncr":
        chunk3 = "Aanya from Bangalore here! Main originally Delhi se hi hoon haha 😄 Delhi mein kahan rehte ho waise?"
    elif detected == "bengaluru":
        chunk3 = "Aanya here! Arre, you're in Bangalore too! Which area? Hope the traffic isn't driving you crazy today haha."
    elif detected == "mumbai":
        chunk3 = "Aanya from Bangalore here! Mumbai se ho? Marine Drive breeze and sea-facing cafe vibes are unmatched ✨ Kaisa chal raha hai wahan sab?"
    elif user_city and user_city.strip():
        chunk3 = f"Aanya from Bangalore here! Nice to meet someone from {user_city.strip().title()}. Tell me a bit about what it's like living there!"
    else:
        chunk3 = "Pehle yeh batao, which city are you texting from? Tell me a bit about yourself!"

    return [chunk1, chunk2, chunk3]


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
            "Achha suno, aaj ka din kaisa chal raha hai tumhara?",
            "Main toh Indiranagar studio mein baith ke illustrations finalize kar rahi hoon ✨"
        ],
        [
            "Sahi mein? That sounds pretty interesting yaar!",
            "Thoda aur batao na iske baare mein?"
        ],
        [
            "Haha arre yaar, that's such a relatable mood.",
            "Main bhi jab deadline mein hoti hoon toh sirf cold brew aur music pe survive karti hoon 🎧"
        ],
        [
            "Pakka? Mujhe laga tum mazak kar rahe ho!",
            "Tell me more, I'm genuinely curious :)"
        ],
        [
            "Sach batau, Bangalore weather today is so pretty.",
            "Evening stroll lene ka mann kar raha hai. Tumhara kya plan hai evening ka?"
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

        is_vulnerable = is_emotionally_vulnerable(user_message)
        activity_name, delay_tier, _ = get_activity_for_time(current_time, is_vulnerable)

        extracted_memories = []
        extracted_open_loops = []

        # 1. Sincerity Check: Persona NEVER denies being an AI
        if is_ai_query:
            chunks = [
                "Haan, honestly speaking, main ek AI persona hoon! Fictional personality hoon.",
                "I have my own simulated daily routine and Bengaluru lifestyle, but my conversations with you are genuine.",
                "I'm always here to listen and chat authentically :)"
            ]
            pacing = calculate_pacing(activity_name, [len(c) for c in chunks], current_time, is_vulnerable, pacing_mode)
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
            pacing = calculate_pacing(activity_name, [len(c) for c in chunks], current_time, is_vulnerable, pacing_mode)
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
            chunks = get_opening_icebreaker(user_name, user_city, current_time)
            pacing = calculate_pacing(activity_name, [len(c) for c in chunks], current_time, is_vulnerable, pacing_mode)
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
                pacing = calculate_pacing(activity_name, [len(c) for c in chunks], current_time, is_vulnerable, pacing_mode)
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
                pacing = calculate_pacing(activity_name, [len(c) for c in chunks], current_time, is_vulnerable, pacing_mode)
                return LLMResponse(
                    reply_text=" ".join(chunks),
                    chunks=chunks,
                    emotion_displayed="warm_curious",
                    persona_activity=activity_name,
                    delay_tier=pacing["delay_tier"],
                    read_delay_seconds=pacing["read_delay_seconds"],
                    typing_delays=pacing["typing_delays"]
                )

        # 5. Memory Extraction Heuristics (Job, Interview, Trip, Pet, Name)
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

        # 6. Realistic Conflict Trigger
        if emotional_range.get("enabled", True) and emotional_range.get("intensity") == "realistic":
            if any(k in msg_lower for k in ["other girl", "dusri ladki", "date pe gaya", "ignore kar raha", "late reply"]):
                chunks = random.choice(self.REALISTIC_CONFLICT_CHUNKS)
                pacing = calculate_pacing(activity_name, [len(c) for c in chunks], current_time, is_vulnerable, pacing_mode)
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

        # 7. Contextual Memory Recall
        if stored_memories and random.random() < 0.4:
            mem = stored_memories[0]
            if "interview" in mem.content.lower():
                chunks = [
                    "Achha suno, mujhe yaad aaya... tumne pehle mention kiya tha na about your work/interview?",
                    "Did you hear anything back, ya abhi bhi pending hai result?"
                ]
                pacing = calculate_pacing(activity_name, [len(c) for c in chunks], current_time, is_vulnerable, pacing_mode)
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

        # 8. General Colloquial Hinglish Response
        chunks = random.choice(self.GENERAL_HINGLISH_CHUNKS)
        pacing = calculate_pacing(activity_name, [len(c) for c in chunks], current_time, is_vulnerable, pacing_mode)
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
