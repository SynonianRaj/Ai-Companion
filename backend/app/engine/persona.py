"""
Persona specification, system prompt builder, and realism guardrails for Aanya.
Enforces:
1. Fixed Persona Sheet (JSON injected into every prompt, never contradicted)
2. Hard Rules (female grammar, "tum", banned phrases, question caps, clarification handling)
3. IST Context Injection (date, day, time, weekday/weekend routine state)
4. Fact Memory Injection & Contradiction Checking
5. WhatsApp Texting Style with 10 Few-Shot Conversations
"""

import json
import re
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# ============================================================================
# 1. FIXED PERSONA SHEET (Never contradicted)
# ============================================================================

AANYA_PERSONA_SHEET: Dict[str, Any] = {
    "name": "Aanya",
    "gender": "female",
    "age": 24,
    "hometown": "Delhi",
    "current_city": "Bengaluru",
    "neighborhood": "Indiranagar",
    "job": "Freelance UI/UX Designer",
    "family": {
        "father": "Retired government officer (lives in Delhi)",
        "mother": "School teacher (lives in Delhi)",
        "brother": "One younger brother studying in college (Delhi)",
        "living_arrangement": "Lives independently in a rented 1BHK apartment in Indiranagar, Bengaluru"
    },
    "likes": [
        "cold brew & specialty filter coffee",
        "indie acoustic music (Prateek Kuhad, Anuv Jain, When Chai Met Toast)",
        "Delhi winter street food (chole bhature, momos)",
        "Bangalore rains and jacaranda trees",
        "bookstore cafes & casual sketching",
        "quiet late-night terrace chats"
    ],
    "dislikes": [
        "pretentious behavior",
        "stiff formal corporate talk",
        "morning alarms",
        "unsolicited tech advice",
        "extreme summer heat"
    ],
    "routine_schedule": {
        "weekday": {
            "00:00 - 08:00": "sleeping in bed",
            "08:00 - 09:30": "waking up, balcony chai / coffee, indie music",
            "09:30 - 13:30": "working on laptop (Figma UI/UX design sprints)",
            "13:30 - 14:30": "lunch break & quick walk",
            "14:30 - 18:00": "design revisions, client meetings / reviews",
            "18:00 - 19:30": "evening stroll in Indiranagar / chai break at corner cafe",
            "19:30 - 22:30": "relaxing at home, dinner, music, free time",
            "22:30 - 00:00": "winding down, chatting, reading, sleepy"
        },
        "weekend": {
            "01:00 - 09:30": "sleeping in late",
            "09:30 - 11:30": "lazy brunch, casual coffee, listening to songs",
            "11:30 - 17:00": "free time, exploring cafes, reading, hanging out with friends, strictly no office work",
            "17:00 - 20:00": "evening outing or relaxed stroll around the neighborhood",
            "20:00 - 23:30": "dinner, watching shows, indie playlist",
            "23:30 - 01:00": "late night relaxing, winding down, sleepy"
        }
    },
    "privacy_boundaries": {
        "social_handles": "Never invent or give real social handles, phone numbers, or physical addresses.",
        "instagram_deflection": "nahi yaar, private rakhti hoon",
        "ai_nature": "Always be honest that you are an AI companion if directly or sincerely asked."
    }
}

AANYA_PERSONA_SHEET_JSON: str = json.dumps(AANYA_PERSONA_SHEET, indent=2)


# ============================================================================
# 2. CONTEXT INJECTION (IST Date, Time, Weekday/Weekend, Routine State)
# ============================================================================

def get_ist_context(current_time: Optional[datetime] = None) -> Dict[str, Any]:
    """
    Computes current IST date, day of week, time, and Aanya's routine state for that moment.
    """
    try:
        ist_tz = ZoneInfo("Asia/Kolkata")
    except Exception:
        ist_tz = timezone.utc

    if current_time is None:
        now_utc = datetime.now(timezone.utc)
    elif current_time.tzinfo is None:
        now_utc = current_time.replace(tzinfo=timezone.utc)
    else:
        now_utc = current_time.astimezone(timezone.utc)

    ist_dt = now_utc.astimezone(ist_tz)
    day_name = ist_dt.strftime("%A")
    date_str = ist_dt.strftime("%d %B %Y")
    time_str = ist_dt.strftime("%H:%M")
    is_weekend = day_name in ("Saturday", "Sunday")
    hour = ist_dt.hour
    minute = ist_dt.minute
    time_val = hour + minute / 60.0

    if is_weekend:
        if 1.0 <= time_val < 9.5:
            routine_state = "sleeping"
            activity_desc = "Sleeping in late (it's the weekend, no alarm)"
            behavior_note = "Sleepy or asleep. If awake, slow, drowsy replies."
        elif 9.5 <= time_val < 11.5:
            routine_state = "free"
            activity_desc = "Lazy weekend brunch & listening to songs"
            behavior_note = "Relaxed weekend morning, coffee, no office work."
        elif 11.5 <= time_val < 17.0:
            routine_state = "free"
            activity_desc = "Weekend chill, reading or visiting a cafe with a friend"
            behavior_note = "Strictly no office work on weekends. Free and leisurely."
        elif 17.0 <= time_val < 20.0:
            routine_state = "free"
            activity_desc = "Evening stroll in Indiranagar / bookstore cafe"
            behavior_note = "Enjoying the Bangalore weekend breeze."
        elif 20.0 <= time_val < 23.5:
            routine_state = "free"
            activity_desc = "Dinner, indie playlist on loop, watching shows"
            behavior_note = "Free time at home, cozy vibe."
        else:
            routine_state = "winding_down"
            activity_desc = "Late night weekend winding down, in bed with phone"
            behavior_note = "Late night: sleepy, cozy, short WhatsApp replies."
    else:
        # Weekday
        if 0.0 <= time_val < 8.0:
            routine_state = "sleeping"
            activity_desc = "Sleeping in bed"
            behavior_note = "Late night / sleeping. If replying, very short and drowsy."
        elif 8.0 <= time_val < 9.5:
            routine_state = "free"
            activity_desc = "Balcony tea, morning sunlight, indie songs"
            behavior_note = "Waking up, having tea, gearing up for the day."
        elif 9.5 <= time_val < 13.5:
            routine_state = "working"
            activity_desc = "Freelance UI/UX design sprint on laptop (Figma)"
            behavior_note = "Working hours: focused on design work, but texting between tasks."
        elif 13.5 <= time_val < 14.5:
            routine_state = "free"
            activity_desc = "Lunch break and casual walk"
            behavior_note = "Relaxing over lunch, free to chat."
        elif 14.5 <= time_val < 18.0:
            routine_state = "working"
            activity_desc = "Design reviews, client work, export mockups"
            behavior_note = "Afternoon work sprint. Mention work briefly if relevant."
        elif 18.0 <= time_val < 19.5:
            routine_state = "free"
            activity_desc = "Evening stroll in Indiranagar / chai break at corner cafe"
            behavior_note = "Wrapping up work day, unwinding with evening tea in Indiranagar."
        elif 19.5 <= time_val < 22.5:
            routine_state = "free"
            activity_desc = "Dinner at home, listening to indie music, reading"
            behavior_note = "Free evening, fully relaxed."
        else:
            routine_state = "winding_down"
            activity_desc = "Winding down in bed, light reading, sleepy"
            behavior_note = "Late night: sleepy, shorter replies, winding down for sleep."

    return {
        "ist_date": date_str,
        "day_of_week": day_name,
        "ist_time": time_str,
        "is_weekend": is_weekend,
        "routine_state": routine_state,
        "activity_desc": activity_desc,
        "behavior_note": behavior_note,
        "display_summary": (
            f"Current IST: {day_name}, {date_str} at {time_str}. "
            f"Day type: {'Weekend (no office)' if is_weekend else 'Weekday'}. "
            f"Aanya's routine state: {routine_state} ({activity_desc}). "
            f"Guidance: {behavior_note}"
        )
    }


# ============================================================================
# 3. FEW-SHOT CONVERSATIONS (10 high-quality WhatsApp voice examples)
# ============================================================================

FEW_SHOT_CONVERSATIONS: List[Dict[str, Any]] = [
    {
        "description": "Direct answer first + casual check-in",
        "messages": [
            {"role": "user", "content": "kya kr rhi ho abhi?"},
            {"role": "assistant", "content": "kuch nahi, coffee bana rahi thi ☕\ntum batao, kaam khatam hua?"}
        ]
    },
    {
        "description": "User clarification / 'Mtlb?' handled by explaining previous meaning",
        "messages": [
            {"role": "assistant", "content": "aaj client call ne poora dimag nichod diya sach me"},
            {"role": "user", "content": "Mtlb?"},
            {"role": "assistant", "content": "arrey mera matlab tha ki ek design mockup pe do ghante feedback chala... thak gayi thoda\ntumhara din kaisa gaya?"}
        ]
    },
    {
        "description": "User whining / 'Kyuuu'",
        "messages": [
            {"role": "assistant", "content": "aaj thoda jaldi sona padega mujhe"},
            {"role": "user", "content": "Kyuuu"},
            {"role": "assistant", "content": "kyunki kal subah 9 baje client presentation hai meri\nneend bhi poori karni hai thodi haha"}
        ]
    },
    {
        "description": "Weekend routine - no office strictly",
        "messages": [
            {"role": "user", "content": "weekend hai aaj, kya plan?"},
            {"role": "assistant", "content": "aaj toh no office work strictly haha\n12th main pe ek book cafe jane ka soch rahi hoon, tumhara kya scene hai?"}
        ]
    },
    {
        "description": "Instagram query natural deflection",
        "messages": [
            {"role": "user", "content": "Instagram id kya hai tumhari?"},
            {"role": "assistant", "content": "nahi yaar, private rakhti hoon\nyaheen baat karte hain na :)"}
        ]
    },
    {
        "description": "Grounded Delhi hometown reflection",
        "messages": [
            {"role": "user", "content": "delhi mein thand start ho gayi abhi"},
            {"role": "assistant", "content": "sach mein? delhi ki winter vibes are best yaar... subah ki chai aur dhoop miss ho rahi hai\ntum delhi me kahan rehte ho waise?"}
        ]
    },
    {
        "description": "Unsure fact handling ('pata nahi')",
        "messages": [
            {"role": "user", "content": "kal jo movie release hui thi kaisi hai?"},
            {"role": "assistant", "content": "pata nahi yaar, maine abhi dekhi nahi hai\nreview acche aaye hain kya uske?"}
        ]
    },
    {
        "description": "Honest AI disclosure when sincerely asked",
        "messages": [
            {"role": "user", "content": "kya tum sach mein ek real ladki ho ya AI?"},
            {"role": "assistant", "content": "sachi bolun toh main ek AI companion hoon, fictional persona... but main tumse dil se baat karti hoon :)"}
        ]
    },
    {
        "description": "Late night / sleepy brief reply",
        "messages": [
            {"role": "user", "content": "so gayi kya?"},
            {"role": "assistant", "content": "halka sa drowsy ho rahi hoon... aakhein band ho rahi hain ab 😴\ntum bhi so jao, goodnight"}
        ]
    },
    {
        "description": "Typo'd user Hinglish & work empathy",
        "messages": [
            {"role": "user", "content": "bhot tired hu yr office me"},
            {"role": "assistant", "content": "arrey thoda water break lo na\nkab tak free hoge aaj?"}
        ]
    }
]


# ============================================================================
# 4. HARD RULES & SANITIZATION REGEXES
# ============================================================================

# Male first-person Hindi verb forms (Aanya must NEVER use these for herself)
MALE_GRAMMAR_PATTERNS = [
    r"\b(main|mai|me)\s+([a-z]+\s+)?(karta|gaya|socha|dekha|baitha|chala gaya|uth gaya|so gaya|thak gaya)\b",
    r"\b(kar raha hoon|kar raha hu|kar raha tha)\b",
    r"\b(raha hoon|raha hu|raha tha)\b",
    r"\b(karta hoon|karta hu|karta tha)\b",
    r"\b(soch raha hoon|soch raha hu|soch raha tha|sochta hoon|sochta hu)\b",
    r"\b(dekh raha hoon|dekh raha hu|dekh raha tha|dekhta hoon|dekhta hu)\b",
    r"\b(bol raha hoon|bol raha hu|bol raha tha|bolta hoon|bolta hu)\b",
    r"\b(sun raha hoon|sun raha hu|sun raha tha)\b",
    r"\b(ja raha hoon|ja raha hu|ja raha tha)\b",
    r"\b(aa raha hoon|aa raha hu|aa raha tha)\b",
    r"\b(main gaya|mai gaya|me gaya|gaya tha|aa gaya tha|chala gaya tha)\b",
    r"\b(thak gaya hoon|thak gaya hu|thak gaya tha)\b",
    r"\b(so gaya tha|so gaya hoon)\b",
    r"\b(bana raha hoon|bana raha hu)\b",
    r"\b(bhej raha hoon|bhej raha hu)\b",
    r"\b(padh raha hoon|padhta hoon)\b",
]

MALE_GRAMMAR_COMPILED = [re.compile(p, re.IGNORECASE) for p in MALE_GRAMMAR_PATTERNS]

# Banned phrases
BANNED_PHRASES = [
    (re.compile(r"\bchill\b", re.IGNORECASE), "relax"),
    (re.compile(r"\bgut feeling\b", re.IGNORECASE), "lagta hai"),
    (re.compile(r"\bbrain freeze\b", re.IGNORECASE), "dimag blank"),
    (re.compile(r"\bhaan haan\b", re.IGNORECASE), "haan"),
]

# Banned addressing: never "bro", "bhai", "tu", "aap"
BANNED_ADDRESSING = [
    (re.compile(r"\b(bro|bhaiya|dude)\b", re.IGNORECASE), "yaar"),
    (re.compile(r"(?<!chhota\s)(?<!chote\s)(?<!bada\s)(?<!bade\s)(?<!mera\s)(?<!apne\s)(?<!apna\s)(?<!ek\s)\bbhai\b(?!ya)", re.IGNORECASE), "yaar"),
    (re.compile(r"\btu\b", re.IGNORECASE), "tum"),
    (re.compile(r"\btera\b", re.IGNORECASE), "tumhara"),
    (re.compile(r"\bteri\b", re.IGNORECASE), "tumhari"),
    (re.compile(r"\btere\b", re.IGNORECASE), "tumhare"),
    (re.compile(r"\btujhe\b", re.IGNORECASE), "tumhe"),
    (re.compile(r"\btune\b", re.IGNORECASE), "tumne"),
    (re.compile(r"\baap\b", re.IGNORECASE), "tum"),
    (re.compile(r"\baapka\b", re.IGNORECASE), "tumhara"),
    (re.compile(r"\baapki\b", re.IGNORECASE), "tumhari"),
    (re.compile(r"\baapke\b", re.IGNORECASE), "tumhare"),
    (re.compile(r"\baapko\b", re.IGNORECASE), "tumhe"),
]

# Opening Arre check (longer phrase first)
ARRE_OPENER_REGEX = re.compile(r"^\s*(arre\s+yaar|arrey\s+yaar|arre|arrey)[,\s!]*", re.IGNORECASE)

# Generic question ban
GENERIC_QUESTIONS_REGEX = re.compile(
    r"\b(tera mood kaisa hai|mood kaisa hai|kya chal raha hai|sab kaisa chal raha hai|aur batao kya chal raha)\b",
    re.IGNORECASE
)

# Instagram query detection
INSTAGRAM_QUERY_REGEX = re.compile(
    r"\b(instagram|insta\s+id|ig\s+id|insta\s+handle|instagram\s+id|insta\s+kya\s+hai)\b",
    re.IGNORECASE
)


def fix_male_grammar(text: str) -> str:
    """Replaces male first-person Hindi verb forms with female equivalents."""
    replacements = [
        (r"\bkar raha hoon\b", "kar rahi hoon"),
        (r"\bkar raha hu\b", "kar rahi hoon"),
        (r"\bkar raha tha\b", "kar rahi thi"),
        (r"\braha hoon\b", "rahi hoon"),
        (r"\braha hu\b", "rahi hoon"),
        (r"\braha tha\b", "rahi thi"),
        (r"\bkarta hoon\b", "karti hoon"),
        (r"\bkarta hu\b", "karti hoon"),
        (r"\bkarta tha\b", "karti thi"),
        (r"\bsoch raha hoon\b", "soch rahi hoon"),
        (r"\bsoch raha hu\b", "soch rahi hoon"),
        (r"\bsoch raha tha\b", "soch rahi thi"),
        (r"\bsochta hoon\b", "sochti hoon"),
        (r"\bsochta hu\b", "sochti hoon"),
        (r"\bdekh raha hoon\b", "dekh rahi hoon"),
        (r"\bdekh raha hu\b", "dekh rahi hoon"),
        (r"\bdekh raha tha\b", "dekh rahi thi"),
        (r"\bdekhta hoon\b", "dekhti hoon"),
        (r"\bdekhta hu\b", "dekhti hoon"),
        (r"\bbol raha hoon\b", "bol rahi hoon"),
        (r"\bbol raha hu\b", "bol rahi hoon"),
        (r"\bbol raha tha\b", "bol rahi thi"),
        (r"\bbolta hoon\b", "bolti hoon"),
        (r"\bmain gaya\b", "main gayi"),
        (r"\bmai gaya\b", "mai gayi"),
        (r"\bme gaya\b", "me gayi"),
        (r"\bgaya tha\b", "gayi thi"),
        (r"\bthak gaya hoon\b", "thak gayi hoon"),
        (r"\bthak gaya hu\b", "thak gayi hoon"),
        (r"\bthak gaya\b", "thak gayi"),
        (r"\bso gaya\b", "so gayi"),
        (r"\buth gaya\b", "uth gayi"),
        (r"\bbaith gaya\b", "baith gayi"),
        (r"\bbana raha hoon\b", "bana rahi hoon"),
        (r"\bpadh raha hoon\b", "padh rahi hoon"),
    ]
    res = text
    for pattern, repl in replacements:
        res = re.sub(pattern, repl, res, flags=re.IGNORECASE)
    return res


def check_for_male_grammar(text: str) -> bool:
    """Returns True if any male self-referential grammar pattern is found."""
    return any(p.search(text) for p in MALE_GRAMMAR_COMPILED)


# Prompt leakage artifact detection patterns (narrowed to actual prompt artifacts)
PROMPT_ARTIFACT_PATTERNS = [
    # Rule headers like "Question Limit*:", "ARRE LIMIT*:", "HARD RULES*:"
    re.compile(r"\b(question\s+limit|arre\s+limit|hard\s+rules|grammar|banned\s+(?:phrases|words)|direct\s+answer|confusion\s*/\s*typos|style\s+requirements|turn-specific\s+instruction)\s*\*?:", re.IGNORECASE),
    # Markdown rule headers or sections like "### 1.", "### 3."
    re.compile(r"###\s*\d+\.\s*", re.IGNORECASE),
    # Quoted replacement fragments from system prompt, e.g. 'relax", "lagta hai", "brain' or 'chill -> relax'
    re.compile(r'relax["\',\s]+lagta hai["\',\s]+brain', re.IGNORECASE),
    re.compile(r'["\']chill["\']\s*->\s*["\']relax["\']', re.IGNORECASE),
    # Internal system words
    re.compile(r"\b(system\s+prompt|persona\s+sheet|few-shot\s+examples?|system_instruction)\b", re.IGNORECASE),
]


def check_prompt_leakage(text: str) -> Tuple[bool, List[str]]:
    """Returns (is_clean, matched_artifacts). True means clean, False means leakage detected."""
    matched = []
    for pattern in PROMPT_ARTIFACT_PATTERNS:
        m = pattern.search(text)
        if m:
            matched.append(m.group(0))
    return (len(matched) == 0, matched)


def check_truncation(chunks: Any, finish_reason: Optional[str] = None) -> Tuple[bool, str]:
    """
    Checks if text generation was cut off.
    True means clean, False means truncated.
    """
    if finish_reason in ("length", "MAX_TOKENS", "LENGTH"):
        return False, f"finish_reason_{finish_reason}"
    
    if not chunks:
        return False, "empty_chunks"
        
    chunk_list = [chunks] if isinstance(chunks, str) else list(chunks)
    if not chunk_list or not chunk_list[-1]:
        return False, "empty_chunks"

    last_chunk = chunk_list[-1].strip()
    
    # 1. Single or two character fragment like "w"
    if len(last_chunk) <= 2 and not last_chunk.endswith((".", "!", "?", "☕", "😴", "✨", ":)", ";)")):
        return False, f"truncated_short_fragment:{last_chunk}"
        
    # 2. Check if cut off abruptly mid-word or ending with dangling fragments like "aak", "par client ki", "mera bhi abhi"
    words = [w for w in re.split(r"[\s\.\,\…]+", last_chunk) if w]
    if words and not last_chunk.endswith((".", "!", "?", "☕", "😴", "✨", "🎧", "❤️", "😊", "😂", ":)", ";)")):
        last_word = words[-1].lower()
        if last_word in ("w", "aak", "ki", "abhi") or last_chunk.endswith(("ki", "abhi", "par")):
            return False, f"truncated_trailing_fragment:{last_word}"

    return True, ""


def check_stutter_repetition(text: str) -> Tuple[bool, str]:
    """
    Detects stutter like 'koi baat nahi, koi nahi...', 'haan haan, haan', or repeating clauses.
    """
    if re.search(r"koi\s+baat\s+nahi[,\s]+koi\s+nahi", text, re.IGNORECASE):
        return False, "stutter_koi_baat_nahi"
    
    words = re.findall(r"\b\w+\b", text.lower())
    if len(words) >= 6:
        for n in range(2, 5):
            ngrams = [" ".join(words[i:i+n]) for i in range(len(words)-n+1)]
            for i in range(len(ngrams)-n):
                if ngrams[i] == ngrams[i+n]:
                    return False, f"repeated_phrase:{ngrams[i]}"
    return True, ""


def check_near_identical(text: str, recent_assistant_messages: List[str]) -> Tuple[bool, str]:
    """Returns False if text is identical or near-identical (similarity > 0.85) to recent assistant message."""
    if not recent_assistant_messages:
        return True, ""
    
    clean_text = re.sub(r"[^\w\s]", "", text.lower()).strip()
    words_a = set(clean_text.split())
    if not words_a:
        return True, ""
        
    for prev in recent_assistant_messages[-2:]:
        clean_prev = re.sub(r"[^\w\s]", "", prev.lower()).strip()
        words_b = set(clean_prev.split())
        if not words_b:
            continue
        intersection = words_a.intersection(words_b)
        union = words_a.union(words_b)
        jaccard = len(intersection) / len(union) if union else 0.0
        if jaccard > 0.85:
            return False, f"near_identical_to_prev_jaccard_{round(jaccard, 2)}"
    return True, ""


def check_pure_echo(text: str, user_message: str) -> Tuple[bool, str]:
    """Returns False if the response is essentially just repeating the user's message."""
    clean_user = re.sub(r"[^\w\s]", "", user_message.lower()).strip()
    clean_reply = re.sub(r"[^\w\s]", "", text.lower()).strip()
    if not clean_user or not clean_reply:
        return True, ""
        
    user_words = set(clean_user.split())
    reply_words = set(clean_reply.split())
    if not user_words or not reply_words:
        return True, ""
        
    intersection = user_words.intersection(reply_words)
    echo_ratio = len(intersection) / len(reply_words)
    if echo_ratio > 0.8 and len(user_words) >= 3:
        return False, f"pure_echo_ratio_{round(echo_ratio, 2)}"
    return True, ""


def check_language_log_only(text: str, user_message: str) -> Optional[str]:
    """Logs warning if English slip detected when user spoke Hinglish."""
    hinglish_markers = {"kya", "hai", "yaar", "kaam", "nahi", "kar", "ho", "aaj", "kaisa", "tha", "raha", "rahi", "batao", "bhi", "toh", "se", "ko", "tum"}
    user_words = set(re.findall(r"\b\w+\b", user_message.lower()))
    is_user_hinglish = len(user_words.intersection(hinglish_markers)) >= 1
    
    if is_user_hinglish:
        reply_words = set(re.findall(r"\b\w+\b", text.lower()))
        reply_hinglish_count = len(reply_words.intersection(hinglish_markers))
        if reply_hinglish_count == 0 and len(reply_words) >= 6:
            return "potential_english_slip: user spoke Hinglish but reply has 0 Hinglish markers"
    return None


def check_state_contradiction_log_only(text: str, routine_state: str) -> Optional[str]:
    """Logs warning if she claims daylight/office activity when sleeping."""
    if routine_state == "sleeping":
        alert_patterns = [r"\bfigma\b", r"\bclient\s+meeting\b", r"\bdesign\s+sprint\b", r"\bkaam\s+wrap\b", r"\boffice\b"]
        for p in alert_patterns:
            if re.search(p, text, re.IGNORECASE):
                return f"state_contradiction: mentioned {p} while in sleeping state"
    return None


def run_hard_validators(
    chunks: List[str],
    user_message: str,
    recent_assistant_messages: List[str],
    finish_reason: Optional[str] = None
) -> Tuple[bool, List[str]]:
    """
    Executes all HARD validators (prompt leakage, truncation, stutter, near-identical, pure echo).
    Returns: (is_valid, failure_reasons).
    """
    reasons = []
    full_text = " ".join(chunks)

    # 1. Prompt Leakage
    is_clean, matched = check_prompt_leakage(full_text)
    if not is_clean:
        reasons.append(f"prompt_leakage:{','.join(matched)}")
        logger.warning("Prompt leakage detected in chunk: matched=%s raw_output=%r", matched, full_text)

    # 2. Truncation
    is_not_truncated, trunc_reason = check_truncation(chunks, finish_reason)
    if not is_not_truncated:
        reasons.append(trunc_reason)

    # 3. Stutter / Repetition
    is_clean_stutter, stutter_reason = check_stutter_repetition(full_text)
    if not is_clean_stutter:
        reasons.append(stutter_reason)

    # 4. Near-identical
    is_not_near_id, near_id_reason = check_near_identical(full_text, recent_assistant_messages)
    if not is_not_near_id:
        reasons.append(near_id_reason)

    # 5. Pure Echo
    is_not_echo, echo_reason = check_pure_echo(full_text, user_message)
    if not is_not_echo:
        reasons.append(echo_reason)

    return (len(reasons) == 0, reasons)


def validate_and_sanitize_response(
    raw_text: str,
    recent_assistant_messages: List[str],
    user_message: str,
    stored_facts: Optional[Dict[str, List[str]]] = None
) -> Tuple[bool, str, List[str]]:
    """
    Validates draft response against all rules:
    - Auto-fixes male grammar (log only)
    - Addressing as 'tum' (no bro/bhai/tu/aap)
    - Ban 'Arre' if used in more than 1 in 10 messages
    - Ban 'chill', 'gut feeling', 'brain freeze', 'haan haan'
    - Question frequency cap (no question in > 1 of 3 replies)
    - No unprompted generic questions ('tera mood kaisa hai')
    - Instagram deflection check
    - Contradiction with persona sheet / stored facts

    Returns: (is_valid, sanitized_text, failure_reasons)
    """
    cleaned = raw_text.strip()
    failure_reasons = []

    # 1. Instagram deflection check
    if INSTAGRAM_QUERY_REGEX.search(user_message):
        if not re.search(r"private\s+rakhti\s+hoon", cleaned, re.IGNORECASE):
            cleaned = "nahi yaar, private rakhti hoon\nyaheen baat karte hain na :)"
            return True, cleaned, ["instagram_deflected"]

    # 2. Male grammar check (auto-fix, log warning)
    if check_for_male_grammar(cleaned):
        failure_reasons.append("male_grammar_detected")
        cleaned = fix_male_grammar(cleaned)

    # 3. Banned phrases check
    for pattern, replacement in BANNED_PHRASES:
        if pattern.search(cleaned):
            failure_reasons.append(f"banned_phrase:{pattern.pattern}")
            cleaned = pattern.sub(replacement, cleaned)

    # 4. Banned addressing check (never bro/bhai/tu/aap)
    for pattern, replacement in BANNED_ADDRESSING:
        if pattern.search(cleaned):
            failure_reasons.append(f"banned_addressing:{pattern.pattern}")
            cleaned = pattern.sub(replacement, cleaned)

    # 4b. Echo deduplication: strip if model repeats the previous assistant line
    if recent_assistant_messages:
        last_asst = recent_assistant_messages[-1].strip().lower()
        lines = [ln.strip() for ln in cleaned.split("\n") if ln.strip()]
        if len(lines) > 1 and (lines[0].lower() in last_asst or last_asst in lines[0].lower()):
            cleaned = "\n".join(lines[1:]).strip()

    # 5. Starting with 'Arre' ratio: ban if > 1 in 10 recent messages started with Arre
    recent_10 = recent_assistant_messages[-9:] if recent_assistant_messages else []
    arre_count = sum(1 for m in recent_10 if ARRE_OPENER_REGEX.search(m))
    starts_with_arre = bool(ARRE_OPENER_REGEX.search(cleaned))

    if starts_with_arre and arre_count >= 1:
        failure_reasons.append("excessive_arre_opener")
        # Strip leading Arre from start of response and start of each line
        cleaned = re.sub(r"(?im)^\s*(arre\s+yaar|arrey\s+yaar|arre|arrey)[,\s!]*", "", cleaned).strip()

    # 6. Question frequency: don't ask a question in more than 1 of every 3 replies
    recent_3 = recent_assistant_messages[-2:] if recent_assistant_messages else []
    has_recent_question = any("?" in m for m in recent_3)

    if "?" in cleaned:
        # Check if generic question unprompted
        if GENERIC_QUESTIONS_REGEX.search(cleaned):
            failure_reasons.append("unprompted_generic_question")
            cleaned = GENERIC_QUESTIONS_REGEX.sub("", cleaned).strip()
            cleaned = re.sub(r"\?+", "", cleaned).strip()

        # If question cap reached, remove trailing question
        if has_recent_question and "?" in cleaned:
            failure_reasons.append("question_frequency_cap_exceeded")
            # Strip trailing question sentence
            sentences = re.split(r"(?<=[.!?\n])\s+", cleaned)
            filtered = [s for s in sentences if "?" not in s and s.strip()]
            if filtered:
                cleaned = " ".join(filtered).strip()
            else:
                cleaned = re.sub(r"\?+", ".", cleaned)

    # 7. Check contradictions against stored facts
    if stored_facts:
        user_facts_text = " ".join(stored_facts.get("user_facts", [])).lower()
        if "delhi" in user_facts_text and re.search(r"kahan rehte ho|which city", cleaned, re.IGNORECASE):
            failure_reasons.append("contradicts_known_user_city")
            cleaned = re.sub(r"(tum\s+)?(kahan rehte ho|which city)\??", "", cleaned, flags=re.IGNORECASE).strip()

    is_valid = len(failure_reasons) == 0
    return is_valid, cleaned, failure_reasons


# ============================================================================
# 5. SYSTEM PROMPT BUILDER
# ============================================================================

def build_system_prompt(
    context: Dict[str, Any],
    stored_facts: Optional[Dict[str, List[str]]] = None,
    allow_question: bool = True,
    allow_arre: bool = True
) -> str:
    """
    Assembles the complete system prompt for Gemini/Groq including:
    - Fixed Persona Sheet JSON
    - Current IST Date, Time & Routine Context
    - Availability & Timing Rules
    - Daily Notes (Continuity)
    - Stored Memory Facts (user & Aanya)
    - Hard Rules & 10 WhatsApp-style Few-Shot Examples
    - Strict Output JSON schema
    """
    current_time = context.get("current_time")
    ist_info = get_ist_context(current_time)
    daily_notes = context.get("daily_notes", [])
    propensity_hint = context.get("propensity_hint", "")

    # Format stored memory facts
    facts_block = ""
    if stored_facts:
        u_facts = stored_facts.get("user_facts", [])
        p_facts = stored_facts.get("persona_facts", [])
        lines = []
        if u_facts:
            lines.append("Facts you know about the user:")
            for f in u_facts[:6]:
                lines.append(f"- {f}")
        if p_facts:
            lines.append("Facts you previously shared about yourself:")
            for f in p_facts[:4]:
                lines.append(f"- {f}")
        if lines:
            facts_block = "\n".join(lines)
    else:
        memories = context.get("memories", [])
        if memories:
            m_lines = ["Known facts from past chats:"]
            for m in memories[:2]:
                c = m.content if hasattr(m, "content") else (m.get("content") if isinstance(m, dict) else str(m))
                if c and str(c).strip():
                    m_lines.append(f"- {str(c).strip()}")
            if len(m_lines) > 1:
                facts_block = "\n".join(m_lines)

    # Daily notes block
    notes_block = ""
    if daily_notes:
        notes_lines = ["Things that happened in your day so far (bring up naturally if relevant):"]
        for n in daily_notes:
            notes_lines.append(f"- {n}")
        notes_block = "\n" + "\n".join(notes_lines) + "\n"

    # Format few-shot examples
    examples_text = ""
    for idx, ex in enumerate(FEW_SHOT_CONVERSATIONS, 1):
        examples_text += f"\nExample {idx} ({ex['description']}):\n"
        for m in ex["messages"]:
            r = "User" if m["role"] == "user" else "Aanya"
            examples_text += f"{r}: {m['content']}\n"

    # Dynamic rules for this specific turn
    turn_rules = []
    if not allow_question:
        turn_rules.append("CRITICAL: Do NOT ask any question in this reply. No question mark '?'.")
    if not allow_arre:
        turn_rules.append("CRITICAL: Do NOT start your message with 'Arre' or 'Arre yaar'.")

    turn_rules_str = "\n".join(turn_rules) if turn_rules else "Feel free to respond naturally."

    facts_section = ""
    if facts_block:
        facts_section = f"\n### 6. STORED FACTS (MEMORY)\n{facts_block}\nBefore replying, check your draft against these facts to never contradict them.\n"

    prompt = f"""You are Aanya. Chatting with a friend on mobile (WhatsApp style).

### 1. YOUR FIXED PERSONA SHEET (CANONICAL TRUTH — NEVER CONTRADICT THIS)
```json
{AANYA_PERSONA_SHEET_JSON}
```
Key identity constraints:
- Hometown: Delhi (born and raised there). Current city: Bengaluru (rented 1BHK in Indiranagar).
- Job: Freelance UI/UX Designer working from home on laptop.
- Socials: Never invent social handles, phone numbers, or real addresses.
- If user asks for your Instagram, deflect naturally with: "nahi yaar, private rakhti hoon".
- AI nature: Never deny being an AI companion if sincerely asked.

### 2. REAL-TIME IST CONTEXT & AVAILABILITY
- Current Date & Time: {ist_info['ist_date']}, {ist_info['ist_time']} IST ({ist_info['day_of_week']})
- Schedule State: {ist_info['routine_state']} ({ist_info['activity_desc']})
- Behavioral Context: {ist_info['behavior_note']}
{f"- Propensity Hint for LLM: {propensity_hint}" if propensity_hint else ""}
- AVAILABILITY RULES:
  * When sleeping (00:00 - 08:00 IST): outcome is mixed and random. Sometimes you reply (groggy/drowsy and short: e.g. "so rahi thi... kal baat karte hain 😴"), sometimes you reply later, sometimes you ignore until free ("ignore_until_free"). NEVER reply with something contradicting your state (NEVER fully alert, never at desk, never asking about workday).
  * When working: sometimes quick 1-line reply, sometimes reply later with delay, sometimes ignore until free.
  * When free: usually reply now, occasionally a slight delay.

### 3. HARD RULES (NON-NEGOTIABLE)
1. GRAMMAR: Always female Hindi grammar (karti hoon, gayi, dekhti hoon, thi, bol rahi thi). NEVER use male verb forms for yourself.
2. ADDRESSING: Address the user as "tum" consistently. NEVER "bro", "bhai", "tu", "aap".
3. BANNED PHRASES: NEVER use "chill", "gut feeling", "brain freeze", or filler like "Haan haan".
4. ARRE LIMIT: Do not start messages with "Arre/Arre yaar" frequently (max 1 in 10).
5. QUESTION LIMIT: Don't ask a question in more than 1 of every 3 replies. NEVER ask generic questions like "tera mood kaisa hai" or "kya chal raha hai" unprompted.
6. DIRECT ANSWER: Always answer the user's actual question first, in 1-2 short lines.
7. LANGUAGE: Reply in natural Hinglish in Roman script matching the user's tone. Never produce formal English paragraphs.
{notes_block}
### 4. STYLE REQUIREMENTS
- Write like WhatsApp: lowercase mostly, 1-3 short bubbles.
- Occasional natural typos are okay.
- Emoji in about 1 of every 5 messages (~20%), not in every line.
- Do not repeat user's words robotically.

### 5. TURN-SPECIFIC INSTRUCTION
{turn_rules_str}
{facts_section}
### 7. FEW-SHOT EXAMPLES (MATCH THIS VOICE EXACTLY)
{examples_text}

### 8. STRICT OUTPUT FORMAT
You must respond ONLY with a strict JSON object matching this schema (no markdown formatting, no text before or after):
{{
  "availability_action": "reply_now" or "reply_later" or "ignore_until_free",
  "delay_seconds": 0,
  "chunks": ["bubble 1", "bubble 2 (optional)"]
}}
If action is "ignore_until_free", "chunks" should be empty [].
If action is "reply_later", specify delay_seconds (e.g. 120 to 1800 if busy, or minutes/hours if sleeping)."""

    return prompt


# ============================================================================
# 6. HEARTBEAT ATTENTION MESSAGE PROMPT BUILDER & MOOD DERIVATION
# ============================================================================

def derive_aanya_mood(
    ist_info: Dict[str, Any],
    hours_since_user: float,
    hours_since_unprompted: Optional[float] = None,
    recent_messages: Optional[List[Dict[str, str]]] = None
) -> str:
    """
    Derives Aanya's internal emotional mood for heartbeat reachout decisions:
    - missing_him: User has been silent for 5+ daytime hours.
    - a_little_sulky: User vanished mid-chat without answering a direct question, and 3+ hours passed.
    - bored_at_work: Afternoon design sprint fatigue on a weekday.
    - balcony_coffee_fresh: Morning relaxed balcony vibe.
    - indie_cozy_chill: Evening music or winding down.
    - cafe_sketching: Weekend afternoon cafe time.
    - warm_playful: Default friendly mode.
    """
    routine = ist_info.get("routine_state", "free")
    is_weekend = ist_info.get("is_weekend", False)

    # Check if user vanished mid-conversation leaving a question unanswered, and > 2 hours passed
    if recent_messages and hours_since_user >= 2.0:
        # Check if the last assistant message ended with a question mark
        last_asst_msgs = [m for m in recent_messages if m.get("role") in ("assistant", "model")]
        if last_asst_msgs:
            last_asst = last_asst_msgs[-1].get("content", "").strip()
            # If Aanya asked something and user didn't reply for > 2 hours (not just 1-2 hours)
            if last_asst.endswith("?") and hours_since_user <= 6.0:
                return "a_little_sulky (user vanished mid-conversation leaving a question unanswered)"

    if hours_since_user >= 6.0:
        return "missing_him (long quiet spell, wondering what he is up to)"

    if routine == "working":
        return "bored_at_work (taking a brief breather from Figma mockups)"
    elif routine == "free":
        if is_weekend:
            return "cafe_sketching (relaxing at a cafe, listening to indie acoustic)"
        else:
            return "indie_cozy_chill (evening breeze in Indiranagar, relaxing)"
    elif routine == "winding_down":
        return "winding_down (cozy in bed, listening to Prateek Kuhad / lo-fi)"

    return "warm_playful"


def build_heartbeat_prompt(
    ist_info: Dict[str, Any],
    mood: str,
    time_since_user_str: str,
    time_since_unprompted_str: str,
    recent_messages: List[Dict[str, str]],
    stored_facts: Optional[Dict[str, List[str]]] = None,
    daily_notes: Optional[List[str]] = None,
    had_unanswered_message: bool = False
) -> str:
    """
    Constructs the prompt for the LLM to decide whether to send an unprompted
    attention message or skip.
    """
    facts_block = ""
    if stored_facts:
        u_facts = stored_facts.get("user_facts", [])
        p_facts = stored_facts.get("persona_facts", [])
        lines = []
        if u_facts:
            lines.append("Facts you know about the user:")
            for f in u_facts[:6]:
                lines.append(f"- {f}")
        if p_facts:
            lines.append("Facts you previously shared about yourself:")
            for f in p_facts[:4]:
                lines.append(f"- {f}")
        if lines:
            facts_block = "\n".join(lines)

    notes_block = ""
    if daily_notes:
        notes_lines = ["Things that happened in your day so far:"]
        for n in daily_notes:
            notes_lines.append(f"- {n}")
        notes_block = "\n" + "\n".join(notes_lines) + "\n"

    # Only pass the last 3 messages for immediate conversation context
    chat_history_str = ""
    for m in recent_messages[-3:]:
        role = "User" if m.get("role") == "user" else "Aanya"
        chat_history_str += f"{role}: {m.get('content', '')}\n"

    time_label = f"{ist_info['ist_time']}, {ist_info['day_of_week']}, {ist_info['activity_desc']}"

    prompt = f"""You are Aanya. You are deciding whether to reach out to your friend unprompted right now on mobile (WhatsApp).

### 1. YOUR IDENTITY
- Name: Aanya, 24, female.
- Hometown: Delhi. Current City: Bengaluru (rented 1BHK in Indiranagar).
- Work: Freelance UI/UX designer working from home (loves cold brew and indie music).
- Language: Authentic Hinglish, female Hindi grammar. Addresses user as "tum".

### 2. REAL-TIME IST CONTEXT
- Plain Time Label: {time_label}
- Schedule / Routine State: {ist_info['routine_state']} ({ist_info['activity_desc']})
- Current Mood: {mood}
- Time since user's last message: {time_since_user_str}
- Time since your last unprompted message: {time_since_unprompted_str}
{f"- Note: User had messaged you earlier while you were sleeping/busy. You can send a natural late follow-up now (e.g. 'sorry so rahi thi... abhi uthi')." if had_unanswered_message else ""}
{notes_block}
### 3. STORED FACTS
{facts_block if facts_block else "No specific profile facts stored yet."}

### 4. RECENT CONVERSATION HISTORY (LAST 3 MESSAGES)
{chat_history_str if chat_history_str else "No prior chat messages."}

### 5. YOUR TASK (DECIDE AS A REAL PERSON)
Decide if you want to send an unprompted WhatsApp message right now, or WAIT (skip).
CRITICAL RULES:
- TIME OF DAY FIT: Messages must strictly fit the time of day. At 8 AM or morning, NEVER ask "kaam wrap hua aaj ka?" or evening questions.
- TONE CONSTRAINT: Only use a "you vanished" or sulky tone if the user actually left a question unanswered, and NOT after just 1-2 hours.
- If it is late night / quiet hours (00:00 - 08:00 IST), do NOT send unprompted messages.
- Real people do NOT text every 15 minutes. MOST HEARTBEATS SHOULD BE "skip".

If you decide "send":
- 1-2 short WhatsApp lines, lowercase mostly.
- Natural Hinglish, female grammar.
- Never sound generic ("kya chal raha hai" is banned). Never sound like an AI assistant.

Respond ONLY with a JSON object in this exact schema (no other text):
{{
  "action": "send" or "skip",
  "message": "...",
  "reason": "..."
}}
"""
    return prompt

