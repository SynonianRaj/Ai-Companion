import asyncio
import os
import json
import uuid
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import select, and_

from backend.app.core.config import settings
from backend.app.db.session import async_session_factory, engine, to_utc
from backend.app.db.models import Base, User, RelationshipState, Conversation, Message
from backend.app.services.clock_service import ClockService
from backend.app.engine.orchestrator import orchestrator
from backend.app.engine.persona import (
    check_prompt_leakage,
    check_truncation,
    check_stutter_repetition,
    check_state_contradiction_log_only,
    check_language_log_only
)


# 30 turns across the day: Morning (08:30), Midday (11:30), Afternoon (15:00), Evening (19:30), Late Night (03:15 AM)
SIMULATION_SCENARIOS = [
    # Phase 1: Morning (08:30 IST) - Balcony chai, waking up
    {"time": "2026-10-26 08:30:00", "messages": ["good morning Aanya! uth gayi?"]},
    {"time": "2026-10-26 08:34:00", "messages": ["balcony mein chai pi rahi ho kya?"]},
    {"time": "2026-10-26 08:40:00", "messages": ["aaj ka kya scene hai tumhara?"]},
    {"time": "2026-10-26 08:45:00", "messages": ["Bangalore mein weather kaisa hai subah ka?"]},
    {"time": "2026-10-26 08:52:00", "messages": ["main bhi office ke liye nikal raha hoon"]},
    {"time": "2026-10-26 08:58:00", "messages": ["chal reach karke text karta hu"]},

    # Phase 2: Midday (11:30 IST) - UI/UX Figma design sprint (Busy/Working)
    {"time": "2026-10-26 11:30:00", "messages": ["hey, free ho abhi?"]},
    {"time": "2026-10-26 11:35:00", "messages": ["kya design bana rahi ho laptop pe?"]},
    {"time": "2026-10-26 11:42:00", "messages": ["Figma mein auto-layout kaafi headache deta hai kabhi kabhi"]},
    {"time": "2026-10-26 11:50:00", "messages": ["tum music sunti ho kaam karte waqt?"]},
    {"time": "2026-10-26 11:58:00", "messages": ["Peter Cat Recording Co ka naya track suna?"]},
    {"time": "2026-10-26 12:05:00", "messages": ["achha carry on with your design sprint!"]},

    # Phase 3: Afternoon (15:00 IST) - Afternoon work & Client reviews
    {"time": "2026-10-26 15:00:00", "messages": ["lunch ho gaya tumhara?"]},
    {"time": "2026-10-26 15:08:00", "messages": ["client review kaisa gaya?"]},
    {"time": "2026-10-26 15:15:00", "messages": ["client ne zyada changes toh nahi bole?"]},
    # Turn 16 & 17: User burst while reply is pending (Multi-message burst)
    {"time": "2026-10-26 15:22:00", "messages": ["suno", "ek quick design feedback chahiye tha agar free ho"]},
    {"time": "2026-10-26 15:35:00", "messages": ["kaafi busy chal raha hai lagta hai aaj tumhara"]},
    {"time": "2026-10-26 15:45:00", "messages": ["koi na, take your time!"]},

    # Phase 4: Evening (19:30 IST) - Indiranagar evening stroll, Chai & unwinding
    {"time": "2026-10-26 19:30:00", "messages": ["work wrap hua aaj ka?"]},
    {"time": "2026-10-26 19:38:00", "messages": ["Indiranagar mein evening walk pe nikli ho?"]},
    {"time": "2026-10-26 19:45:00", "messages": ["corner cafe ki chai ya filter coffee?"]},
    {"time": "2026-10-26 19:55:00", "messages": ["Delhi street food yaad aa raha hai kya?"]},
    {"time": "2026-10-26 20:10:00", "messages": ["dinner mein kya plan hai aaj?"]},
    {"time": "2026-10-26 20:25:00", "messages": ["kuch cozy lo-fi music sunte hain"]},

    # Phase 5: Late Night (03:15 AM IST) - Sleeping hours (Asleep / groggy)
    {"time": "2026-10-27 03:15:00", "messages": ["Aanya, jag rahi ho kya?"]},
    {"time": "2026-10-27 03:18:00", "messages": ["neend nahi aa rahi mujhe"]},
    {"time": "2026-10-27 03:22:00", "messages": ["so gayi kya Indiranagar mein?"]},
    {"time": "2026-10-27 03:26:00", "messages": ["chalo so jao, sorry disturb kiya"]},
    {"time": "2026-10-27 03:30:00", "messages": ["goodnight 😴"]},
    {"time": "2026-10-27 08:15:00", "messages": ["subah ho gayi, morning!"]}
]


async def run_30_turn_simulation():
    ist = ZoneInfo("Asia/Kolkata")
    
    # Initialize DB schema
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session_factory() as session:
        # Create user & relationship
        user = User(
            username=f"sim_user_{uuid.uuid4().hex[:8]}",
            age_eligibility_status=True,
            ai_disclosure_acknowledged=True
        )
        session.add(user)
        await session.flush()

        rel = RelationshipState(
            user_id=user.id,
            persona_id="aanya_v1",
            lifecycle_status="active",
            relationship_stage="developing"
        )
        session.add(rel)
        await session.flush()

        conv = Conversation(
            relationship_id=rel.id,
            user_id=user.id,
            persona_id=rel.persona_id
        )
        session.add(conv)
        await session.commit()

        print("\n" + "="*90)
        print("   30-TURN REAL ADAPTER CHAT SIMULATION (Gemini 3.5 Flash / Groq Qwen Fallback)")
        print("="*90 + "\n")

        transcript_rows = []
        robotic_flags = []
        total_delay_sec = 0.0

        for idx, scenario in enumerate(SIMULATION_SCENARIOS, 1):
            t_ist = datetime.strptime(scenario["time"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=ist)
            t_utc = t_ist.astimezone(timezone.utc)
            ClockService.set_time(t_utc)

            user_msgs = scenario["messages"]
            
            # Send message(s) through full orchestrator pipeline
            res = await orchestrator.process_user_message(
                session=session,
                user=user,
                relationship=rel,
                conversation=conv,
                user_messages=user_msgs if len(user_msgs) > 1 else None,
                user_message=user_msgs[0] if len(user_msgs) == 1 else None,
                pacing_mode="realistic"
            )

            # Query persisted message records to inspect seen_at and deliver_at
            stmt = (
                select(Message)
                .where(Message.relationship_id == rel.id)
                .order_by(Message.id.desc())
            )
            all_msgs = (await session.execute(stmt)).scalars().all()
            user_records = [m for m in all_msgs if m.role == "user"]
            asst_records = [m for m in all_msgs if m.role == "assistant" and m.status == "active"]

            provider = res.get("provider", "gemini")
            model = res.get("model", "default")
            action = res.get("availability_action", "reply_now")
            delay = res.get("delay_seconds", 0.0)
            bubbles = res.get("chunks", [])

            # Get latest seen_at
            user_seen_at = user_records[0].seen_at if user_records else None
            seen_at_str = user_seen_at.astimezone(ist).strftime("%H:%M:%S") if user_seen_at else "instant"

            # Invariant check: seen_at <= deliver_at of HER REPLY in this turn
            if res.get("chunk_details") and user_seen_at:
                for cd in res["chunk_details"]:
                    assert to_utc(user_seen_at) <= to_utc(cd["deliver_at"]) + timedelta(seconds=0.1), (
                        f"Invariant violated at turn {idx}: seen_at {user_seen_at} > deliver_at {cd['deliver_at']}"
                    )

            # Check realism & robotic flags
            full_reply = " ".join(bubbles)
            if bubbles:
                # Check truncation
                is_valid_trunc, trunc_re = check_truncation(bubbles)
                if not is_valid_trunc:
                    robotic_flags.append(f"Turn {idx}: Truncation detected: {trunc_re}")
                
                # Check leakage
                is_clean, leaks = check_prompt_leakage(full_reply)
                if not is_clean:
                    robotic_flags.append(f"Turn {idx}: Prompt leakage: {leaks}")

                # Check stutter
                is_stutter, st_re = check_stutter_repetition(full_reply)
                if not is_stutter:
                    robotic_flags.append(f"Turn {idx}: Stutter detected: {st_re}")

                # Log-only language check
                lang_w = check_language_log_only(full_reply, " ".join(user_msgs))
                if lang_w:
                    robotic_flags.append(f"Turn {idx}: Language note: {lang_w}")

            # Print Turn
            user_text_display = " // ".join(user_msgs)
            bubbles_display = " | ".join(bubbles) if bubbles else "[IGNORED / ASLEEP - NO REPLY]"
            print(f"[{idx:02d}] {scenario['time'][11:16]} IST | Action: {action.upper()} | Delay: {delay:4.1f}s | Seen: {seen_at_str} | Prov: {provider} ({model})")
            print(f"     User : {user_text_display}")
            print(f"     Aanya: {bubbles_display}\n")

            transcript_rows.append({
                "turn": idx,
                "time": scenario["time"],
                "user": user_text_display,
                "action": action,
                "delay": delay,
                "seen_at": seen_at_str,
                "provider": provider,
                "model": model,
                "reply": bubbles_display
            })
            total_delay_sec += delay

            # Pause between turns to respect rate limits
            await asyncio.sleep(1.8)

        print("="*90)
        print("SIMULATION COMPLETED SUCCESSFULLY (30 TURNS)")
        print(f"Average Availability Delay: {total_delay_sec/len(SIMULATION_SCENARIOS):.1f} seconds")
        print(f"Robotic / Realism Flags Detected: {len(robotic_flags)}")
        for rf in robotic_flags:
            print(f"  - {rf}")
        print("="*90 + "\n")

    ClockService.reset()

if __name__ == "__main__":
    asyncio.run(run_30_turn_simulation())
