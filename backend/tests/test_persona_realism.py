"""
Comprehensive test suite verifying Persona Realism for Aanya:
1. Fixed Persona Sheet JSON injection and boundaries (no fake handles/addresses, Instagram deflection)
2. Hard Rules:
   - Female Hindi grammar post-check regex (flags karta hoon, gaya, raha) and fixes
   - Consistent addressing as 'tum' (never bro, bhai, tu, aap)
   - 'Arre' opener ratio limit (< 1 in 10 messages)
   - Banned phrases ('chill', 'gut feeling', 'brain freeze', 'haan haan')
   - Question frequency cap (<= 1 in 3 replies) and no generic unprompted questions
   - Clarification handling ('Mtlb?', 'Kyuuu') & 'pata nahi'
3. IST Context & Routine State injection (weekday vs weekend, sleeping, working, free)
4. Fact Memory extraction, persistence, injection, and contradiction screening
5. Gemini 2.5 Flash configuration and fallback chain
6. Spontaneous messages respecting routine & Render keep-awake ping
"""

import pytest
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from unittest.mock import AsyncMock, patch

from backend.app.core.config import settings
from backend.app.engine.persona import (
    AANYA_PERSONA_SHEET,
    AANYA_PERSONA_SHEET_JSON,
    get_ist_context,
    build_system_prompt,
    validate_and_sanitize_response,
    fix_male_grammar,
    check_for_male_grammar,
    MALE_GRAMMAR_COMPILED
)
from backend.app.services.memory_service import memory_service
from backend.app.services.scheduler_service import scheduler_service
from backend.app.engine.adapter import (
    MockTemplateLLMAdapter,
    GeminiLLMAdapter,
    GroqLLMAdapter,
    LLMAdapterFactory,
    mock_adapter
)


def test_persona_sheet_canonical_integrity():
    """Verify Persona Sheet fixed JSON parameters."""
    assert AANYA_PERSONA_SHEET["name"] == "Aanya"
    assert AANYA_PERSONA_SHEET["gender"] == "female"
    assert AANYA_PERSONA_SHEET["age"] == 24
    assert AANYA_PERSONA_SHEET["hometown"] == "Delhi"
    assert AANYA_PERSONA_SHEET["current_city"] == "Bengaluru"
    assert AANYA_PERSONA_SHEET["neighborhood"] == "Indiranagar"
    assert AANYA_PERSONA_SHEET["job"] == "Freelance UI/UX Designer"
    assert "private rakhti hoon" in AANYA_PERSONA_SHEET["privacy_boundaries"]["instagram_deflection"]
    assert "weekday" in AANYA_PERSONA_SHEET["routine_schedule"]
    assert "weekend" in AANYA_PERSONA_SHEET["routine_schedule"]


def test_ist_context_injection():
    """Verify IST date, day of week, time, and routine state resolution."""
    # Weekday 11:00 AM IST (Working)
    dt_weekday_work = datetime(2026, 10, 26, 5, 30, tzinfo=timezone.utc)  # Monday 11:00 AM IST
    ctx1 = get_ist_context(dt_weekday_work)
    assert ctx1["day_of_week"] == "Monday"
    assert ctx1["is_weekend"] is False
    assert ctx1["routine_state"] == "working"
    assert "Figma" in ctx1["activity_desc"]

    # Weekend 14:00 IST (Free - No office)
    dt_weekend_afternoon = datetime(2026, 10, 25, 8, 30, tzinfo=timezone.utc)  # Sunday 2:00 PM IST
    ctx2 = get_ist_context(dt_weekend_afternoon)
    assert ctx2["day_of_week"] == "Sunday"
    assert ctx2["is_weekend"] is True
    assert ctx2["routine_state"] == "free"
    assert "no office work" in ctx2["behavior_note"].lower()

    # Late Night 00:30 IST (Winding down / Sleeping)
    dt_late_night = datetime(2026, 10, 25, 19, 0, tzinfo=timezone.utc)  # 00:30 AM IST Monday
    ctx3 = get_ist_context(dt_late_night)
    assert ctx3["routine_state"] == "sleeping"
    assert "sleepy" in ctx3["behavior_note"].lower() or "drowsy" in ctx3["behavior_note"].lower()


def test_male_grammar_detection_and_fix():
    """Verify post-check regex flags male verb forms and corrects them to female forms."""
    male_samples = [
        "Main kal market gaya tha",
        "Main subah se soch raha tha ki kya karun",
        "Aaj main thak gaya hoon",
        "Main roz Figma pe kaam karta hoon",
        "Main abhi lunch kar raha hoon"
    ]
    for text in male_samples:
        assert check_for_male_grammar(text) is True, f"Failed to flag male grammar: {text}"
        fixed = fix_male_grammar(text)
        assert check_for_male_grammar(fixed) is False, f"Fix retained male grammar: {fixed}"
        assert any(fem in fixed for fem in ["gayi", "soch rahi", "thak gayi", "karti hoon", "kar rahi hoon"])

    # Female forms should NOT be flagged
    female_samples = [
        "main kal market gayi thi",
        "main subah se soch rahi thi",
        "aaj main thak gayi hoon",
        "main roz design ka kaam karti hoon",
        "coffee bana rahi hoon ☕"
    ]
    for text in female_samples:
        assert check_for_male_grammar(text) is False


def test_banned_phrases_and_addressing_sanitization():
    """Verify banned words (chill, gut feeling, brain freeze, haan haan, bro, bhai, tu) are sanitized."""
    raw = "Haan haan bro, chill karo. Mera gut feeling bol raha tha tu theek hai."
    is_valid, sanitized, failures = validate_and_sanitize_response(
        raw_text=raw,
        recent_assistant_messages=[],
        user_message="Hey"
    )
    assert is_valid is False
    assert "chill" not in sanitized.lower()
    assert "gut feeling" not in sanitized.lower()
    assert "bro" not in sanitized.lower()
    assert "haan haan" not in sanitized.lower()
    # Should address as tum or yaar
    assert "tum" in sanitized.lower() or "yaar" in sanitized.lower()


def test_arre_opener_ratio_limit():
    """Starting with 'Arre' is banned if used in more than 1 in 10 messages."""
    # Last message already started with Arre
    recent_asst = [
        "arre yaar, aaj bahut traffic tha",
        "suno, coffee pee li?",
        "theek hai"
    ]
    raw = "Arre yaar, main market jaa rahi hoon"
    is_valid, sanitized, failures = validate_and_sanitize_response(
        raw_text=raw,
        recent_assistant_messages=recent_asst,
        user_message="kya plan hai?"
    )
    assert "excessive_arre_opener" in failures
    assert not sanitized.lower().startswith("arre")


def test_question_frequency_cap_and_generic_question_ban():
    """Question frequency capped to <= 1 in 3 replies; unprompted generic questions banned."""
    recent_asst = [
        "coffee pee li maine ☕",
        "aaj mausam kaisa hai wahan?"  # Question asked here
    ]
    raw_with_question = "main Indiranagar me hoon. tumhara mood kaisa hai?"
    is_valid, sanitized, failures = validate_and_sanitize_response(
        raw_text=raw_with_question,
        recent_assistant_messages=recent_asst,
        user_message="kahan ho?"
    )
    assert is_valid is False
    # Generic question stripped and trailing question mark removed
    assert "mood kaisa" not in sanitized.lower()
    assert "?" not in sanitized


def test_instagram_deflection_rule():
    """Verify natural deflection when asked for Instagram handle."""
    is_valid, sanitized, failures = validate_and_sanitize_response(
        raw_text="Follow me at @aanya_design",
        recent_assistant_messages=[],
        user_message="Instagram id kya hai tumhari?"
    )
    assert "private rakhti hoon" in sanitized.lower()
    assert "@" not in sanitized


def test_fact_memory_extraction():
    """Verify structured extraction of user name, city, job, preferences."""
    text1 = "Mera naam Rahul hai aur main Delhi se software engineer hoon"
    facts1 = memory_service.extract_user_facts(text1)
    fact_types = {f["type"]: f["content"] for f in facts1}
    assert "user_name" in fact_types
    assert "Rahul" in fact_types["user_name"]
    assert "user_city" in fact_types
    assert "Delhi" in fact_types["user_city"]
    assert "user_job" in fact_types
    assert "Software Engineer" in fact_types["user_job"]

    text2 = "Mujhe cold coffee bahut pasand hai"
    facts2 = memory_service.extract_user_facts(text2)
    assert len(facts2) >= 1
    assert "cold coffee" in facts2[0]["content"].lower()


def test_contradiction_screening():
    """Verify draft checking against stored facts prevents contradictions."""
    stored_facts = {
        "user_facts": ["User lives in Delhi", "User's name is Rahul"],
        "persona_facts": ["Aanya lives in Indiranagar, Bengaluru"]
    }
    # Draft asking 'tum kahan rehte ho?' when city is already known
    raw_draft = "main theek hoon. tum kahan rehte ho?"
    is_valid, sanitized, failures = validate_and_sanitize_response(
        raw_text=raw_draft,
        recent_assistant_messages=[],
        user_message="kaisa chal raha hai?",
        stored_facts=stored_facts
    )
    assert "contradicts_known_user_city" in failures
    assert "kahan rehte ho" not in sanitized.lower()


@pytest.mark.asyncio
async def test_mock_adapter_persona_realism_responses():
    """Test mock template engine responses for key realistic queries."""
    # 1. Instagram deflection
    res_insta = await mock_adapter.generate_response({
        "user_message": "Instagram id kya hai?",
        "recent_messages": []
    })
    assert "private rakhti hoon" in res_insta.reply_text.lower()
    assert "@" not in res_insta.reply_text

    # 2. Clarification ('Mtlb?')
    res_mtlb = await mock_adapter.generate_response({
        "user_message": "Mtlb?",
        "recent_messages": [{"role": "assistant", "content": "aaj client call lamba chala"}]
    })
    assert "matlab" in res_mtlb.reply_text.lower()

    # 3. Whining ('Kyuuu')
    res_kyu = await mock_adapter.generate_response({
        "user_message": "Kyuuu",
        "relationship_stage": "getting_to_know",
        "recent_messages": [{"role": "assistant", "content": "aaj jaldi sona padega"}]
    })
    assert "kyunki" in res_kyu.reply_text.lower()

    # 4. Weekend query
    res_weekend = await mock_adapter.generate_response({
        "user_message": "weekend hai aaj",
        "relationship_stage": "getting_to_know",
        "recent_messages": []
    })
    assert "no office work" in res_weekend.reply_text.lower() or "cafe" in res_weekend.reply_text.lower()

    # 5. Location query
    res_loc = await mock_adapter.generate_response({
        "user_message": "tum kahan rehti ho?",
        "relationship_stage": "getting_to_know",
        "recent_messages": []
    })
    assert "bengaluru" in res_loc.reply_text.lower() or "bangalore" in res_loc.reply_text.lower()
    assert "indiranagar" in res_loc.reply_text.lower()
    assert "delhi" in res_loc.reply_text.lower()


@pytest.mark.asyncio
async def test_gemini_adapter_fallback_to_groq_when_no_gemini_key(monkeypatch):
    """Gemini adapter without API key smoothly falls back to Groq adapter."""
    monkeypatch.setattr(settings, "GEMINI_API_KEY", None)
    monkeypatch.setattr(settings, "GROQ_API_KEY", None)

    adapter = GeminiLLMAdapter()
    res = await adapter.generate_response({
        "user_message": "Hey Aanya!",
        "recent_messages": []
    })
    assert res is not None
    assert len(res.chunks) > 0


@pytest.mark.asyncio
async def test_scheduler_ping_render_awake(monkeypatch):
    """Test that keep-awake ping executes cleanly and logs run."""
    import httpx
    mock_get = AsyncMock()
    mock_get.return_value = httpx.Response(status_code=200, request=httpx.Request("GET", "http://test/health"))
    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    status = await scheduler_service.ping_render_awake()
    assert status == 200
    assert mock_get.call_count == 1
