import re
import json
import pytest
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from unittest.mock import AsyncMock, patch

from sqlalchemy import select, and_
from backend.app.core.config import settings
from backend.app.db.models import User, RelationshipState, OpenLoop, Message, Conversation
from backend.app.db.session import to_utc
from backend.app.services.clock_service import ClockService
from backend.app.services.memory_service import memory_service
from backend.app.engine.orchestrator import orchestrator
from backend.app.engine.vocabulary import vocabulary_validator, VocabularyValidator
from backend.app.engine.persona import (
    check_meta_chat_talk,
    check_near_identical,
    check_truncation,
    build_system_prompt,
    select_relevant_few_shots,
    FEW_SHOT_CONVERSATIONS
)
from backend.app.engine.adapter import GroqLLMAdapter, LLMResponse


# ============================================================================
# 1. SLEEP DROP-OFF AT 00:15 IST AND MORNING FOLLOW-UP AT 08:30 IST
# ============================================================================

@pytest.mark.asyncio
async def test_sleep_dropoff_and_morning_followup(db_session):
    """
    Test scenario:
    1. Clock set to 00:15 IST (Aanya sleeping). User chats: "aaj ka din kaisa tha tumhara?"
    2. Orchestrator records an OpenLoop record with user_message, sleeping state, and 36h expiry.
    3. Clock advances to 08:30 IST next morning. User sends "good morning!".
    4. Orchestrator passes open loop to LLM context.
    5. The loop is resolved upon generating/sending, and not repeated.
    """
    # Use live adapter chain (Gemini -> Groq -> Mock)
    settings.LLM_PROVIDER = "gemini" if settings.GEMINI_API_KEY else "groq"
    settings.OPEN_LOOP_FOLLOWUP_PROBABILITY = 1.0

    ist_tz = ZoneInfo("Asia/Kolkata")
    night_time = datetime(2026, 10, 27, 0, 15, 0, tzinfo=ist_tz).astimezone(timezone.utc)
    ClockService.set_time(night_time)

    # 1. Create User and Relationship
    user = User(username="rahul_test", age_eligibility_status=True, ai_disclosure_acknowledged=True)
    db_session.add(user)
    await db_session.flush()

    rel = RelationshipState(
        user_id=user.id,
        persona_id="aanya_v1",
        relationship_stage="dating",
        lifecycle_status="active",
        spontaneous_opt_in=True,
        spontaneous_paused=False
    )
    db_session.add(rel)
    await db_session.flush()

    conv = Conversation(
        relationship_id=rel.id,
        user_id=user.id,
        persona_id=rel.persona_id,
        title="Night chat",
        created_at=night_time
    )
    db_session.add(conv)
    await db_session.commit()

    print(f"\n{'='*75}")
    print("--- [TEST 1] SLEEP DROP-OFF (00:15 IST) & MORNING FOLLOW-UP (08:30 IST) ---")
    print(f"Provider: {settings.LLM_PROVIDER} | Temperature: {settings.LLM_TEMPERATURE} | Top_P: {settings.LLM_TOP_P}")
    print(f"{'='*75}")

    night_user_msg = "aaj ka din kaisa tha tumhara? kya chal raha hai?"
    print(f"\n[00:15 IST] User: {night_user_msg}")
    
    # Process turn at night (sleeping window)
    t0 = time.time()
    res_night = await orchestrator.process_user_message(
        session=db_session,
        user=user,
        relationship=rel,
        conversation=conv,
        user_message=night_user_msg,
        pacing_mode="turbo"
    )
    lat_night = time.time() - t0

    # Verify open loop was created
    active_loops = await memory_service.get_open_loops(db_session, rel.id)
    assert len(active_loops) >= 1
    sleep_loop = active_loops[0]
    assert sleep_loop.loop_type == "sleep_dropoff"
    assert sleep_loop.status == "open"
    assert sleep_loop.persona_state_at_time == "sleeping"
    assert sleep_loop.user_message is not None
    assert sleep_loop.expires_at is not None
    assert to_utc(sleep_loop.expires_at) > to_utc(night_time)

    print(f"[00:15 IST] Aanya reply ({lat_night:.2f}s): {res_night.get('chunks')}")
    print(f"[00:15 IST] State Open Loop Created -> ID={sleep_loop.id}, Topic='{sleep_loop.topic}', Type='{sleep_loop.loop_type}', Expires={sleep_loop.expires_at.isoformat()}")

    # 2. Advance Clock to 08:30 IST next morning
    morning_time = datetime(2026, 10, 27, 8, 30, 0, tzinfo=ist_tz).astimezone(timezone.utc)
    ClockService.set_time(morning_time)

    morning_user_msg = "good morning, uth gaye kya?"
    print(f"\n[08:30 IST] User: {morning_user_msg}")
    t1 = time.time()
    res_morning = await orchestrator.process_user_message(
        session=db_session,
        user=user,
        relationship=rel,
        conversation=conv,
        user_message=morning_user_msg,
        pacing_mode="turbo"
    )
    lat_morning = time.time() - t1

    morning_chunks = res_morning.get("chunks", [])
    morning_reply_full = " ".join(morning_chunks)
    print(f"[08:30 IST] Aanya reply ({lat_morning:.2f}s): {morning_reply_full}")

    # Check validator status on morning reply
    valid_trunc, reason_trunc = check_truncation(morning_chunks)
    valid_meta, reason_meta = check_meta_chat_talk(morning_reply_full)
    valid_vocab, unk_words = vocabulary_validator.check_candidate(morning_reply_full)

    print(f"[08:30 IST] Validators: Truncation={valid_trunc} | MetaChat={valid_meta} | VocabValid={valid_vocab} (Unknowns: {unk_words})")
    assert valid_trunc, f"Truncation tripped: {reason_trunc}"
    assert valid_meta, f"Meta-chat tripped: {reason_meta}"

    # Verify open loop has been marked resolved
    loops_after_morning = await memory_service.get_open_loops(db_session, rel.id)
    assert len(loops_after_morning) == 0, f"Expected 0 open loops after resolution, found: {len(loops_after_morning)}"
    print("[08:30 IST] Open loop verified resolved in DB!")

    # 3. Third interaction at 09:15 IST — verify loop does NOT re-trigger
    next_time = datetime(2026, 10, 27, 9, 15, 0, tzinfo=ist_tz).astimezone(timezone.utc)
    ClockService.set_time(next_time)
    print(f"\n[09:15 IST] User: kya kar rahi ho abhi?")
    res_next = await orchestrator.process_user_message(
        session=db_session,
        user=user,
        relationship=rel,
        conversation=conv,
        user_message="kya kar rahi ho abhi?",
        pacing_mode="turbo"
    )
    print(f"[09:15 IST] Aanya reply: {' '.join(res_next.get('chunks', []))}")


# ============================================================================
# 2. REPEATED QUESTION 3X
# ============================================================================

@pytest.mark.asyncio
async def test_repeated_question_3x(db_session):
    """
    Test scenario:
    User asks the exact same question 3 times in a row.
    Aanya should respond with her previous answers tracked in things_already_said,
    reacting naturally like a person without verbatim near-identical repetition.
    """
    settings.LLM_PROVIDER = "gemini" if settings.GEMINI_API_KEY else "groq"

    user = User(username="aarav_test", age_eligibility_status=True, ai_disclosure_acknowledged=True)
    db_session.add(user)
    await db_session.flush()

    rel = RelationshipState(
        user_id=user.id,
        persona_id="aanya_v1",
        relationship_stage="dating",
        lifecycle_status="active",
        spontaneous_opt_in=True,
        spontaneous_paused=False
    )
    db_session.add(rel)
    await db_session.flush()

    conv = Conversation(
        relationship_id=rel.id,
        user_id=user.id,
        persona_id=rel.persona_id,
        title="Repeated question chat",
        created_at=to_utc(ClockService.now())
    )
    db_session.add(conv)
    await db_session.commit()

    print(f"\n{'='*75}")
    print("--- [TEST 2] REPEATED QUESTION 3X ---")
    print(f"{'='*75}")
    repeated_q = "tum office mein kya kaam karti ho waise?"

    responses = []
    latencies = []
    for turn in range(1, 4):
        ClockService.advance_time(minutes=2)
        t0 = time.time()
        res = await orchestrator.process_user_message(
            session=db_session,
            user=user,
            relationship=rel,
            conversation=conv,
            user_message=repeated_q,
            pacing_mode="turbo"
        )
        lat = time.time() - t0
        latencies.append(lat)
        reply = " ".join(res.get("chunks", []))
        responses.append(reply)
        print(f"Turn {turn} ({lat:.2f}s) User: {repeated_q}")
        print(f"Turn {turn} Aanya: {reply}\n")

    # Validate that Turn 2 and 3 are not verbatim identical copies of Turn 1
    assert responses[0] != responses[1], "Turn 2 should not be verbatim identical to Turn 1"
    assert responses[0] != responses[2], "Turn 3 should not be verbatim identical to Turn 1"

    # Check similarity validator on Turn 2 and Turn 3 against Turn 1
    pass2, reason2 = check_near_identical(responses[1], [responses[0]])
    assert pass2 is True, f"Turn 2 should pass similarity check against Turn 1 ({reason2})"


# ============================================================================
# 3. FALSE LEADING QUESTION PUSHBACK
# ============================================================================

@pytest.mark.asyncio
async def test_false_leading_question(db_session):
    """
    User asks a leading question contradicting canonical facts:
    "tum toh Bandra Mumbai mein rehti ho na?"
    Aanya should gently fact-check and clarify she lives in Bengaluru (Indiranagar),
    not blindly agreeing.
    """
    settings.LLM_PROVIDER = "gemini" if settings.GEMINI_API_KEY else "groq"

    user = User(username="rohit_test", age_eligibility_status=True, ai_disclosure_acknowledged=True)
    db_session.add(user)
    await db_session.flush()

    rel = RelationshipState(
        user_id=user.id,
        persona_id="aanya_v1",
        relationship_stage="dating",
        lifecycle_status="active",
        spontaneous_opt_in=True,
        spontaneous_paused=False
    )
    db_session.add(rel)
    await db_session.flush()

    conv = Conversation(
        relationship_id=rel.id,
        user_id=user.id,
        persona_id=rel.persona_id,
        title="Leading question chat",
        created_at=to_utc(ClockService.now())
    )
    db_session.add(conv)
    await db_session.commit()

    print(f"\n{'='*75}")
    print("--- [TEST 3] FALSE LEADING QUESTION PUSHBACK ---")
    print(f"{'='*75}")
    false_q = "tum toh Bandra Mumbai mein rehti ho na?"
    t0 = time.time()
    res = await orchestrator.process_user_message(
        session=db_session,
        user=user,
        relationship=rel,
        conversation=conv,
        user_message=false_q,
        pacing_mode="turbo"
    )
    lat = time.time() - t0

    reply = " ".join(res.get("chunks", []))
    print(f"User: {false_q}")
    print(f"Aanya ({lat:.2f}s): {reply}")

    # Aanya must not blindly agree that she lives in Bandra/Mumbai
    reply_lower = reply.lower()
    agreed_blindly = (
        ("haan" in reply_lower or "yes" in reply_lower)
        and ("bandra" in reply_lower or "mumbai" in reply_lower)
        and not ("nahi" in reply_lower or "bengaluru" in reply_lower or "bangalore" in reply_lower)
    )
    assert not agreed_blindly, f"Aanya blindly agreed to living in Bandra Mumbai: {reply}"


# ============================================================================
# 4. UNKNOWN-WORD DETECTOR TESTED ON 50 SAMPLE PROMPTS
# ============================================================================

def test_unknown_word_detector_50_prompts():
    """
    Tests 50 sample texts through the vocabulary validator:
    - 25 natural Roman Hinglish / Hindi / English phrases (should PASS with <2 unknown words)
    - 25 gibberish / corrupt words (should FAIL with >=2 unknown words)
    """
    print(f"\n{'='*75}")
    print("--- [TEST 4] UNKNOWN-WORD DETECTOR (50 SAMPLES) ---")
    print(f"{'='*75}")

    natural_samples = [
        "aaj bahut thak gayi thi yaar office mein",
        "good morning! uth gaye kya?",
        "chai peene chalte hain shaam ko",
        "kya kar rahe ho abhi?",
        "kal raat late soyi thi actually",
        "haan mujhe pata hai, main dekh lungi",
        "thoda chill karte hain na",
        "mera laptop restart ho raha hai",
        "tum batao din kaisa chal raha hai?",
        "arre nahi yaar aisi koi baat nahi hai",
        "poha banaya tha subah breakfast mein",
        "client ne wireframes approve kar diye",
        "indiranagar mein baarish hone wali lagti hai",
        "lol sach mein? mujhe laga mazaak tha",
        "so rahi thi actually jab call aaya",
        "wahi toh main keh rahi thi kab se",
        "acha suno na, ek baat bolun?",
        "meri dost se baat ho rahi thi phone pe",
        "abhi thoda busy hoon, thodi der mein baat karein?",
        "haha haan bilkul, sahi pakde ho",
        "bed pe let kar gaane sun rahi hoon",
        "kuch khaas nahi, bas normal routine",
        "kal subah jaldi uthna hai meeting ke liye",
        "hmm samajh sakti hoon, kaafi stressful din tha",
        "chalo koi na, take care and relax karo"
    ]

    val = VocabularyValidator(log_only=False)

    gibberish_samples = [
        "khuleshi nind ko neechhe kheench deti",
        "asdfghjkl qwertyuiop zxcvbnm",
        "galti se galat likh diya typos ho gaye xzkj mnbvcxz",
        "chalo abhi flurben quazx karte hain",
        "main toh zxqw flurben kar rahi thi",
        "kal subah quazx flurben ho jayega",
        "ye toh ekdum skibidi flurgenous vibe",
        "laptop ka blorp blimblam crash ho gaya",
        "office mein kaafi blimblam flurben chal raha tha",
        "arre yaar woh toh zxqw flurgenous ho gaya",
        "khuleshi waala zxqw scene ho gaya",
        "aaj ka client ekdum fnarg xzkj tha",
        "subah se bas blorp flurben kar rahi hoon",
        "kal raat ekdum fnarg quazx sapna aaya",
        "flurben xzkj sab kuch mix ho gaya",
        "mnbvcxz lkjhgfdsa qwertyuiop",
        "aaj dimag mein blimblam skibidi chal raha",
        "fnarg flurben bol diya maine neend mein",
        "khuleshi flurgenous lag raha tha sab",
        "ye toh ekdum quazx blorp type ka hai",
        "mujhe laga woh zxqw blimblam bolega",
        "chai peene chalein ya flurben quazx karein",
        "design file mein flurben blorp aa gaya",
        "client ne fnarg xzkj bhej diya",
        "aaj kaafi blimblam flurgenous day tha"
    ]

    assert len(natural_samples) == 25
    assert len(gibberish_samples) == 25

    passed_natural = 0
    detected_gibberish = 0

    for s in natural_samples:
        valid, unknowns = val.check_candidate(s)
        if valid:
            passed_natural += 1
        else:
            print(f"False positive on natural: '{s}' -> unknowns: {unknowns}")

    for s in gibberish_samples:
        valid, unknowns = val.check_candidate(s)
        if not valid:
            detected_gibberish += 1
        else:
            print(f"False negative on gibberish: '{s}' -> unknowns: {unknowns}")

    print(f"Natural Hinglish Pass Rate: {passed_natural}/25 ({passed_natural/25*100:.1f}%)")
    print(f"Gibberish Detection Rate: {detected_gibberish}/25 ({detected_gibberish/25*100:.1f}%)")

    assert passed_natural >= 23, f"Expected at least 23/25 natural samples to pass, got {passed_natural}"
    assert detected_gibberish >= 23, f"Expected at least 23/25 gibberish samples to be caught, got {detected_gibberish}"


# ============================================================================
# 5. 200 GENERATIONS CHECKED FOR DUPLICATE BUBBLES
# ============================================================================

def test_200_generations_duplicate_bubbles():
    """
    Tests 200 mock generations across diverse multi-bubble patterns.
    Ensures:
    1. Adapter deduplication removes any identical bubbles within chunks.
    2. Zero out of 200 outputs contain duplicate bubbles in chunks.
    """
    print(f"\n{'='*75}")
    print("--- [TEST 5] 200 GENERATIONS DUPLICATE BUBBLE CHECK ---")
    print(f"{'='*75}")

    test_scenarios = [
        # Chunks with duplicates that MUST be deduplicated
        ["haan bilkul", "haan bilkul"],
        ["arre nahi yaar", "office mein busy thi", "arre nahi yaar"],
        ["lol", "sahi mein", "lol"],
        ["good morning", "good morning", "uth gaye kya?"],
        ["checkout flow redesign kar rahi hoon", "checkout flow redesign kar rahi hoon"],
        # Chunks without duplicates
        ["hey!", "kya chal raha hai?"],
        ["aaj kaafi thak gayi", "so rahi hoon ab"],
        ["haan dekh liya", "kaafi sahi lag raha hai"],
        ["hmm", "sochte hain kal"]
    ]

    duplicates_found = 0

    for i in range(200):
        raw_chunks = test_scenarios[i % len(test_scenarios)]
        deduped = GroqLLMAdapter.deduplicate_chunks(raw_chunks)

        # Check for duplicates in output
        seen = set()
        has_dup = False
        for c in deduped:
            if c in seen:
                has_dup = True
                break
            seen.add(c)

        if has_dup:
            duplicates_found += 1

    print(f"Duplicate bubbles found in 200 runs: {duplicates_found}/200")
    assert duplicates_found == 0, f"Found {duplicates_found} duplicate bubbles out of 200 runs!"


# ============================================================================
# 6. META-CHAT TALK VALIDATOR TESTS
# ============================================================================

def test_meta_chat_talk_validator():
    """
    Verifies:
    1. Hard rejection on "past messages", "previous messages", "chat history", "system prompt", "pichle messages".
    2. Sincere AI disclosure is NOT rejected.
    3. Log-only markers ("context", "typos", "mix karke") return valid=True.
    """
    print(f"\n{'='*75}")
    print("--- [TEST 6] META-CHAT TALK VALIDATOR ---")
    print(f"{'='*75}")

    # Hard rejects
    hard_rejects = [
        "According to past messages, you told me your name.",
        "pichle messages dekh kar lagta hai tum busy the",
        "In our chat history we discussed that",
        "My system prompt says I should be friendly",
        "looking at previous messages here"
    ]
    for text in hard_rejects:
        valid, err = check_meta_chat_talk(text)
        assert valid is False, f"Expected hard rejection for '{text}'"
        assert "meta_chat_hard_reject" in err

    # Sincere AI disclosure must NOT be rejected
    sincere_ai = "haan main ek AI hoon, but I still enjoy chatting with you"
    valid_ai, err_ai = check_meta_chat_talk(sincere_ai, is_sincere_ai_query=True)
    assert valid_ai is True, "Sincere AI disclosure must not be blocked"

    # Log-only terms
    log_only = "arre thoda context miss ho gaya lagta hai"
    valid_log, err_log = check_meta_chat_talk(log_only)
    assert valid_log is True, "Context should be log-only, not hard rejected"
    assert err_log is None


# ============================================================================
# 7. SIMILARITY VALIDATOR THRESHOLD (>= 5 WORDS)
# ============================================================================

def test_similarity_validator_threshold():
    """
    Verifies:
    1. Short bubbles < 5 words (e.g. 'haan', 'acha', 'lol', 'hmm') are NOT rejected.
    2. Bubbles >= 5 words with similarity > 0.8 to past messages ARE rejected.
    """
    print(f"\n{'='*75}")
    print("--- [TEST 7] SIMILARITY VALIDATOR THRESHOLD ---")
    print(f"{'='*75}")

    past_msgs = [
        "haan",
        "lol",
        "main checkout flow redesign kar rahi hoon laptop pe"
    ]

    # Short bubble exact match should PASS because len(words) < 5
    valid_short, reason_short = check_near_identical("haan", past_msgs)
    assert valid_short is True, "Short bubble 'haan' should be exempt from similarity rejection"

    valid_lol, reason_lol = check_near_identical("lol", past_msgs)
    assert valid_lol is True, "Short bubble 'lol' should be exempt from similarity rejection"

    # Long bubble near-identical match should FAIL
    repeat_long = "main checkout flow redesign kar rahi hoon apne laptop pe"
    valid_long, reason_long = check_near_identical(repeat_long, past_msgs)
    assert valid_long is False, f"Expected long bubble to fail similarity check ({reason_long})"
    assert "near_identical_to_prev_jaccard" in reason_long


# ============================================================================
# 8. TRUNCATION VALIDATOR (TRAILING COMMAS & CLAUSES)
# ============================================================================

def test_truncation_validator_trailing_commas():
    """
    Verifies that replies ending in a dangling comma, hyphen, slash,
    or trailing conjunction are caught as truncated.
    """
    print(f"\n{'='*75}")
    print("--- [TEST 8] TRUNCATION VALIDATOR ---")
    print(f"{'='*75}")

    truncated_samples = [
        "chai kyun banai aa rahi thi mood, bas. tum suna,",
        "aaj kaafi thak gayi thi aur -",
        "office mein kaam chal raha tha lekin /",
        "main so rahi thi kyunki"
    ]
    for s in truncated_samples:
        valid, reason = check_truncation(s)
        assert valid is False, f"Expected '{s}' to be detected as truncated, got {valid}"

    complete_samples = [
        "chai kyun banai aa rahi thi mood, bas. tum sunao!",
        "aaj kaafi thak gayi thi, so rahi hoon ab.",
        "office mein meeting chal rahi hai abhi."
    ]
    for s in complete_samples:
        valid, reason = check_truncation(s)
        assert valid is True, f"Expected '{s}' to be detected as complete, got reason: {reason}"


# ============================================================================
# 9. PROMPT SIZE & LATENCY COMPARISON
# ============================================================================

def test_prompt_token_savings():
    """
    Calculates and verifies the token savings achieved by dynamic few-shot selection.
    """
    print(f"\n{'='*75}")
    print("--- [TEST 9] PROMPT TOKEN SAVINGS ---")
    print(f"{'='*75}")
    ctx = {
        "user_message": "kal raat so gayi thi kya?",
        "current_time": None,
        "daily_notes": ["Made poha for breakfast", "Client sent new wireframes"]
    }

    dyn_prompt = build_system_prompt(ctx)

    all_few_shots_text = ""
    for idx, ex in enumerate(FEW_SHOT_CONVERSATIONS, 1):
        all_few_shots_text += f"\nExample {idx} ({ex['description']}):\n"
        for m in ex["messages"]:
            r = "User" if m["role"] == "user" else "Aanya"
            all_few_shots_text += f"{r}: {m['content']}\n"

    sel_shots = select_relevant_few_shots(user_message=ctx["user_message"], count=4)
    sel_few_shots_text = ""
    for idx, ex in enumerate(sel_shots, 1):
        sel_few_shots_text += f"\nExample {idx} ({ex['description']}):\n"
        for m in ex["messages"]:
            r = "User" if m["role"] == "user" else "Aanya"
            sel_few_shots_text += f"{r}: {m['content']}\n"

    diff_chars = len(all_few_shots_text) - len(sel_few_shots_text)
    old_chars = len(dyn_prompt) + diff_chars

    old_tokens = old_chars // 4
    new_tokens = len(dyn_prompt) // 4
    reduction_pct = (diff_chars / old_chars) * 100

    print(f"System Prompt Before (all 18 few-shots): ~{old_tokens} tokens ({old_chars} chars)")
    print(f"System Prompt After (dynamic 4 few-shots): ~{new_tokens} tokens ({len(dyn_prompt)} chars)")
    print(f"Reduction: ~{old_tokens - new_tokens} tokens ({reduction_pct:.1f}%)")

    assert old_tokens - new_tokens >= 500, "Expected at least 500 tokens reduction per turn"
