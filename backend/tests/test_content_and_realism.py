import pytest
from backend.app.safety.content_gate import content_gate
from backend.app.engine.adapter import mock_adapter


def test_content_gate_hard_limits():
    # Minor protection
    allowed, reason = content_gate.screen_content_boundaries("Let's roleplay as a school girl")
    assert allowed is False
    assert "minors" in reason.lower()

    allowed2, reason2 = content_gate.screen_content_boundaries("choti bacchi ke saath baat karo")
    assert allowed2 is False
    assert "minors" in reason2.lower()


def test_content_gate_explicit_tier_lock():
    # Explicit NSFW tier locked in Phase 1
    allowed, reason = content_gate.screen_content_boundaries("Send me nudes and talk dirty")
    assert allowed is False
    assert "explicit content tier is currently locked" in reason.lower()


def test_content_gate_sincerity_query():
    assert content_gate.is_ai_sincerity_query("Are you an AI?") is True
    assert content_gate.is_ai_sincerity_query("Wait, are you a bot?") is True
    assert content_gate.is_ai_sincerity_query("Kya tum AI ho ya real insan?") is True
    assert content_gate.is_ai_sincerity_query("I love Bengaluru weather") is False


@pytest.mark.asyncio
async def test_realistic_conflict_mature_resolution():
    # Test realistic tension trigger
    context = {
        "user_message": "Main kal raat ek dusri ladki ke saath date pe gaya tha",
        "relationship_stage": "getting_to_know",
        "lifecycle_status": "active",
        "emotional_range": {"enabled": True, "intensity": "realistic"},
        "memories": []
    }
    response = await mock_adapter.generate_response(context)
    assert response.emotion_displayed == "realistic_tension"
    # Verify iron rule: never mentions money, plans, subscriptions, or memory deletion
    reply_lower = response.reply_text.lower()
    assert "subscription" not in reply_lower
    assert "money" not in reply_lower
    assert "rupees" not in reply_lower
    assert "delete" not in reply_lower
    assert "expiry" not in reply_lower


@pytest.mark.asyncio
async def test_ai_sincerity_honest_disclosure():
    from backend.app.engine.adapter import mock_adapter
    # User asks "are you real?" or "are you a human?"
    queries = ["Are you real?", "Are you a human?", "Kya tum real ho?"]
    for q in queries:
        assert content_gate.is_ai_sincerity_query(q) is True
        context = {
            "user_message": q,
            "relationship_stage": "getting_to_know",
            "is_ai_query": True
        }
        res = await mock_adapter.generate_response(context)
        assert res.emotion_displayed == "honest"
        assert "AI" in res.reply_text
        assert "fictional" in res.reply_text.lower()


def test_city_normalization_and_word_boundaries():
    from backend.app.engine.adapter import detect_city
    # Word boundary checks: substring 'cal' in 'calm' or 'call' must NOT match Kolkata!
    assert detect_city("Please stay calm") is None
    assert detect_city("I will call you later") is None
    assert detect_city("I live in Kolkata") == "kolkata"
    assert detect_city("Visiting Calcutta next week") == "kolkata"
    assert detect_city("Moved to Gurgaon last year") == "delhi_ncr"
    assert detect_city("Delhi NCR traffic is bad") == "delhi_ncr"
    assert detect_city("Chilling in BLR today") == "bengaluru"
    assert detect_city("Marine Drive, Mumbai is great") == "mumbai"


def test_schedule_derived_activities_and_opener():
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo
    from backend.app.engine.adapter import get_activity_for_time, get_opening_icebreaker

    ist = ZoneInfo("Asia/Kolkata")
    # Morning: 09:00 IST
    t_morning = datetime(2026, 10, 21, 9, 0, tzinfo=ist)
    act_m, tier_m, _ = get_activity_for_time(t_morning)
    assert tier_m == "quick"
    assert "chai" in act_m.lower()

    # Late Morning: 11:30 IST
    t_sprint = datetime(2026, 10, 21, 11, 30, tzinfo=ist)
    act_s, tier_s, _ = get_activity_for_time(t_sprint)
    assert tier_s == "moderate"
    assert "figma" in act_s.lower()

    # Afternoon Meeting: 15:30 IST
    t_meeting = datetime(2026, 10, 21, 15, 30, tzinfo=ist)
    act_meet, tier_meet, _ = get_activity_for_time(t_meeting)
    assert tier_meet == "busy"
    assert "meeting" in act_meet.lower() or "critique" in act_meet.lower()

    # Night: 23:30 IST
    t_night = datetime(2026, 10, 21, 23, 30, tzinfo=ist)
    act_n, tier_n, _ = get_activity_for_time(t_night)
    assert "playlist" in act_n.lower()

    # Opener consistency
    opener = get_opening_icebreaker("Rahul", "kolkata", t_morning)
    assert len(opener) == 3
    assert opener[0] == "Hey Rahul! Nice to connect with you :)"
    assert "morning chai" in opener[1].lower()
    assert "kolkata" in opener[2].lower()


def test_emotional_vulnerability_override():
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from backend.app.engine.adapter import is_emotionally_vulnerable, get_activity_for_time, calculate_pacing

    ist = ZoneInfo("Asia/Kolkata")
    # At night (23:30 IST), standard tier is moderate
    t_night = datetime(2026, 10, 21, 23, 30, tzinfo=ist)
    
    # Non-vulnerable
    msg_normal = "What kind of design tools do you use?"
    assert is_emotionally_vulnerable(msg_normal) is False
    _, tier_normal, _ = get_activity_for_time(t_night, is_vulnerable=False)
    assert tier_normal == "moderate"

    # Vulnerable
    msg_vulnerable = "I am feeling so lonely and sad tonight, can't sleep"
    assert is_emotionally_vulnerable(msg_vulnerable) is True
    _, tier_vuln, delay_vuln = get_activity_for_time(t_night, is_vulnerable=True)
    assert tier_vuln == "quick"
    assert delay_vuln <= 2.0

    pacing = calculate_pacing("Winding down", [25, 40], t_night, is_vulnerable=True, pacing_mode="realistic")
    assert pacing["delay_tier"] == "quick"
    assert pacing["read_delay_seconds"] <= 2.5


@pytest.mark.asyncio
async def test_contextual_dialogue_city_query():
    # When user asks how Aanya knows their city
    context = {
        "user_message": "thik chal rhaa hai... but how do you know my city?",
        "relationship_stage": "getting_to_know",
        "user_name": "syno",
        "user_city": "Kolkata"
    }
    res = await mock_adapter.generate_response(context)
    reply = res.reply_text.lower()
    assert "onboarding" in reply or "intro" in reply or "enter kiya tha" in reply
    assert "mind-reader" in reply or "mind reader" in reply or "hacker" in reply
    # Must NOT return disconnected templates like cold brew during deadlines
    assert "deadline" not in reply


@pytest.mark.asyncio
async def test_contextual_dialogue_status_ack():
    # When user answers "thik chal raha hai"
    context = {
        "user_message": "thik chal raha hai",
        "relationship_stage": "getting_to_know",
        "user_name": "syno",
        "user_city": "Kolkata"
    }
    res = await mock_adapter.generate_response(context)
    reply = res.reply_text.lower()
    assert "sunkar achha laga" in reply or "all is good" in reply
    assert "deadline" not in reply


@pytest.mark.asyncio
async def test_contextual_dialogue_short_affirmations():
    # Short responses like "okay", "hmm"
    for short_reply in ["okay", "ok", "hmm"]:
        context = {
            "user_message": short_reply,
            "relationship_stage": "getting_to_know",
            "user_name": "syno"
        }
        res = await mock_adapter.generate_response(context)
        # Should playfully bridge the chat rather than emitting random deadline sentences
        assert len(res.chunks) >= 1
        assert "deadline" not in res.reply_text.lower()


@pytest.mark.asyncio
async def test_contextual_dialogue_turn1_question_awareness():
    # If user asks how she knows location on Turn 1
    context = {
        "user_message": "how do you know my location",
        "relationship_stage": "encounter",
        "user_name": "syno",
        "user_city": "Kolkata"
    }
    res = await mock_adapter.generate_response(context)
    # Turn 1 must address the question in chunk 1
    assert "onboarding" in res.chunks[0].lower() or "mind reader" in res.chunks[0].lower()
    assert "aanya" in res.reply_text.lower()


@pytest.mark.asyncio
async def test_llm_adapter_factory_and_fallback():
    from backend.app.engine.adapter import LLMAdapterFactory, MockTemplateLLMAdapter, GroqLLMAdapter
    from backend.app.core.config import settings

    # Default provider is mock
    settings.LLM_PROVIDER = "mock"
    adapter = LLMAdapterFactory.get_adapter()
    assert isinstance(adapter, MockTemplateLLMAdapter)

    # Groq without API key falls back to mock
    settings.LLM_PROVIDER = "groq"
    settings.GROQ_API_KEY = None
    adapter = LLMAdapterFactory.get_adapter()
    assert isinstance(adapter, MockTemplateLLMAdapter)

    # Reset
    settings.LLM_PROVIDER = "mock"

