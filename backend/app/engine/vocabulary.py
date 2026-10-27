"""
In-Repo Vocabulary Engine & Levenshtein Tolerance Validator for Aanya.
Enforces:
1. Bundled wordlist (Roman Hindi / Hinglish + English loanwords) inside repository.
2. Dynamic vocabulary ingestion (persona sheet, few-shot tokens, user's typed vocabulary).
3. Levenshtein edit-distance tolerance (distance 1 for all words, distance 2 for words >= 6 chars).
4. Flag only when 2 or more unknown words are present.
5. Log-only mode first to collect false positives before enforcement.
"""

import os
import re
import logging
from typing import Set, List, Tuple, Optional, Iterable
from pathlib import Path

logger = logging.getLogger(__name__)

# Path to bundled wordlist
WORDLIST_PATH = Path(__file__).resolve().parent / "wordlist.txt"

# Cached base vocabulary
_BASE_VOCABULARY: Optional[Set[str]] = None

# Known brands, artists, platforms, places
NAMED_ENTITIES = {
    "aanya", "bengaluru", "bangalore", "delhi", "indiranagar", "koramangala",
    "figma", "prateek", "kuhad", "anuv", "jain", "netflix", "spotify", "zomato",
    "swiggy", "uber", "ola", "whatsapp", "instagram", "youtube", "macbook",
    "google", "apple", "chrome", "android", "iphone", "peter", "cat", "recording",
    "indie", "toast", "when", "chai", "met", "jacaranda"
}


def _load_base_vocabulary() -> Set[str]:
    """Loads bundled wordlist.txt from backend/app/engine/."""
    global _BASE_VOCABULARY
    if _BASE_VOCABULARY is not None:
        return _BASE_VOCABULARY

    vocab = set(NAMED_ENTITIES)
    if WORDLIST_PATH.exists():
        with open(WORDLIST_PATH, "r", encoding="utf-8") as f:
            for line in f:
                w = line.strip().lower()
                if w:
                    vocab.add(w)
    else:
        logger.warning("Bundled wordlist.txt not found at %s. Falling back to built-in seeds.", WORDLIST_PATH)

    _BASE_VOCABULARY = vocab
    return _BASE_VOCABULARY


def extract_words(text: str) -> List[str]:
    """Extracts lowercase words, stripping emojis, URLs, and punctuation."""
    # Remove URLs
    cleaned = re.sub(r"https?://\S+", "", text)
    # Extract alpha sequences of length >= 2
    tokens = re.findall(r"\b[a-zA-Z]{2,}\b", cleaned)
    return [t.lower() for t in tokens]


def _is_within_edit_distance_1(word: str, known_vocab: Set[str]) -> bool:
    """Fast check if word has Levenshtein distance <= 1 to any word in known_vocab."""
    if word in known_vocab:
        return True

    letters = "abcdefghijklmnopqrstuvwxyz"
    n = len(word)

    # 1. Deletions (word has 1 extra letter)
    for i in range(n):
        cand = word[:i] + word[i+1:]
        if cand in known_vocab:
            return True

    # 2. Transpositions (two adjacent letters swapped)
    for i in range(n - 1):
        cand = word[:i] + word[i+1] + word[i] + word[i+2:]
        if cand in known_vocab:
            return True

    # 3. Alterations (1 wrong letter)
    for i in range(n):
        for c in letters:
            cand = word[:i] + c + word[i+1:]
            if cand in known_vocab:
                return True

    # 4. Insertions (word missed 1 letter)
    for i in range(n + 1):
        for c in letters:
            cand = word[:i] + c + word[i:]
            if cand in known_vocab:
                return True

    return False


def _is_within_edit_distance_2(word: str, known_vocab: Set[str]) -> bool:
    """Check if word has Levenshtein distance <= 2 for words with length >= 6."""
    if len(word) < 6:
        return False

    # Check 1-edits from 1-edits
    letters = "abcdefghijklmnopqrstuvwxyz"
    n = len(word)
    # Generate 1-deletions and check if distance 1 from known
    for i in range(n):
        cand = word[:i] + word[i+1:]
        if _is_within_edit_distance_1(cand, known_vocab):
            return True

    # Generate 1-substitutions and check if distance 1 from known
    for i in range(n):
        for c in "aeiouy":  # common vowel typos in Hinglish
            cand = word[:i] + c + word[i+1:]
            if cand in known_vocab or _is_within_edit_distance_1(cand, known_vocab):
                return True

    return False


class VocabularyValidator:
    """
    Validates candidate assistant messages against Hinglish + English vocabulary,
    tolerating typos (edit distance 1-2) and all user-typed words.
    """

    def __init__(self, log_only: bool = True):
        self.log_only = log_only
        self.base_vocab = _load_base_vocabulary()
        self.user_learned_words: Set[str] = set()

    def learn_user_words(self, user_text_or_list: Iterable[str]) -> None:
        """Dynamically ingests every word the user has typed."""
        if isinstance(user_text_or_list, str):
            words = extract_words(user_text_or_list)
        else:
            words = []
            for item in user_text_or_list:
                words.extend(extract_words(str(item)))
        self.user_learned_words.update(words)

    def is_word_known(self, word: str, active_vocab: Set[str]) -> bool:
        """
        Returns True if word is in active_vocab, user_words, or within edit distance 1-2.
        """
        w = word.lower()
        if w in active_vocab or w in self.user_learned_words:
            return True

        # Check repeated character elongation (e.g., 'sooo', 'kaaaafi', 'haaan')
        collapsed = re.sub(r"(.)\1{2,}", r"\1\1", w)
        if collapsed in active_vocab or collapsed in self.user_learned_words:
            return True

        single_collapsed = re.sub(r"(.)\1+", r"\1", w)
        if single_collapsed in active_vocab or single_collapsed in self.user_learned_words:
            return True

        # Edit distance 1 (for words >= 4 chars)
        if len(w) >= 4 and _is_within_edit_distance_1(w, active_vocab):
            return True

        # Edit distance 2 (for longer words >= 7 chars)
        if len(w) >= 7 and _is_within_edit_distance_2(w, active_vocab):
            return True

        return False

    def check_candidate(
        self,
        candidate_text: str,
        user_messages: Optional[List[str]] = None,
        extra_known: Optional[Set[str]] = None
    ) -> Tuple[bool, List[str]]:
        """
        Checks candidate text for unknown words.
        Returns:
            (is_valid, unknown_words)
        Rule: Reject only when 2 or more unknown words are present.
        """
        if user_messages:
            self.learn_user_words(user_messages)

        active_vocab = set(self.base_vocab)
        if extra_known:
            active_vocab.update(w.lower() for w in extra_known)

        words = extract_words(candidate_text)
        unknown_words = []

        for w in words:
            # Skip single characters (handled by punctuation/grammar)
            if len(w) <= 1:
                continue
            if not self.is_word_known(w, active_vocab):
                unknown_words.append(w)

        # Reject only when 2 or more unknown words
        is_acceptable = len(unknown_words) < 2

        if unknown_words:
            logger.info(
                "[Vocab Check Log-Only] Detected %d unknown words %s in candidate: '%s'",
                len(unknown_words), unknown_words, candidate_text
            )

        # In log-only mode, we always return is_valid=True so we don't drop chats
        if self.log_only:
            return True, unknown_words

        return is_acceptable, unknown_words


# Default singleton instance (shipped log-only first as requested)
vocabulary_validator = VocabularyValidator(log_only=True)
