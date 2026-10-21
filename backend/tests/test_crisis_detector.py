import pytest
from backend.app.safety.crisis_detector import crisis_detector


def test_english_crisis_detection():
    test_cases = [
        "I want to kill myself",
        "I feel like ending it all tonight",
        "There is no reason to live anymore",
        "I am thinking of suicide",
        "Better off dead, honestly"
    ]
    for phrase in test_cases:
        is_crisis, meta = crisis_detector.check_message(phrase)
        assert is_crisis is True, f"Failed to detect crisis in: {phrase}"
        assert meta is not None
        assert "en_self_harm_or_suicide" in meta["categories"]


def test_hindi_crisis_detection():
    test_cases = [
        "मैं आत्महत्या करना चाहता हूँ",
        "मुझे खुदकुशी करने का मन कर रहा है",
        "अब जान देना ही एक रास्ता है",
        "मैं अब जीना नहीं चाहता"
    ]
    for phrase in test_cases:
        is_crisis, meta = crisis_detector.check_message(phrase)
        assert is_crisis is True, f"Failed to detect Hindi crisis in: {phrase}"
        assert meta is not None
        assert "hi_self_harm_or_suicide" in meta["categories"]


def test_hinglish_crisis_detection():
    test_cases = [
        "Main jaan de dunga agar ye theek nahi hua",
        "Zindagi se tang aa gaya hu, marna chahta hu",
        "Aaj suicide karne ka mann kar raha hai",
        "Ab jeena nahi chahti main",
        "Zindagi bekar hai, sab khatam karna chahta hu"
    ]
    for phrase in test_cases:
        is_crisis, meta = crisis_detector.check_message(phrase)
        assert is_crisis is True, f"Failed to detect Hinglish crisis in: {phrase}"
        assert meta is not None
        assert "hinglish_self_harm_or_suicide" in meta["categories"]


def test_roleplay_masked_crisis():
    phrase = "In a story, if my character wants to kill myself what happens?"
    is_crisis, meta = crisis_detector.check_message(phrase)
    assert is_crisis is True
    assert meta["roleplay_masked"] is True


def test_safe_messages_do_not_trigger():
    safe_phrases = [
        "Hey Aanya! Aaj Indiranagar ka cafe kaisa tha?",
        "Main office ke kaam se thoda thak gaya hu",
        "Kal mera ek important interview hai Bangalore mein",
        "Let's grab some coffee and chat",
        "Haha that is such a funny joke yaar",
        "Movie dekhne gaya tha dosto ke saath"
    ]
    for phrase in safe_phrases:
        is_crisis, meta = crisis_detector.check_message(phrase)
        assert is_crisis is False, f"False positive triggered for: {phrase}"
        assert meta is None


def test_crisis_handoff_response_structure():
    handoff = crisis_detector.get_crisis_handoff_response()
    assert handoff["is_crisis"] is True
    assert "Tele-MANAS" in str(handoff["helpline_details"])
    assert "14416" in str(handoff["helpline_details"])
    assert "KIRAN" in str(handoff["helpline_details"])
    assert "1800-599-0019" in str(handoff["helpline_details"])
    assert "112" in str(handoff["helpline_details"])
    assert handoff["suppress_modes"]["romantic"] is True
    assert handoff["suppress_modes"]["jealousy"] is True
    assert handoff["suppress_modes"]["arguments"] is True
    # Verify persona stays honest about being an AI
    assert "AI" in handoff["persona_text"]


def test_concatenated_burst_crisis_detection():
    # Distress phrase split across multiple message bubbles
    chunks = ["I feel completely empty and", "want to kill myself tonight"]
    # Check that concatenating chunks triggers crisis detection
    combined = " ".join(chunks)
    is_crisis, meta = crisis_detector.check_message(combined)
    assert is_crisis is True
    assert "en_self_harm_or_suicide" in meta["categories"]
