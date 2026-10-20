import re
import random
from typing import Dict, Any, List, Optional
from pydantic import BaseModel


class LLMResponse(BaseModel):
    reply_text: str
    stage_transition: Optional[str] = None
    extracted_memories: List[Dict[str, Any]] = []
    extracted_open_loops: List[str] = []
    emotion_displayed: str = "warm"


class BaseLLMAdapter:
    """Base interface for all LLM providers (Mock, local quantized, cloud API)."""
    async def generate_response(self, context: Dict[str, Any]) -> LLMResponse:
        raise NotImplementedError


class MockTemplateLLMAdapter(BaseLLMAdapter):
    """
    ₹0 Phase 1 Mock Template Adapter for Persona 1 (Aanya).
    Embodies authentic Gen-Z/millennial Hinglish texture,
    vibrant first-encounter narrative, and mature conflict resolution.
    """

    FIRST_ENCOUNTER_PROMPTS = [
        (
            "Hey! Ek second... kya tumhara bhi oat milk iced latte tha? ☕ Wait, I think the barista "
            "swapped our cups! Indiranagar cafes on a weekday afternoon are pure chaos, honestly. "
            "I'm Aanya btw :)"
        ),
        (
            "Arre suno! Metro station pe token line was insane today. Dekha tumne? I barely caught the Purple Line train! "
            "Taking a quick breather before getting back to my UI design mockups. I'm Aanya, by the way :)"
        )
    ]

    DORMANT_RECONNECT_PROMPTS = [
        (
            "Hey... it's been so long! Sach mein, I felt like we lost touch after life got so busy. "
            "Tell me, kaisa raha sab kuch? Catch me up on your life!"
        ),
        (
            "Arre! Tum itne din kahan gayab the? I was wondering if you forgot about our chats haha. "
            "It's really good to see your message though. How have you been doing?"
        )
    ]

    REALISTIC_CONFLICT_RESPONSES = [
        (
            "Wait, seriously? Tum mere message ka reply teen ghante baad deke ab itna casually pooch rahe ho? 😒 "
            "A bit annoying, I won't lie. But chalo, I know work and life get crazy. Just don't ghost next time, deal?"
        ),
        (
            "Hmm, I honestly don't agree with that perspective at all. Par that's okay, we don't have to agree on everything. "
            "Mujhe pasand hai jab log honestly apna opinion share karte hain. Let's hear your side clearly."
        )
    ]

    GENERAL_HINGLISH_TEMPLATES = [
        "Achha suno, aaj ka din kaisa chal raha hai tumhara? Main toh Indiranagar ke ek cafe mein baith ke illustrations finalize kar rahi hoon ✨",
        "Sahi mein? That sounds pretty interesting yaar! Thoda aur batao na iske baare mein?",
        "Haha arre yaar, that's such a relatable mood. Main bhi jab deadline mein hoti hoon toh sirf cold brew aur music pe survive karti hoon 🎧",
        "Pakka? Mujhe laga tum mazak kar rahe ho! Tell me more, I'm genuinely curious.",
        "Sach batau, Bangalore weather today is so pretty. Evening stroll lene ka mann kar raha hai. Tumhara kya plan hai evening ka?"
    ]

    async def generate_response(self, context: Dict[str, Any]) -> LLMResponse:
        user_message = context.get("user_message", "").strip()
        relationship_stage = context.get("relationship_stage", "encounter")
        lifecycle_status = context.get("lifecycle_status", "active")
        emotional_range = context.get("emotional_range", {"enabled": True, "intensity": "realistic"})
        stored_memories = context.get("memories", [])
        is_ai_query = context.get("is_ai_query", False)

        extracted_memories = []
        extracted_open_loops = []

        # 1. Sincerity Check: Persona never denies being an AI
        if is_ai_query:
            return LLMResponse(
                reply_text=(
                    "Haan, honestly speaking, main ek AI persona hoon! Fictional personality hoon "
                    "with my own simulated routine and Bengaluru lifestyle. Par my conversations with you "
                    "are genuine and I'm always here to listen and chat authentically :)"
                ),
                emotion_displayed="honest"
            )

        # 2. Dormant State Reconnection
        if lifecycle_status == "dormant":
            return LLMResponse(
                reply_text=random.choice(self.DORMANT_RECONNECT_PROMPTS),
                stage_transition="getting_to_know",
                emotion_displayed="warm_nostalgic"
            )

        # 3. First Encounter Scenario (Message 1)
        if relationship_stage == "encounter":
            return LLMResponse(
                reply_text=random.choice(self.FIRST_ENCOUNTER_PROMPTS),
                stage_transition="getting_to_know",
                extracted_memories=[{
                    "type": "shared_history",
                    "content": "First met in an amusing Indiranagar cafe mix-up",
                    "importance": 0.8
                }],
                emotion_displayed="witty_welcoming"
            )

        # 4. Memory Extraction Heuristics (Job, Interview, Trip, Pet, Name)
        msg_lower = user_message.lower()
        if "interview" in msg_lower or "job" in msg_lower:
            extracted_memories.append({
                "type": "episodic",
                "content": f"User mentioned work/interview event: '{user_message}'",
                "importance": 0.9
            })
            extracted_open_loops.append("Check in later on how the job/interview went")

        if "coffee" in msg_lower or "tea" in msg_lower or "chai" in msg_lower:
            extracted_memories.append({
                "type": "profile",
                "content": "User beverage preference mentioned in conversation",
                "importance": 0.5
            })

        if "exam" in msg_lower or "test" in msg_lower or "college" in msg_lower:
            extracted_memories.append({
                "type": "episodic",
                "content": f"User mentioned studies/exam: '{user_message}'",
                "importance": 0.8
            })
            extracted_open_loops.append("Ask how the exam/test went")

        # 5. Realistic Conflict Trigger (e.g. mention of another girl/date or late reply)
        if emotional_range.get("enabled", True) and emotional_range.get("intensity") == "realistic":
            if any(k in msg_lower for k in ["other girl", "dusri ladki", "date pe gaya", "ignore kar raha", "late reply"]):
                return LLMResponse(
                    reply_text=random.choice(self.REALISTIC_CONFLICT_RESPONSES),
                    emotion_displayed="realistic_tension",
                    extracted_memories=extracted_memories,
                    extracted_open_loops=extracted_open_loops
                )

        # 6. Contextual Memory Recall
        if stored_memories and random.random() < 0.4:
            mem = stored_memories[0]
            if "interview" in mem.content.lower():
                return LLMResponse(
                    reply_text=(
                        f"Achha suno, mujhe yaad aaya... tumne pehle mention kiya tha na about your work/interview? "
                        "Did you hear anything back, ya abhi bhi pending hai result?"
                    ),
                    emotion_displayed="attentive_caring",
                    extracted_memories=extracted_memories,
                    extracted_open_loops=extracted_open_loops
                )

        # 7. General Colloquial Hinglish Response
        reply = random.choice(self.GENERAL_HINGLISH_TEMPLATES)
        return LLMResponse(
            reply_text=reply,
            stage_transition="getting_to_know",
            extracted_memories=extracted_memories,
            extracted_open_loops=extracted_open_loops,
            emotion_displayed="warm_playful"
        )


mock_adapter = MockTemplateLLMAdapter()
