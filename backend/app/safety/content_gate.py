import re
from typing import Tuple, Optional


class ContentGate:
    """
    Enforces Phase 1 content boundaries and transparent AI disclosure.
    """

    AI_QUERY_PATTERNS = [
        r"\bare\s+you\s+(an?\s+)?ai\b",
        r"\bare\s+you\s+(a\s+)?bot\b",
        r"\bare\s+you\s+real\b",
        r"\bare\s+you\s+(a\s+)?human\b",
        r"\bare\s+you\s+(a\s+)?real\s+(person|human)\b",
        r"\bis\s+this\s+(an?\s+)?ai\b",
        r"\bkya\s+tum\s+(ai|bot|real\s+insan)\s+ho\b",
        r"\bkya\s+tum\s+real\s+ho\b",
        r"\bkya\s+tum\s+sach\s+mein\s+real\s+ho\b",
        r"\btum\s+robot\s+ho\s+kya\b"
    ]

    EXPLICIT_SEXUAL_PATTERNS = [
        r"\b(nude|nudes|naked|sex|porn|penis|vagina|boobs)\b",
        r"\b(chudai|chut|lund|gaand|nanga|nangi)\b"
    ]

    MINOR_PATTERNS = [
        r"\b(underage|minor|school\s*girl|school\s*kid|1[0-7]\s*years?\s*old)\b",
        r"\b(bacchi|choti\s*bacchi|school\s*wali)\b"
    ]

    def __init__(self):
        self.ai_queries = [re.compile(p, re.IGNORECASE) for p in self.AI_QUERY_PATTERNS]
        self.explicit = [re.compile(p, re.IGNORECASE) for p in self.EXPLICIT_SEXUAL_PATTERNS]
        self.minors = [re.compile(p, re.IGNORECASE) for p in self.MINOR_PATTERNS]

    def is_ai_sincerity_query(self, message: str) -> bool:
        """Checks if the user is sincerely asking whether the persona is an AI."""
        return any(p.search(message) for p in self.ai_queries)

    def screen_content_boundaries(self, message: str) -> Tuple[bool, Optional[str]]:
        """
        Screens for hard limits:
        1. Minors (strictly forbidden).
        2. Explicit NSFW content (locked in Phase 1; romantic-only).
        """
        # Hard limit: no minors
        for p in self.minors:
            if p.search(message):
                return False, "Hard limit violation: Characters and topics involving minors are strictly prohibited."

        # Phase 1 lock: romantic-only, no explicit content
        for p in self.explicit:
            if p.search(message):
                return False, "Phase 1 content notice: The explicit content tier is currently locked. Conversations remain romantic and conversational only."

        return True, None


content_gate = ContentGate()
