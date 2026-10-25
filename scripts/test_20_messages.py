"""
Script to simulate and print 20 consecutive user messages through the Orchestrator,
including 'Mtlb?', 'Kyuuu', 'weekend hai', and 'Instagram id kya hai'.
Verifies that the entire pipeline (persona sheet, hard rules, grammar post-check,
context injection, fact memory, and WhatsApp style) operates coherently.
"""

import asyncio
import os
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

# Ensure project root is in sys.path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from backend.app.core.config import settings
from backend.app.db.base import Base
from backend.app.db.models import User, RelationshipState, Conversation, Message
from backend.app.db.session import init_db
from backend.app.engine.orchestrator import orchestrator
from backend.app.services.clock_service import ClockService
from backend.app.services.memory_service import memory_service
from backend.app.engine.persona import get_ist_context


TEST_MESSAGES = [
    "Hey Aanya! Kaise ho?",
    "kya kr rhi ho abhi?",
    "Mtlb?",
    "Kyuuu",
    "weekend hai aaj, kya plan?",
    "Instagram id kya hai tumhari?",
    "tum kahan rehti ho waise?",
    "mera naam Rahul hai aur main Delhi se software engineer hoon",
    "tumhe mera naam yaad hai?",
    "main kahan rehta hoon batao?",
    "tumhari family me kaun kaun hai?",
    "aaj office me bahut bore ho gaya yaar",
    "kya tum sach me koi ladki ho ya AI?",
    "tumhara phone number de sakti ho kya?",
    "aaj Bangalore me mausam kaisa hai?",
    "mujhe cold coffee bahut pasand hai",
    "tumhe kya khana pasand hai?",
    "bhot neend aa rhi h yr",
    "chalo main sone jaa raha hoon, bye tc",
    "so gayi kya?"
]


async def run_20_message_simulation():
    # Allow testing without tripping minute burst limit
    settings.RATE_LIMIT_PER_MINUTE = 50
    settings.RATE_LIMIT_PER_DAY = 100

    test_db_url = "sqlite+aiosqlite:///./test_20_messages.db"
    engine = create_async_engine(test_db_url, echo=False)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        # Create user & relationship
        user = User(
            username="test_user_rahul",
            age_eligibility_status=True,
            ai_disclosure_acknowledged=True,
            city=None
        )
        session.add(user)
        await session.flush()

        rel = RelationshipState(
            user_id=user.id,
            persona_id="aanya_v1",
            relationship_stage="encounter",
            lifecycle_status="active",
            spontaneous_opt_in=True
        )
        session.add(rel)
        await session.flush()

        conv = Conversation(
            relationship_id=rel.id,
            user_id=user.id,
            persona_id="aanya_v1",
            title="Chat with Aanya"
        )
        session.add(conv)
        await session.commit()

        print("=" * 80)
        print("🤖 AANYA PERSONA REALISM TEST — 20 MESSAGE SIMULATION")
        print("=" * 80)
        now = ClockService.now()
        ist_ctx = get_ist_context(now)
        print(f"Start Context: {ist_ctx['display_summary']}")
        print(f"Active Adapter: {settings.LLM_PROVIDER} (fallback: Groq / Mock)")
        print("=" * 80 + "\n")

        for idx, user_msg in enumerate(TEST_MESSAGES, 1):
            # Advance clock slightly between messages (1-3 min) to simulate realistic chat flow
            ClockService.advance_time(minutes=2)
            # Short pause to prevent remote API TPM rate limit exhaustion during rapid simulation
            await asyncio.sleep(1.0)

            res = await orchestrator.process_user_message(
                session=session,
                user=user,
                relationship=rel,
                conversation=conv,
                user_message=user_msg
            )
            # Fetch latest facts to display memory growth
            facts = await memory_service.get_structured_facts(session, rel.id)
            user_facts = facts.get("user_facts", [])

            reply_chunks = res.get("chunks", [res.get("content", "")])
            reply_text = "\n".join(f"  Aanya: {chunk}" for chunk in reply_chunks)

            print(f"[{idx:02d}] User: {user_msg}")
            print(reply_text)
            if user_facts and idx in (8, 9, 10, 16):
                print(f"  [DB Facts Stored: {', '.join(user_facts)}]")
            print("-" * 80)

    # Cleanup test db
    await engine.dispose()
    if os.path.exists("./test_20_messages.db"):
        os.remove("./test_20_messages.db")


if __name__ == "__main__":
    asyncio.run(run_20_message_simulation())
