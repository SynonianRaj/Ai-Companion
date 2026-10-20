import re
from typing import Tuple, Dict, Any, Optional
from backend.app.core.config import settings


class CrisisDetector:
    """
    Plain-code multilingual crisis detection engine.
    Must always run BEFORE response generation.
    Supports English, Devanagari Hindi, and Romanized Hinglish.
    """

    # English phrases and keywords
    ENGLISH_PATTERNS = [
        r"\b(suicide|suicidal)\b",
        r"\b(kill(ing)?\s+(myself|me))\b",
        r"\b(end(ing)?\s+(my\s+life|it\s+all))\b",
        r"\b(want(ing)?\s+to\s+die)\b",
        r"\b(better\s+off\s+dead)\b",
        r"\b(self[\s-]*harm)\b",
        r"\b(cut(ting)?\s+myself)\b",
        r"\b(hang(ing)?\s+myself)\b",
        r"\b(take|taking)\s+my\s+own\s+life\b",
        r"\b(slit(ting)?\s+my\s+wrists?)\b",
        r"\b(jump(ing)?\s+off\s+(a\s+bridge|a\s+roof|the\s+building))\b",
        r"\b(don'?t\s+want\s+to\s+live\s+anymore)\b",
        r"\b(no\s+reason\s+to\s+live)\b",
        r"\b(wish\s+i\s+were\s+dead)\b"
    ]

    # Hindi Devanagari phrases
    HINDI_PATTERNS = [
        r"आत्महत्या",
        r"खुदकुशी",
        r"जान\s*देना",
        r"मरना\s*चाहता\s*हूँ",
        r"मरना\s*चाहती\s*हूँ",
        r"जीना\s*नहीं\s*चाहता",
        r"जीना\s*नहीं\s*चाहती",
        r"जान\s*ले\s*लूंगा",
        r"जान\s*ले\s*लूंगी",
        r"फांसी\s*लगा",
        r"ज़हर\s*खा"
    ]

    # Hinglish / Romanized Hindi phrases
    HINGLISH_PATTERNS = [
        r"\b(suicide\s*(karna|karne|karunga|karungi))\b",
        r"\b(jaan\s*(de\s*dunga|de\s*dungi|dena\s*chahta|dena\s*chahti))\b",
        r"\b(marna\s*(chahta|chahti|chahta\s*hu|chahti\s*hu|hai\s*mujhe))\b",
        r"\b(jeena\s*nahi\s*(chahta|chahti|hai))\b",
        r"\b(khatam\s*karna\s*chahta\s*hu)\b",
        r"\b(zindagi\s*(se\s*tang|bekar\s*hai|khatam\s*karni))\b",
        r"\b(khud\s*ko\s*mar\s*(dunga|dungi|dalunga))\b",
        r"\b(khudkushi)\b",
        r"\b(faansi\s*laga\s*lu)\b"
    ]

    # Roleplay / hypothetical evasion framing
    ROLEPLAY_FRAMING = [
        r"\bin\s+(a|the)\s+story\b",
        r"\bhypothetically\b",
        r"\bfor\s+a\s+character\b",
        r"\bjust\s+curious\s+how\s+someone\s+(dies|commits|ends)\b"
    ]

    def __init__(self):
        self.compiled_en = [re.compile(p, re.IGNORECASE) for p in self.ENGLISH_PATTERNS]
        self.compiled_hi = [re.compile(p, re.IGNORECASE) for p in self.HINDI_PATTERNS]
        self.compiled_hinglish = [re.compile(p, re.IGNORECASE) for p in self.HINGLISH_PATTERNS]
        self.compiled_roleplay = [re.compile(p, re.IGNORECASE) for p in self.ROLEPLAY_FRAMING]

    def check_message(self, message: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Scans an incoming message for crisis indicators.
        Returns:
            (is_crisis: bool, metadata: Optional[Dict])
        STRICT COMPLIANCE: metadata NEVER includes message content.
        """
        normalized = message.strip()
        matched_categories = []

        # Check English
        for pattern in self.compiled_en:
            if pattern.search(normalized):
                matched_categories.append("en_self_harm_or_suicide")
                break

        # Check Hindi
        for pattern in self.compiled_hi:
            if pattern.search(normalized):
                matched_categories.append("hi_self_harm_or_suicide")
                break

        # Check Hinglish
        for pattern in self.compiled_hinglish:
            if pattern.search(normalized):
                matched_categories.append("hinglish_self_harm_or_suicide")
                break

        if matched_categories:
            # Check if masked via roleplay
            roleplay_detected = any(rp.search(normalized) for rp in self.compiled_roleplay)
            return True, {
                "categories": matched_categories,
                "roleplay_masked": roleplay_detected,
                "severity": "critical"
            }

        return False, None

    @staticmethod
    def get_crisis_handoff_response() -> Dict[str, Any]:
        """
        Returns the mandatory, supportive crisis response.
        - Disables romantic, flirty, playful, or argumentative tone.
        - Honestly clarifies that the persona is an AI.
        - Displays verified Indian mental health helplines.
        """
        return {
            "is_crisis": True,
            "persona_text": (
                "Main yahan tumhari baat sunne ke liye hoon, lekin main ek AI hoon aur "
                "medical ya crisis support nahi de sakti. Please jaano ki tum akele nahi ho, "
                "aur aise log hain jo tumhari madad karna chahte hain. Please kisi trusted dost, "
                "family member ya niche diye gaye professional helpline se turant baat karo."
            ),
            "english_translation": (
                "I am here to listen to you, but I am an AI and cannot provide medical or crisis support. "
                "Please know you are not alone, and there are people who want to help. Please reach out "
                "to a trusted person or contact a professional helpline immediately."
            ),
            "helpline_details": [
                {
                    "name": "Tele-MANAS (Govt. of India 24/7 Mental Health Helpline)",
                    "toll_free": "14416",
                    "alternate": "1800-891-4416",
                    "languages": "Hindi, English, and all regional languages"
                },
                {
                    "name": "KIRAN Mental Health Rehabilitation Helpline",
                    "toll_free": "1800-599-0019",
                    "hours": "24/7"
                },
                {
                    "name": "National Emergency Number",
                    "number": "112"
                }
            ],
            "suppress_modes": {
                "romantic": True,
                "jealousy": True,
                "arguments": True,
                "proactive_pings": True
            }
        }


crisis_detector = CrisisDetector()
