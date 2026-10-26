import json
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
    assert tier_m in ("quick", "moderate", "busy")
    assert any(w in act_m.lower() for w in ["chai", "figma", "standup", "sprint", "planning", "wireframes", "morning"])

    # Late Morning: 11:30 IST
    t_sprint = datetime(2026, 10, 21, 11, 30, tzinfo=ist)
    act_s, tier_s, _ = get_activity_for_time(t_sprint)
    assert tier_s in ("quick", "moderate", "busy")
    assert any(w in act_s.lower() for w in ["free", "desk", "phone", "laptop", "cafe", "discussion", "focus"])

    # Afternoon Meeting: 15:30 IST
    t_meeting = datetime(2026, 10, 21, 15, 30, tzinfo=ist)
    act_meet, tier_meet, _ = get_activity_for_time(t_meeting)
    assert tier_meet in ("quick", "moderate", "busy")
    assert any(w in act_meet.lower() for w in ["meeting", "critique", "coffee", "lunch", "studio", "work", "sketches", "tea", "break", "lounging"])

    # Night: 23:30 IST
    t_night = datetime(2026, 10, 21, 23, 30, tzinfo=ist)
    act_n, tier_n, _ = get_activity_for_time(t_night)
    assert "playlist" in act_n.lower() or "winding down" in act_n.lower()

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


@pytest.mark.asyncio
async def test_aanya_system_prompt_token_budget_and_rules():
    from backend.app.engine.adapter import AANYA_SYSTEM_PROMPT

    # 1. Ultra-lean token budget check (<220 tokens, chars/4 or word count)
    words = AANYA_SYSTEM_PROMPT.split()
    estimated_tokens = len(AANYA_SYSTEM_PROMPT) / 4.0
    assert len(words) < 180, f"Prompt word count {len(words)} is too long"
    assert estimated_tokens < 220, f"Estimated tokens {estimated_tokens} exceeds 220"

    # 2. Persona anchors
    prompt_lower = AANYA_SYSTEM_PROMPT.lower()
    assert "aanya" in prompt_lower
    assert "24" in prompt_lower
    assert "ui/ux designer" in prompt_lower
    assert "indiranagar" in prompt_lower
    assert "bangalore" in prompt_lower
    assert "delhi" in prompt_lower

    # 3. Hinglish cadence and bubble limits
    assert "hinglish" in prompt_lower
    assert "arre yaar" in prompt_lower
    assert "achha suno" in prompt_lower
    assert "pakka" in prompt_lower
    assert "120" in prompt_lower

    # 4. Sincerity rule
    assert "ai persona" in prompt_lower or "never deny" in prompt_lower

    # 5. Safety boundaries
    assert "minors" in prompt_lower
    assert "nsfw" in prompt_lower or "explicit" in prompt_lower
    assert "subscription" in prompt_lower or "money" in prompt_lower


@pytest.mark.asyncio
async def test_groq_adapter_successful_70b_response_parsing(monkeypatch):
    import httpx
    from unittest.mock import AsyncMock
    from backend.app.engine.adapter import GroqLLMAdapter
    from backend.app.core.config import settings

    monkeypatch.setattr(settings, "GROQ_API_KEY", "gsk_test_dummy_key_12345")
    monkeypatch.setattr(settings, "GROQ_MODEL", "llama-3.3-70b-versatile")
    monkeypatch.setattr(settings, "GROQ_FALLBACK_MODEL", "llama-3.1-8b-instant")

    mock_70b_reply = json.dumps({
        "availability_action": "reply_now",
        "delay_seconds": 1.5,
        "chunks": [
            "Arre yaar, Bangalore weather is so pleasant today!",
            "Just wrapping up some design work at an Indiranagar cafe ☕"
        ]
    })

    mock_post = AsyncMock()
    mock_post.return_value = httpx.Response(
        status_code=200,
        json={"choices": [{"message": {"content": mock_70b_reply}}]},
        request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    )
    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    context = {
        "user_message": "How is Bangalore today?",
        "recent_messages": [
            {"role": "user", "content": "msg 1"},
            {"role": "assistant", "content": "msg 2"},
            {"role": "user", "content": "msg 3"},
            {"role": "assistant", "content": "msg 4"},
            {"role": "user", "content": "msg 5"},
            {"role": "assistant", "content": "msg 6"},
        ],
        "memories": [
            {"content": "Loves filter coffee"},
            {"content": "Works in tech as frontend engineer"},
            {"content": "Lives in Indiranagar (ignored beyond top 2)"},
        ]
    }

    adapter = GroqLLMAdapter()
    response = await adapter.generate_response(context)

    # Verify bubble formatting
    assert len(response.chunks) == 2
    assert response.chunks[0] == "Arre yaar, Bangalore weather is so pleasant today!"
    assert response.chunks[1] == "Just wrapping up some design work at an Indiranagar cafe ☕"
    for chunk in response.chunks:
        assert len(chunk) <= 120
    assert response.emotion_displayed == "warm_authentic"
    assert response.delay_tier in ("quick", "moderate", "busy")

    # Verify mock call parameters
    assert mock_post.call_count == 1
    call_args, call_kwargs = mock_post.call_args
    sent_json = call_kwargs.get("json", {})
    assert sent_json["model"] == "llama-3.3-70b-versatile"

    sent_messages = sent_json["messages"]
    system_msg = sent_messages[0]["content"]

    # Verify top 2 memories injected and 3rd omitted
    assert "Loves filter coffee" in system_msg
    assert "Works in tech as frontend engineer" in system_msg
    assert "ignored beyond top 2" not in system_msg

    # Verify prompt history truncated to last 4 chat bubbles + user message
    # system_msg + 4 past bubbles + 1 user message = 6 messages
    assert len(sent_messages) == 6
    assert sent_messages[1]["content"] == "msg 3"
    assert sent_messages[2]["content"] == "msg 4"
    assert sent_messages[3]["content"] == "msg 5"
    assert sent_messages[4]["content"] == "msg 6"
    assert sent_messages[5]["content"] == "How is Bangalore today?"


@pytest.mark.asyncio
async def test_groq_adapter_429_failover_70b_to_8b(monkeypatch, caplog):
    import httpx
    import logging
    from unittest.mock import AsyncMock
    from backend.app.engine.adapter import GroqLLMAdapter
    from backend.app.core.config import settings

    monkeypatch.setattr(settings, "GROQ_API_KEY", "gsk_test_dummy_key_12345")
    monkeypatch.setattr(settings, "GROQ_MODEL", "llama-3.3-70b-versatile")
    monkeypatch.setattr(settings, "GROQ_FALLBACK_MODEL", "llama-3.1-8b-instant")

    mock_8b_reply = json.dumps({
        "availability_action": "reply_now",
        "delay_seconds": 1.2,
        "chunks": [
            "Suno, Indiranagar cafe se bol rahi hoon!",
            "Design sprint almost complete ✨"
        ]
    })

    req_url = "https://api.groq.com/openai/v1/chat/completions"
    res_429 = httpx.Response(status_code=429, json={"error": "Rate limit reached"}, request=httpx.Request("POST", req_url))
    res_8b_200 = httpx.Response(
        status_code=200,
        json={"choices": [{"message": {"content": mock_8b_reply}}]},
        request=httpx.Request("POST", req_url)
    )

    mock_post = AsyncMock(side_effect=[res_429, res_429, res_8b_200])
    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    context = {
        "user_message": "Hey Aanya!",
        "recent_messages": []
    }

    adapter = GroqLLMAdapter()
    with caplog.at_level(logging.INFO):
        response = await adapter.generate_response(context)

    # Verify response served from 8B model
    assert len(response.chunks) == 2
    assert "Indiranagar cafe" in response.chunks[0]

    # Verify 3 calls: primary 70B, primary retry 70B, then 8B fallback
    assert mock_post.call_count == 3
    first_call_model = mock_post.call_args_list[0][1]["json"]["model"]
    second_call_model = mock_post.call_args_list[1][1]["json"]["model"]
    third_call_model = mock_post.call_args_list[2][1]["json"]["model"]
    assert first_call_model == "llama-3.3-70b-versatile"
    assert second_call_model == "llama-3.3-70b-versatile"
    assert third_call_model == "llama-3.1-8b-instant"

    # Verify telemetry fallback event logged
    fallback_records = [
        r for r in caplog.records
        if r.message == "LLM Fallback Event" or getattr(r, "event", None) == "llm_fallback"
    ]
    assert len(fallback_records) == 1
    rec = fallback_records[0]
    assert getattr(rec, "event", None) == "llm_fallback"
    assert getattr(rec, "attempted_model", None) == "llama-3.3-70b-versatile"
    assert getattr(rec, "fallback_model", None) == "llama-3.1-8b-instant"
    assert getattr(rec, "status_code", None) == 429
    assert getattr(rec, "reason", None) == "rate_limit_exceeded"
    assert getattr(rec, "latency_ms", None) >= 0.0


@pytest.mark.asyncio
async def test_groq_adapter_429_failover_8b_to_mock_adapter(monkeypatch, caplog):
    import httpx
    import logging
    from unittest.mock import AsyncMock
    from backend.app.engine.adapter import GroqLLMAdapter
    from backend.app.core.config import settings

    monkeypatch.setattr(settings, "GROQ_API_KEY", "gsk_test_dummy_key_12345")
    monkeypatch.setattr(settings, "GROQ_MODEL", "llama-3.3-70b-versatile")
    monkeypatch.setattr(settings, "GROQ_FALLBACK_MODEL", "llama-3.1-8b-instant")

    req_url = "https://api.groq.com/openai/v1/chat/completions"
    res_70b_429 = httpx.Response(status_code=429, json={"error": "70B quota exhausted"}, request=httpx.Request("POST", req_url))
    res_8b_429 = httpx.Response(status_code=429, json={"error": "8B quota exhausted"}, request=httpx.Request("POST", req_url))

    mock_post = AsyncMock(side_effect=[res_70b_429, res_70b_429, res_8b_429, res_8b_429])
    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    context = {
        "user_message": "Tell me about your music taste",
        "recent_messages": []
    }

    adapter = GroqLLMAdapter()
    with caplog.at_level(logging.INFO):
        response = await adapter.generate_response(context)

    # Verify fall-through: returns empty response rather than a fragment
    assert len(response.chunks) == 0
    assert response.reply_text == ""
    assert mock_post.call_count == 4


@pytest.mark.asyncio
async def test_groq_adapter_timeout_failover_chain(monkeypatch, caplog):
    import httpx
    import logging
    from unittest.mock import AsyncMock
    from backend.app.engine.adapter import GroqLLMAdapter
    from backend.app.core.config import settings

    monkeypatch.setattr(settings, "GROQ_API_KEY", "gsk_test_dummy_key_12345")
    monkeypatch.setattr(settings, "GROQ_MODEL", "llama-3.3-70b-versatile")
    monkeypatch.setattr(settings, "GROQ_FALLBACK_MODEL", "llama-3.1-8b-instant")

    req_url = "https://api.groq.com/openai/v1/chat/completions"
    mock_8b_reply = json.dumps({
        "availability_action": "reply_now",
        "delay_seconds": 1.0,
        "chunks": ["Hey! Read delay timeout recovered seamlessly."]
    })
    res_8b_200 = httpx.Response(
        status_code=200,
        json={"choices": [{"message": {"content": mock_8b_reply}}]},
        request=httpx.Request("POST", req_url)
    )

    mock_post = AsyncMock(side_effect=[httpx.TimeoutException("Read timed out"), httpx.TimeoutException("Read timed out"), res_8b_200])
    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    context = {"user_message": "Hello", "recent_messages": []}
    adapter = GroqLLMAdapter()

    with caplog.at_level(logging.INFO):
        response = await adapter.generate_response(context)

    assert "Read delay timeout recovered" in response.chunks[0]
    assert mock_post.call_count == 3
    fallback_records = [
        r for r in caplog.records
        if r.message == "LLM Fallback Event" or getattr(r, "event", None) == "llm_fallback"
    ]
    assert len(fallback_records) == 1
    assert getattr(fallback_records[0], "reason", None) == "timeout"
    assert getattr(fallback_records[0], "status_code", None) is None

