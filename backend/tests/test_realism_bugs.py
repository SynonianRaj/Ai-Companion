import pytest
import re
import json
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from unittest.mock import AsyncMock, patch

from backend.app.core.config import settings
from backend.app.engine.persona import (
    check_prompt_leakage,
    check_truncation,
    check_stutter_repetition,
    check_near_identical,
    check_pure_echo,
    run_hard_validators,
    check_language_log_only,
    check_state_contradiction_log_only,
    build_system_prompt,
    build_heartbeat_prompt,
    derive_aanya_mood,
    get_ist_context,
    AANYA_PERSONA_SHEET
)
from backend.app.engine.adapter import (
    strip_thinking_tags,
    parse_llm_json_response,
    get_activity_for_time,
    LLMResponse
)
from backend.app.services.continuity_service import continuity_service
from backend.app.services.clock_service import ClockService
from backend.app.db.models import User, RelationshipState, Conversation, Message, PersonaDailyNote
from backend.app.engine.orchestrator import orchestrator
from sqlalchemy import select, and_


# ============================================================================
# 1. PROMPT LEAKAGE REGRESSION TESTS
# ============================================================================

def test_leakage_validator_detects_prompt_artifacts():
    # Exact failure examples from prompt
    leakage_1 = "Question Limit*: Don't ask a question in >1"
    valid, leaks = check_prompt_leakage(leakage_1)
    assert valid is False
    assert len(leaks) > 0

    leakage_2 = 'relax", "lagta hai", "brain'
    valid, leaks = check_prompt_leakage(leakage_2)
    assert valid is False
    assert len(leaks) > 0

    leakage_3 = "According to my system prompt, I am Aanya."
    valid, leaks = check_prompt_leakage(leakage_3)
    assert valid is False

    leakage_4 = "In my persona sheet I am a designer living in Indiranagar."
    valid, leaks = check_prompt_leakage(leakage_4)
    assert valid is False

    leakage_5 = 'Banned words: ["metro", "commute"]'
    valid, leaks = check_prompt_leakage(leakage_5)
    assert valid is False

    # Natural conversation should NOT be blocked
    clean_1 = "don't ask me about that meeting, it was so boring!"
    valid, leaks = check_prompt_leakage(clean_1)
    assert valid is True
    assert len(leaks) == 0

    clean_2 = "kya lagta hai tumhe, movie achhi hogi?"
    valid, leaks = check_prompt_leakage(clean_2)
    assert valid is True

    clean_3 = "relax karo yaar, weekend aa gaya!"
    valid, leaks = check_prompt_leakage(clean_3)
    assert valid is True


def test_leakage_logging_on_trip(caplog):
    import logging
    with caplog.at_level(logging.WARNING):
        chunks = ["Hey", 'relax", "lagta hai", "brain']
        is_valid, reasons = run_hard_validators(
            chunks=chunks,
            user_message="Hey Aanya",
            recent_assistant_messages=[]
        )
        assert is_valid is False
        assert any("prompt_leakage" in r for r in reasons)
        # Check raw output was logged
        assert any("Prompt leakage detected in chunk" in r.message for r in caplog.records)


# ============================================================================
# 2. TRUNCATED MESSAGES REGRESSION TESTS
# ============================================================================

def test_truncation_validator_detects_cut_words_and_fragments():
    # Exact failure examples from prompt: single isolated characters / cut words
    valid, _ = check_truncation("w")
    assert valid is False

    valid, _ = check_truncation("so rahi thi yaar... aak")
    assert valid is False

    valid, _ = check_truncation("haan bas freedom thodi milti hai par client ki")
    assert valid is False

    valid, _ = check_truncation("mera bhi abhi")
    assert valid is False

    # Complete natural sentences should NOT be flagged
    valid, _ = check_truncation("waha pe kaun kaun tha?")
    assert valid is True

    valid, _ = check_truncation("so rahi thi yaar... goodnight!")
    assert valid is True

    valid, _ = check_truncation("haan bas freedom thodi milti hai, client approvals slow hain.")
    assert valid is True

    valid, _ = check_truncation("mera bhi abhi kaam wrap hua!")
    assert valid is True


def test_truncation_finish_reason_and_json():
    # finish_reason="length"
    is_valid, reasons = run_hard_validators(
        chunks=["Haan bilkul"],
        user_message="Hey",
        recent_assistant_messages=[],
        finish_reason="length"
    )
    assert is_valid is False
    assert any("truncated_length" in r or "finish_reason_length" in r for r in reasons)

    # Empty chunks
    is_valid_empty, reasons_empty = run_hard_validators(
        chunks=[],
        user_message="Hey",
        recent_assistant_messages=[]
    )
    assert is_valid_empty is False
    assert any("empty_chunks" in r for r in reasons_empty)


# ============================================================================
# 3. FALLBACK PARITY & THINKING TAG STRIPPING
# ============================================================================

def test_strip_thinking_tags():
    # Reasoning model tags (Qwen / DeepSeek)
    raw_with_think = "<think>Let me formulate a Hinglish reply about Bangalore weather.</think>{\"availability_action\": \"reply_now\", \"delay_seconds\": 1.0, \"chunks\": [\"Bangalore ka mausam mast hai!\"]}"
    cleaned = strip_thinking_tags(raw_with_think)
    assert "<think>" not in cleaned
    assert "formulate" not in cleaned
    parsed = parse_llm_json_response(raw_with_think)
    assert parsed is not None
    assert parsed["chunks"] == ["Bangalore ka mausam mast hai!"]

    # Unclosed think tag (if cut by token limit)
    unclosed = "<think>Thinking about what to say... I should say"
    assert strip_thinking_tags(unclosed) == ""


def test_unified_json_schema_parsing():
    json_str = json.dumps({
        "availability_action": "reply_later",
        "delay_seconds": 45.0,
        "chunks": ["Thoda client work me phansi hoon.", "10 min me text karti hoon!"]
    })
    parsed = parse_llm_json_response(json_str)
    assert parsed["availability_action"] == "reply_later"
    assert parsed["delay_seconds"] == 45.0
    assert len(parsed["chunks"]) == 2


# ============================================================================
# 4. LANGUAGE CHECK (LOG-ONLY)
# ============================================================================

def test_language_validator_log_only():
    # User wrote Hinglish, model slipped into formal English paragraph
    user_msg = "aaj ka din kaisa raha?"
    model_slip = "Finally heading home. Any fun plans for the evening? It has been quite a productive day at the office."
    warning = check_language_log_only(model_slip, user_msg)
    assert warning is not None
    assert "english_slip" in warning.lower()

    # User wrote English, model replied in English -> OK!
    user_eng = "How was your day today?"
    warning2 = check_language_log_only(model_slip, user_eng)
    assert warning2 is None

    # Natural Hinglish -> OK!
    hinglish_reply = "Bas wrap kiya client work! Bangalore breeze bahar bohot pyari hai abhi."
    assert check_language_log_only(hinglish_reply, user_msg) is None


# ============================================================================
# 5. SINGLE SOURCE OF TRUTH (NO METRO COMMUTE)
# ============================================================================

def test_zero_metro_commute_references():
    # Persona sheet must not contain metro commute references
    sheet_text = json.dumps(AANYA_PERSONA_SHEET).lower()
    assert "metro commute" not in sheet_text
    assert "metro" not in sheet_text

    # Time context check across all 24 hours
    tz = ZoneInfo("Asia/Kolkata")
    for hour in range(24):
        for minute in [0, 30]:
            t = datetime(2026, 10, 26, hour, minute, tzinfo=tz)
            ctx = get_ist_context(t)
            desc = ctx["activity_desc"].lower()
            note = ctx["behavior_note"].lower()
            assert "metro" not in desc, f"Found metro in desc at {hour}:{minute}: {desc}"
            assert "commute" not in desc, f"Found commute in desc at {hour}:{minute}: {desc}"
            assert "metro" not in note, f"Found metro in note at {hour}:{minute}: {note}"


# ============================================================================
# 6. HEARTBEAT TIME SENSE & UNANSWERED QUESTION REASONING
# ============================================================================

def test_heartbeat_time_sense():
    # Morning 08:19 IST
    tz = ZoneInfo("Asia/Kolkata")
    t_morning = datetime(2026, 10, 26, 8, 19, tzinfo=tz)
    ctx_morning = get_ist_context(t_morning)
    prompt_morning = build_heartbeat_prompt(
        ist_info=ctx_morning,
        mood="balcony_coffee_fresh",
        time_since_user_str="8 hours",
        time_since_unprompted_str="14 hours",
        recent_messages=[{"role": "assistant", "content": "Goodnight!"}]
    )
    # Must have plain time label
    assert "08:19" in prompt_morning
    assert "morning" in prompt_morning.lower()
    # Must explicitly prohibit evening phrases in morning
    assert "kaam wrap hua aaj ka?" in prompt_morning

    # Sulky tone only if user left a question unanswered and > 2 hours passed
    recent_with_q = [
        {"role": "user", "content": "hey"},
        {"role": "assistant", "content": "aaj kya plan hai shaam ka?"}
    ]
    # At 1.5 hours -> NOT sulky
    mood_1h = derive_aanya_mood(ctx_morning, hours_since_user=1.5, recent_messages=recent_with_q)
    assert "sulky" not in mood_1h

    # At 2.5 hours -> Sulky
    mood_2_5h = derive_aanya_mood(ctx_morning, hours_since_user=2.5, recent_messages=recent_with_q)
    assert "a_little_sulky" in mood_2_5h


# ============================================================================
# 7. DEGENERATE OUTPUT REJECTION (STUTTER, REPETITION, ECHO)
# ============================================================================

def test_reject_stutter_repetition():
    stutter = "koi baat nahi, koi nahi, koi baat nahi yaar"
    valid, _ = check_stutter_repetition(stutter)
    assert valid is False

    clean = "koi baat nahi yaar, main samajh sakti hoon!"
    valid, _ = check_stutter_repetition(clean)
    assert valid is True


def test_reject_near_identical_previous():
    prev = ["Haan bilkul, main abhi Figma pe dashboard designs bana rahi hoon!"]
    duplicate = "Haan bilkul, main abhi Figma pe dashboard designs bana rahi hoon!"
    valid, _ = check_near_identical(duplicate, prev)
    assert valid is False

    different = "Suno, lunch me kya khaya aaj?"
    valid, _ = check_near_identical(different, prev)
    assert valid is True


def test_reject_pure_echo():
    user = "aaj kaafi thand hai Delhi mein"
    echo = "aaj kaafi thand hai Delhi mein!"
    valid, _ = check_pure_echo(echo, user)
    assert valid is False

    reply = "sahi me? Delhi winter ki chai bohot miss ho rahi hai!"
    valid, _ = check_pure_echo(reply, user)
    assert valid is True


# ============================================================================
# 8. AVAILABILITY, DELAY QUEUE & SEEN_AT INVARIANT
# ============================================================================

@pytest.mark.asyncio
async def test_seen_at_le_deliver_at_invariant(db_session):
    """
    INVARIANT: seen_at <= deliver_at of her reply, ALWAYS.
    If she replies, she must have seen the message first.
    """
    user = User(username="invariant_user", age_eligibility_status=True, ai_disclosure_acknowledged=True)
    db_session.add(user)
    await db_session.flush()

    rel = RelationshipState(user_id=user.id, persona_id="aanya_v1", lifecycle_status="active")
    db_session.add(rel)
    await db_session.flush()

    conv = Conversation(relationship_id=rel.id, user_id=user.id, persona_id=rel.persona_id)
    db_session.add(conv)
    await db_session.commit()

    # Process message in realistic pacing
    res = await orchestrator.process_user_message(
        session=db_session,
        user=user,
        relationship=rel,
        conversation=conv,
        user_message="Hey Aanya, kya kar rahi ho?",
        pacing_mode="realistic"
    )

    stmt_msgs = (
        select(Message)
        .where(Message.relationship_id == rel.id)
        .order_by(Message.id.asc())
    )
    msgs = (await db_session.execute(stmt_msgs)).scalars().all()

    user_msgs = [m for m in msgs if m.role == "user"]
    asst_msgs = [m for m in msgs if m.role == "assistant"]

    if asst_msgs:
        # For each assistant reply, user message seen_at must be <= asst deliver_at
        user_seen_at = user_msgs[0].seen_at
        for asst in asst_msgs:
            assert user_seen_at <= asst.deliver_at, f"VIOLATION: seen_at {user_seen_at} > deliver_at {asst.deliver_at}"


# ============================================================================
# 9. CONTINUITY: DAILY MICRO-JOURNAL INJECTION & CONSTRAINTS
# ============================================================================

@pytest.mark.asyncio
async def test_continuity_micro_journal(db_session):
    tz = ZoneInfo("Asia/Kolkata")
    t_fixed = datetime(2026, 10, 26, 10, 0, tzinfo=tz)
    notes = await continuity_service.get_or_create_daily_notes(db_session, "aanya_v1", t_fixed)
    assert len(notes) >= 2

    # Verify no future leakage at 10 AM (morning only)
    notes_10am = await continuity_service.get_daily_notes_for_time(db_session, "aanya_v1", t_fixed)
    assert len(notes_10am) >= 1
    for note in notes_10am:
        note_str = note.get("text", str(note)) if isinstance(note, dict) else str(note)
        # Shouldn't mention evening or late night activities
        assert "dinner" not in note_str.lower()
        assert "night" not in note_str.lower()
